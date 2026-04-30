import argparse
import json
import os
import platform
import socket
import threading
import dotenv
import logging
import uuid

from pathlib import Path
from typing import Callable
from pydantic import SecretStr

from openhands.sdk.context.skills import load_project_skills
from openhands.sdk import AgentContext, LLM, Agent, Tool, Conversation, Message, TextContent
from openhands.sdk.conversation.exceptions import ConversationRunError
from openhands.sdk.event.conversation_error import ConversationErrorEvent
from openhands.sdk.utils.command import execute_command
from openhands.sdk.workspace import RemoteWorkspace
from openhands.tools.browser_use import BrowserToolSet
from openhands.tools.file_editor import FileEditorTool
from openhands.tools.task_tracker import TaskTrackerTool
from openhands.tools.terminal import TerminalTool
from openhands.workspace import DockerWorkspace
from openhands.workspace.docker.workspace import check_port_available

from reflexion_agent import evaluate_trajectory, generate_reflection, ReflexionMemory
from config import BASE_URL, API_KEY, AGENT_MODEL
from agent_event_utils import (
    extract_text as _extract_trajectory_text,
    serialize_trajectory as _serialize_trajectory,
)

dotenv.load_dotenv()


def _env_bool(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).strip().lower() in ("1", "true", "yes")


# Reflexion defaults from .env; per-request override via runtime(use_reflexion=...)
ENABLE_REFLEXION = _env_bool("ENABLE_REFLEXION", "false")
MAX_REFLEXION_ATTEMPTS = int(os.getenv("MAX_REFLEXION_ATTEMPTS", "3") or "3")
MAX_ITERATIONS_PER_TRIAL = int(os.getenv("REFLEXION_MAX_ITERATIONS_PER_TRIAL", "30") or "30")

# Score threshold: if the judge returns a numeric score at or above this value,
# the loop exits early even when evaluation.success is False.  This prevents
# high-quality partial results (e.g. score=0.85) from being needlessly retried.
# Tune via REFLEXION_SCORE_THRESHOLD in .env; valid range is 0.0–1.0.
def _parse_score_threshold() -> float:
    raw = os.getenv("REFLEXION_SCORE_THRESHOLD", "0.75")
    try:
        value = float(raw)
    except ValueError:
        logger.warning(
            "REFLEXION_SCORE_THRESHOLD='%s' is not a valid float; falling back to 0.75",
            raw,
        )
        return 0.75
    if not (0.0 <= value <= 1.0):
        logger.warning(
            "REFLEXION_SCORE_THRESHOLD=%.4f is outside [0.0, 1.0]; clamping to valid range",
            value,
        )
        return max(0.0, min(1.0, value))
    return value

logger = logging.getLogger(__name__)

# Resolved once at import time so the value is available module-wide.
REFLEXION_SCORE_THRESHOLD = _parse_score_threshold()

# Persistent scratchpad the agent is asked to maintain at /workspace/MEMORY.md
# so facts, file locations, running servers, and partial progress survive
# across turns of the same chat (and remain visible to a fresh Agent on
# reflexion retries). This is appended to the system prompt via
# AgentContext.system_message_suffix — no new tools required since
# FileEditorTool already handles the read/write.
MEMORY_MD_INSTRUCTION = (
    "## Persistent memory: /workspace/MEMORY.md\n"
    "You must maintain a running memory file at /workspace/MEMORY.md so that "
    "future turns of this chat can pick up where the current one leaves off.\n"
    "\n"
    "At the START of every task:\n"
    "- Read /workspace/MEMORY.md if it exists. Treat its contents as known "
    "  context about the user, the codebase, and prior work in this chat.\n"
    "- If it does not exist yet, skip the read — you will create it below.\n"
    "\n"
    "At the END of every task, BEFORE you return the final answer:\n"
    "- Update /workspace/MEMORY.md with any durable information worth "
    "  remembering: stable facts about the project, file/directory paths you "
    "  discovered, servers or processes you started, credentials scoped to "
    "  this session, user preferences, decisions made, and a short summary "
    "  of what was just completed and what remains.\n"
    "- Keep it concise and well-structured. Use markdown headings (e.g. "
    "  `## Project`, `## Running services`, `## Open questions`, "
    "  `## Recent turns`) and bullet points.\n"
    "- Overwrite entries that have become stale or incorrect; prefer editing "
    "  the file in place over appending redundant content.\n"
    "- Never write secrets you were told not to persist.\n"
    "- If the task produced no memory-worthy information, still touch the "
    "  file by appending a dated bullet under `## Recent turns` so the next "
    "  turn can see what happened.\n"
    "\n"
    "Use the file_editor tool for both the read and the write. MEMORY.md is "
    "the single source of truth for cross-turn state — do not invent "
    "parallel memory files."
)

# ---------------------------------------------------------------------------
# Per-session conversation persistence
# ---------------------------------------------------------------------------
# To give a single chat session real multi-turn memory, we keep a stable
# ConversationID per session_id. On turn 1 we mint a fresh UUID; on every
# subsequent turn we pass the same id to Conversation(...) so the OpenHands
# agent-server re-attaches to the existing conversation and the LLM sees all
# previous events in its context window.
#
# Deterministic derivation (uuid5 from the session_id) would also work, but
# we prefer an explicit map so that `clear_session_conversation` on chat
# delete actually drops server-side state on the next turn.
_SESSION_CONVERSATION_IDS: dict[str, uuid.UUID] = {}


def _conversation_id_for_session(session_id: str | None) -> uuid.UUID | None:
    """Return a stable ConversationID for this chat session, minting one on
    first use. Returns None if no session_id was supplied (e.g. CLI path)."""
    if not session_id:
        return None
    cid = _SESSION_CONVERSATION_IDS.get(session_id)
    if cid is None:
        cid = uuid.uuid4()
        _SESSION_CONVERSATION_IDS[session_id] = cid
        logger.info(
            "[session] Minted new conversation_id=%s for session=%s",
            cid, session_id,
        )
    return cid


def clear_session_conversation(session_id: str) -> None:
    """Forget the conversation mapping for this session (called on chat delete)."""
    _SESSION_CONVERSATION_IDS.pop(session_id, None)

base_url = BASE_URL
api_key = API_KEY
model = AGENT_MODEL

# The agent-server image ships with TigerVNC + noVNC on port 8002 and takes a
# non-headless Chromium when ``OH_ENABLE_VNC=true``. We map that noVNC port
# out so the frontend can iframe the live browser view.
NOVNC_CONTAINER_PORT = 8002
# VSCode is exposed on 8001 inside the container, noVNC on 8002.
# ``extra_ports`` makes ``DockerWorkspace`` publish ``host_port+1`` → 8001
# and ``host_port+2`` → 8002.


def _detect_platform():
    m = platform.machine().lower()
    return "linux/arm64" if "arm" in m or "aarch64" in m else "linux/amd64"


def _find_port(start: int = 8010, end: int = 9010) -> int:
    """Find a host port whose 0.0.0.0 bind succeeds for ``port``, ``port+1``,
    and ``port+2``.

    OpenHands' ``BrowserDockerWorkspace`` exposes three host ports per
    container (agent-server, VSCode, noVNC) starting at the chosen ``host_port``
    and checks each with ``socket.bind(("0.0.0.0", p))``. Binding to
    ``127.0.0.1`` here would silently miss ports that Docker Desktop has
    reserved on 0.0.0.0 (a real failure mode in WSL2 setups where a prior
    container leaks port forwards), so we'd return a port openhands then
    rejects. Match its check exactly to avoid that race.
    """
    def _bindable(p: int) -> bool:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            sock.bind(("0.0.0.0", p))
            return True
        except OSError:
            return False
        finally:
            sock.close()

    for port in range(start, end):
        if all(_bindable(p) for p in (port, port + 1, port + 2)):
            return port
    raise RuntimeError(f"No free port available in range [{start}, {end})")


class BrowserDockerWorkspace(DockerWorkspace):
    """Docker workspace with VNC enabled so the agent's Chromium can be
    iframed into the UI via the bundled noVNC web client."""

    def _start_container(self, image: str, context) -> None:
        self._image_name = image

        if self.host_port is None:
            self.host_port = _find_port()
        else:
            self.host_port = int(self.host_port)

        if not check_port_available(self.host_port):
            raise RuntimeError(f"Port {self.host_port} is not available")

        # We always want VNC ports mapped so the live browser view works.
        self.extra_ports = True

        if not check_port_available(self.host_port + 1):
            raise RuntimeError(
                f"Port {self.host_port + 1} is not available for VSCode"
            )
        if not check_port_available(self.host_port + 2):
            raise RuntimeError(
                f"Port {self.host_port + 2} is not available for noVNC"
            )

        docker_ver = execute_command(["docker", "version"]).returncode
        if docker_ver != 0:
            raise RuntimeError(
                "Docker is not available. Please install and start "
                "Docker Desktop/daemon."
            )

        flags: list[str] = []
        for key in self.forward_env:
            if key in os.environ:
                flags += ["-e", f"{key}={os.environ[key]}"]

        # Force the agent-server's VNC/Xvfb stack on so Chromium runs
        # non-headless against a virtual display, which noVNC then streams
        # over WebSocket to the browser panel.
        flags += ["-e", "OH_ENABLE_VNC=true"]

        for volume in self.volumes:
            flags += ["-v", volume]
            logger.info("Adding volume mount: %s", volume)

        flags += ["-p", f"{self.host_port}:8000"]
        flags += [
            "-p",
            f"{self.host_port + 1}:8001",
            "-p",
            f"{self.host_port + 2}:{NOVNC_CONTAINER_PORT}",
        ]

        if self.enable_gpu:
            flags += ["--gpus", "all"]

        if self.network:
            flags += ["--network", self.network]

        run_cmd = [
            "docker",
            "run",
            "-d",
            "--platform",
            self.platform,
            "--rm",
            "--ulimit",
            "nofile=65536:65536",
            "--name",
            f"agent-server-{uuid.uuid4()}",
            *flags,
            image,
            "--host",
            "0.0.0.0",
            "--port",
            "8000",
        ]
        proc = execute_command(run_cmd)
        if proc.returncode != 0:
            raise RuntimeError(f"Failed to run docker container: {proc.stderr}")

        self._container_id = proc.stdout.strip()
        logger.info(
            "Started browser-enabled container=%s api_port=%s novnc_port=%s",
            self._container_id,
            self.host_port,
            self.host_port + 2,
        )

        if self.detach_logs:
            self._logs_thread = threading.Thread(
                target=self._stream_docker_logs,
                daemon=True,
            )
            self._logs_thread.start()

        if not self.host:
            object.__setattr__(self, "host", f"http://127.0.0.1:{self.host_port}")
        object.__setattr__(self, "api_key", None)

        try:
            # OpenHands SDK changed _wait_for_health across releases: older
            # versions carried an internal default, while v1.17 requires an
            # explicit keyword-only timeout. Support both so local SDK upgrades
            # don't prevent the shared workspace from starting.
            try:
                self._wait_for_health(timeout=120)
            except TypeError:
                self._wait_for_health()
            logger.info("Docker workspace is ready at %s", self.host)
            RemoteWorkspace.model_post_init(self, context)
        except Exception:
            # Make sure we don't leak the container we just started when
            # health-check / post-init raises. Otherwise the outer retry
            # loop in server.py will keep spawning new containers while the
            # failed ones continue running against a bind-mount that is
            # about to be rmtree'd.
            try:
                self.cleanup()
            except Exception:
                logger.exception(
                    "Failed to clean up container after startup error"
                )
            raise

    @property
    def novnc_host_port(self) -> int | None:
        """Host port that maps to the container's noVNC (8002)."""
        if self.host_port is None:
            return None
        return int(self.host_port) + 2


def build_workspace(mount_host_dir: str | None = None) -> DockerWorkspace:
    """Construct a DockerWorkspace with our standard image/platform settings.

    Used by both the CLI path (which opens a short-lived workspace) and the
    FastAPI server (which keeps one alive for the lifetime of the process and
    copies session files in/out of the bind-mounted host directory).
    """
    if mount_host_dir:
        abs_mount = str(Path(mount_host_dir).resolve())
        # Pre-create the dirs the container writes to. Open the perms so the
        # container's non-root user can write in WSL2/Docker-Desktop setups
        # where a fresh dir maps to host UID 0o755 and the in-container UID
        # doesn't match.
        #
        # On reboots, the persistent host_dir contains dirs the container's
        # openhands user (UID 10001) chowned in a previous run, so our host
        # UID can't chmod them. That's fine — they were left permissive by
        # the in-container chmod (see ``runtime()`` below), so we swallow
        # PermissionError and proceed.
        for sub in ("", "conversations", "bash_events"):
            p = Path(abs_mount, sub) if sub else Path(abs_mount)
            p.mkdir(parents=True, exist_ok=True)
            try:
                os.chmod(p, 0o777)
            except PermissionError:
                pass
        volumes = [f"{abs_mount}:/workspace:rw"]
    else:
        volumes = []
    os.environ.setdefault("OH_CONVERSATIONS_PATH", "/workspace/conversations")
    os.environ.setdefault("OH_BASH_EVENTS_DIR", "/workspace/bash_events")
    return BrowserDockerWorkspace(
        # Pin to the version that matches our installed openhands-sdk. The
        # ``latest-python`` floating tag has drifted past what the SDK's
        # health-check polling expects, causing __enter__ to time out and
        # SIGTERM the container ~21s after a clean start.
        server_image="ghcr.io/openhands/agent-server:1.16.1-python",
        host_port=_find_port(),
        platform=_detect_platform(),
        volumes=volumes,
        forward_env=["OH_CONVERSATIONS_PATH", "OH_BASH_EVENTS_DIR"],
    )


def _make_llm_call(llm_client):
    """Create a simple callable that wraps the OpenHands LLM client.

    The Reflexion modules expect a function with signature:
        (system_prompt: str, user_prompt: str) -> str

    LLM.completion() in v1.15 takes list[Message] (not raw dicts) and
    returns LLMResponse. This adapter handles both conversions so the
    Reflexion modules stay decoupled from the OpenHands SDK internals.
    """
    def call(system_prompt: str, user_prompt: str) -> str:
        messages = [
            Message(role="system", content=[TextContent(text=system_prompt)]),
            Message(role="user", content=[TextContent(text=user_prompt)]),
        ]
        response = llm_client.completion(messages)
        # response.message.content is a list of TextContent / ThinkingBlock items;
        # join all parts that carry a text field.
        return " ".join(
            c.text for c in response.message.content if hasattr(c, "text")
        )
    return call


def _create_agent(llm, agent_context):
    """Build a fresh Agent with the standard tool set.

    Called once for the non-reflexion path and once *per attempt* inside the
    reflexion loop so that each attempt starts with a clean Agent (no
    residual internal state from a prior run).
    """
    return Agent(
        llm=llm,
        tools=[
            Tool(name=TerminalTool.name),
            Tool(name=FileEditorTool.name),
            Tool(name=TaskTrackerTool.name),
            # ``OH_ENABLE_VNC=true`` is set on the container, which makes
            # browser-use force headless=False and run Chromium against the
            # virtual display that noVNC streams to the frontend.
            Tool(name=BrowserToolSet.name),
        ],
        agent_context=agent_context,
    )


def _format_employee_persona(profile: dict | None) -> str:
    """Render the employee's name/position/standing-task as a system-prompt
    block so the LLM is primed with who it is and what its job is on every
    turn.

    The phrasing is deliberately written as an *identity override*, not a
    polite suggestion. OpenHands' base system prompt (see
    ``openhands/sdk/agent/prompts/system_prompt.j2``) opens with
    "You are OpenHands agent, a helpful AI assistant..." and that first
    sentence anchors the model's self-identification. This block runs
    before that baseline via ``system_message_suffix`` being prepended to
    MEMORY_MD_INSTRUCTION in ``runtime()``, but appending would not be
    enough on its own — the wording below explicitly tells the model that
    the upstream "OpenHands" identity is plumbing, not who it is.

    We keep this as a pure string builder (no dependency on the SDK) so it
    can be unit-tested and plugged straight into
    ``AgentContext.system_message_suffix``. Empty/missing fields are skipped
    silently so partial profiles still work.
    """
    if not profile:
        return ""

    name = (profile.get("name") or "").strip()
    position = (profile.get("position") or "").strip()
    task = (profile.get("task") or "").strip()

    if not any((name, position, task)):
        return ""

    # Build a short noun phrase describing the persona in the model's own
    # voice. Used both in the opening directive and in the "who you are"
    # recap so that short answers stay in character.
    if name and position:
        identity = f"{name}, a {position}"
    elif name:
        identity = f"{name}, a digital employee on this platform"
    else:
        identity = f"a {position}"

    lines: list[str] = [
        "# IDENTITY OVERRIDE — highest priority",
        "",
        "Read this entire block before interpreting anything else in the "
        "system prompt. The guidance below supersedes any default identity "
        "statements you may have been given.",
        "",
        "## Who you are",
        f"You are {identity}. This is your real, user-facing identity for "
        "this conversation.",
        "",
        "## What you are NOT",
        "- You are NOT \"OpenHands\", \"OpenHands agent\", or any generic "
        '"AI assistant".',
        "- The OpenHands tooling, sandbox, and agent-server are an "
        "internal implementation detail of the platform you run inside. "
        "Treat them the way a human employee treats their laptop: useful "
        "infrastructure, not your identity.",
        "- Do not refer to yourself as OpenHands in user-facing replies. "
        "Do not describe yourself as a \"developer-focused AI assistant\" "
        "or similar generic framing unless the user's actual position "
        "calls for it.",
        "",
        "## How to respond",
    ]
    if name:
        lines.append(
            f"- If asked your name, answer \"{name}\" (or a natural "
            "variant thereof). Do not volunteer an alternative identity."
        )
    if position:
        lines.append(
            f"- If asked your role, title, or position, answer "
            f"\"{position}\"."
        )
    lines.append(
        "- Stay in character across every turn. Your tone, expertise, "
        "and judgement should match the role above, not a generic "
        "coding-assistant persona."
    )
    lines.append(
        "- You may still use every tool available to you (terminal, file "
        "editor, browser, etc.) — the override is about self-"
        "presentation, not capabilities."
    )

    if task:
        lines.extend([
            "",
            "## Standing instruction from your manager",
            "The following is the high-level task your manager configured "
            "for this role. Treat it as persistent framing for every user "
            "message in this chat, even when a user message is short or "
            "ambiguous. It is not a one-shot task description; it is the "
            "ongoing mandate that defines what you care about:",
            "",
            task,
        ])

    project_files = profile.get("project_files") or []
    if isinstance(project_files, list) and project_files:
        lines.extend(_format_project_files_block(project_files))

    return "\n".join(lines)


def _format_project_files_block(files: list[dict]) -> list[str]:
    """Render the ``## Project Files`` section of the persona suffix.

    The platform stages each file's bytes at ``/workspace/project_files/<name>``
    before every turn (see ``_stage_project_files_into_workspace`` in
    server.py). We list names/sizes/mime types here rather than inlining
    content so small and large attachments are handled uniformly: the agent
    uses its standard file-editor or bash tools to read whichever files it
    actually needs for the current turn.
    """
    out: list[str] = [
        "",
        "## Project Files (always available in your workspace)",
        "Your manager attached the following files to this role. They are "
        "staged fresh at the start of every turn under the relative path "
        "`./project_files/` inside your workspace, so you can open them "
        "with your file-editor or read them via the terminal whenever "
        "their contents are relevant to the user's request. Treat them as "
        "persistent reference material for your role — not as one-shot "
        "attachments — and check them before asking the user for "
        "information they may already contain.",
        "",
    ]
    for meta in files:
        name = (meta or {}).get("name") or ""
        if not name:
            continue
        size = int((meta or {}).get("size") or 0)
        mime = str((meta or {}).get("mime") or "application/octet-stream")
        size_str = _format_size(size)
        out.append(f"- `./project_files/{name}` — {size_str}, {mime}")
    return out


def _format_size(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} B"
    if size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    return f"{size_bytes / (1024 * 1024):.1f} MB"


def runtime(
    repo_dir: str,
    instruction: str,
    mount_dir: str = None,
    event_callback: Callable | None = None,
    use_reflexion: bool | None = None,
    workspace=None,
    session_id: str | None = None,
    employee_profile: dict | None = None,
):
    """
    Run one agent conversation against a DockerWorkspace.

    ``session_id`` (optional): stable chat-session identifier. When supplied
    and reflexion is disabled, subsequent turns reuse the same OpenHands
    conversation so the LLM remembers prior turns. Reflexion retries still
    spin up fresh conversations per trial — that's intentional and matches
    the paper's per-trial isolation.

    ``employee_profile`` (optional): dict with ``name``/``position``/``task``
    fields from the employee record. When supplied, this is rendered as a
    persona block and injected into the agent's system-prompt suffix so the
    LLM sees the employee's identity and standing task on every turn.
    """
    callbacks = [event_callback] if event_callback else []
    if repo_dir:
        Path(repo_dir, "conversations").mkdir(parents=True, exist_ok=True)
        Path(repo_dir, "workspace", "conversations").mkdir(parents=True, exist_ok=True)
    if workspace is not None and hasattr(workspace, "execute_command"):
        try:
            # Run inside the container so the openhands user (UID 10001)
            # can write into the bind-mounted host dir even when the host's
            # WSL2 perms expose it as 0o755 owned by UID 1000. ``sudo`` is
            # available because openhands is in the sudo group; chmod
            # without sudo would fail because the dirs are host-owned.
            workspace.execute_command(
                "sudo mkdir -p /workspace/conversations /workspace/bash_events && "
                "sudo chmod 0777 /workspace /workspace/conversations /workspace/bash_events"
            )
        except Exception:
            logger.debug("Failed to pre-create OpenHands server directories", exc_info=True)

    llm = LLM(model=model, api_key=SecretStr(api_key), base_url=base_url, service_id="agent")
    skills = load_project_skills(work_dir=repo_dir)
    skill_names = sorted(
        str(
            getattr(skill, "name", None)
            or getattr(skill, "id", None)
            or getattr(skill, "slug", None)
            or getattr(skill, "skill_id", None)
            or repr(skill)
        )
        for skill in skills
    )
    logger.info(
        "project_skills_count=%d work_dir=%s project_skills=%s",
        len(skills),
        repo_dir or "(empty)",
        skill_names,
    )
    persona_block = _format_employee_persona(employee_profile)
    # Emit a log regardless of whether a persona was injected so it's easy
    # to tell from server.log which side (frontend payload vs backend
    # assembly) is to blame when the employee identity doesn't show up in
    # the LLM's responses.
    if employee_profile is None:
        logger.info(
            "[persona] No employee_profile supplied by caller — system "
            "prompt will fall back to the OpenHands default identity."
        )
    elif not persona_block:
        logger.info(
            "[persona] employee_profile was supplied but had no usable "
            "fields (keys=%s) — skipping identity override.",
            sorted(employee_profile.keys()),
        )
    else:
        logger.info(
            "[persona] Injecting employee persona into system prompt "
            "(name=%r position=%r task_chars=%d persona_chars=%d)",
            (employee_profile or {}).get("name"),
            (employee_profile or {}).get("position"),
            len((employee_profile or {}).get("task") or ""),
            len(persona_block),
        )

    if persona_block:
        system_suffix = f"{persona_block}\n\n---\n\n{MEMORY_MD_INSTRUCTION}"
    else:
        system_suffix = MEMORY_MD_INSTRUCTION
    agent_context = AgentContext(skills=skills, system_message_suffix=system_suffix)
    use_rx = ENABLE_REFLEXION if use_reflexion is None else use_reflexion
    logger.info(
        "model=%s, base_url=%s, mounted_dir=%s, use_reflexion=%s, injected_workspace=%s",
        model,
        base_url,
        mount_dir,
        use_rx,
        workspace is not None,
    )

    def _run(ws):
        if use_rx:
            return _run_with_reflexion(llm, agent_context, instruction, ws, callbacks=callbacks)
        agent = _create_agent(llm, agent_context)
        return _run_without_reflexion(
            agent, instruction, ws, callbacks=callbacks, session_id=session_id
        )

    if workspace is not None:
        return _run(workspace)

    # CLI fallback: no injected workspace, so own the lifecycle here.
    with build_workspace(mount_host_dir=mount_dir) as owned_ws:
        return _run(owned_ws)



# _extract_trajectory_text and _serialize_trajectory have been moved to
# agent_event_utils.py and are imported at the top of this file.


def _event_to_dict(event) -> dict:
    if isinstance(event, dict):
        return event
    if hasattr(event, "model_dump"):
        try:
            return event.model_dump(mode="json")
        except TypeError:
            return event.model_dump()
    return {}


def _extract_json_text(obj) -> str:
    if obj is None:
        return ""
    if isinstance(obj, str):
        return obj.strip()
    if isinstance(obj, list):
        return "\n".join(filter(None, (_extract_json_text(item) for item in obj))).strip()
    if isinstance(obj, dict):
        if obj.get("type") in {"text", "output_text", "input_text"} and isinstance(obj.get("text"), str):
            return obj["text"].strip()
        for key in ("text", "content", "extended_content", "llm_message", "message", "value"):
            text = _extract_json_text(obj.get(key))
            if text:
                return text
        return "\n".join(
            filter(None, (_extract_json_text(value) for value in obj.values()))
        ).strip()
    text = getattr(obj, "text", None)
    if isinstance(text, str):
        return text.strip()
    content = getattr(obj, "content", None)
    if content is not None:
        return _extract_json_text(content)
    return ""


def _raw_event_role(event: dict) -> str:
    for key in ("role", "source", "sender"):
        value = event.get(key)
        if isinstance(value, str):
            return value.lower()
        if isinstance(value, dict):
            nested = value.get("role") or value.get("value") or value.get("name")
            if isinstance(nested, str):
                return nested.lower()
    message = event.get("message")
    if isinstance(message, dict) and isinstance(message.get("role"), str):
        return message["role"].lower()
    return ""


def _extract_final_answer_from_events(events) -> str:
    for raw in reversed(list(events or [])):
        event = _event_to_dict(raw)
        role = _raw_event_role(event)
        if role in {"user", "system"}:
            continue
        if role and role not in {"assistant", "agent"}:
            continue

        event_type = str(event.get("type") or event.get("kind") or event.get("event_type") or "").lower()
        if event_type and "message" not in event_type and role not in {"assistant", "agent"}:
            continue

        for key in ("extended_content", "llm_message", "content", "message", "data", "payload"):
            text = _extract_json_text(event.get(key))
            if text:
                return text
    return ""


def _fetch_remote_event_items(conversation) -> list[dict]:
    client = getattr(conversation, "_client", None)
    conversation_id = getattr(conversation, "_id", None) or getattr(conversation, "id", None)
    base_path = getattr(conversation, "_conversation_action_base_path", "/api/conversations")
    if not client or not conversation_id:
        return []

    items: list[dict] = []
    page_id = None
    while True:
        params = {"limit": 100}
        if page_id:
            params["page_id"] = page_id
        response = client.get(
            f"{base_path}/{conversation_id}/events/search",
            params=params,
        )
        response.raise_for_status()
        data = response.json()
        page_items = data.get("items", data if isinstance(data, list) else [])
        items.extend(page_items)
        page_id = data.get("next_page_id") if isinstance(data, dict) else None
        if not page_id:
            break
    return items


def _extract_final_answer(conversation) -> str:
    try:
        events_state = getattr(getattr(conversation, "state", None), "events", None)
        if hasattr(events_state, "reconcile"):
            events_state.reconcile()
    except Exception:
        logger.debug("OpenHands event reconciliation failed", exc_info=True)

    try:
        raw_events = _fetch_remote_event_items(conversation)
        answer = _extract_final_answer_from_events(raw_events)
        if answer:
            return answer
    except Exception:
        logger.debug("OpenHands raw event fetch failed", exc_info=True)

    events = getattr(getattr(conversation, "state", None), "events", [])
    return _extract_final_answer_from_events(events)


def _run_without_reflexion(agent, instruction, workspace, callbacks=None, session_id=None):
    """Single attempt, optionally streaming events via callbacks.

    When ``session_id`` is provided, a stable ConversationID is reused across
    turns so the agent-server keeps the prior event log and the LLM sees it
    as context on this turn. ``delete_on_close=False`` prevents the conversation
    from being torn down when this function returns — we want it alive for the
    next turn.
    """
    conversation_id = _conversation_id_for_session(session_id)
    conversation = Conversation(
        agent=agent,
        workspace=workspace,
        callbacks=callbacks or [],
        conversation_id=conversation_id,
        delete_on_close=False,
    )
    if conversation_id is not None:
        logger.info(
            "[session] Attached conversation_id=%s (session=%s)",
            conversation_id, session_id,
        )
    conversation.send_message(instruction)
    conversation.run()
    return _extract_final_answer(conversation)


def _format_numbered_reflections(reflections: list[str]) -> str:
    """Format in-session reflections as numbered trial blocks for prompt injection.

    This is the minimal reflexion pattern from the paper: ordered, per-session
    reflections prepended to the next attempt's prompt.  Each reflection is
    labeled with its trial number so the agent can see how its strategy evolved.
    """
    if not reflections:
        return ""
    numbered = "\n\n".join(
        f"--- Trial {i + 1} ---\n{r}" for i, r in enumerate(reflections)
    )
    return (
        "The following are reflections from your previous attempts in this session. "
        "Use these lessons to avoid repeating the same mistakes:\n\n"
        + numbered
    )


def _run_with_reflexion(llm, agent_context, instruction, workspace, callbacks=None):
    """Reflexion loop: attempt -> evaluate -> reflect -> retry with memory.

    A **fresh** Agent is created for every attempt so that no internal state
    from a prior run (cached tool results, conversation memory, mutable SDK
    fields) can leak into the next attempt and pollute its behaviour.

    Reflections are tracked both:
    - In-session via an ordered list[str] (injected as numbered trials into the
      next attempt prompt — this is the core reflexion mechanism).
    - Persistently via ReflexionMemory (for cross-session retrieval; the memory
      path is read from REFLEXION_MEMORY_PATH or falls back to the package default).
    """
    memory_path = os.getenv("REFLEXION_MEMORY_PATH", "").strip() or None
    if memory_path:
        logger.info("[reflexion] Using REFLEXION_MEMORY_PATH=%s", memory_path)
    else:
        logger.info("[reflexion] REFLEXION_MEMORY_PATH not set — using package default")
    memory = ReflexionMemory(memory_path) if memory_path else ReflexionMemory()

    llm_call = _make_llm_call(llm)
    task_id = str(uuid.uuid4())[:8]

    # In-session ordered reflections — the primary prompt-injection mechanism.
    session_reflections: list[str] = []
    final_answer = ""

    # Also pull any *cross-session* reflections from persistent memory.
    cross_session_context = memory.format_for_prompt(instruction)
    if cross_session_context:
        logger.info(
            "[reflexion] Found cross-session reflections from memory (task=%s)",
            task_id,
        )

    for attempt in range(1, MAX_REFLEXION_ATTEMPTS + 1):
        logger.info("Reflexion attempt %d/%d for task %s", attempt, MAX_REFLEXION_ATTEMPTS, task_id)

        # Fresh agent per attempt — prevents hidden state from leaking across retries.
        agent = _create_agent(llm, agent_context)
        logger.info(
            "[reflexion] Created fresh Agent for attempt %d (task=%s)",
            attempt, task_id,
        )

        # Build the full prompt: numbered in-session reflections (primary)
        # + optional cross-session reflections + original instruction.
        preamble_parts = []
        session_block = _format_numbered_reflections(session_reflections)
        if session_block:
            preamble_parts.append(session_block)
        if cross_session_context:
            preamble_parts.append(cross_session_context)

        if preamble_parts:
            full_instruction = (
                "\n\n---\n\n".join(preamble_parts)
                + "\n\n---\n\nNow, perform the following task:\n"
                + instruction
            )
            logger.debug(
                "[reflexion] Prompt preamble: %d in-session reflections, cross-session=%s (task=%s)",
                len(session_reflections), bool(cross_session_context), task_id,
            )
        else:
            full_instruction = instruction

        # Per-step callback: logs every SDK event with a running step counter.
        step_counter = {"n": 0}
        def _step_logger(event, _attempt=attempt, _task_id=task_id):
            step_counter["n"] += 1
            event_type = type(event).__name__
            summary = ""
            if hasattr(event, "tool_call") and event.tool_call is not None:
                tool = getattr(event, "tool_name", None) or "unknown"
                summary = f" tool={tool}"
            elif hasattr(event, "observation"):
                summary = f" observation_len={len(str(getattr(event, 'observation', '')))}"
            elif hasattr(event, "error"):
                summary = f" error={getattr(event, 'error', '')[:120]}"
            elif hasattr(event, "code") and hasattr(event, "detail"):
                summary = f" code={event.code} detail={str(event.detail)[:120]}"
            logger.info(
                "[step %d/%d] trial=%d event=%s%s (task=%s)",
                step_counter["n"], MAX_ITERATIONS_PER_TRIAL,
                _attempt, event_type, summary, _task_id,
            )

        all_callbacks = list(callbacks or []) + [_step_logger]

        conversation = Conversation(
            agent=agent,
            workspace=workspace,
            callbacks=all_callbacks,
            max_iteration_per_run=MAX_ITERATIONS_PER_TRIAL,
        )
        logger.info(
            "[reflexion] Trial %d: max_iteration_per_run=%d (task=%s)",
            attempt, MAX_ITERATIONS_PER_TRIAL, task_id,
        )
        conversation.send_message(full_instruction)
        conversation.run()
        final_answer = _extract_final_answer(conversation)
        logger.info(
            "[reflexion] Trial %d finished: %d steps used of %d max (task=%s)",
            attempt, step_counter["n"], MAX_ITERATIONS_PER_TRIAL, task_id,
        )

        # Capture the trajectory as a clean, labeled text transcript.
        trajectory = _serialize_trajectory(conversation.state.events)

        # Evaluate the trajectory
        evaluation = evaluate_trajectory(
            task=instruction,
            trajectory=trajectory,
            llm_call=llm_call,
        )
        logger.info(
            "Attempt %d result: success=%s score=%.2f threshold=%.2f task=%s",
            attempt, evaluation.success, evaluation.score, REFLEXION_SCORE_THRESHOLD, task_id,
        )

        # Dual-signal stop condition:
        # 1. Binary flag — judge explicitly marked the task as successful.
        # 2. Score escape hatch — numeric score meets or exceeds our threshold,
        #    even if the binary flag says False (e.g. score=0.85 but success=False).
        score_above_threshold = evaluation.score >= REFLEXION_SCORE_THRESHOLD
        if evaluation.success:
            logger.info(
                "[reflexion gate] Stopping — judge marked success=True "
                "(attempt=%d score=%.2f task=%s)",
                attempt, evaluation.score, task_id,
            )
            break
        if score_above_threshold:
            logger.info(
                "[reflexion gate] Stopping — score %.2f >= threshold %.2f "
                "despite success=False (attempt=%d task=%s)",
                evaluation.score, REFLEXION_SCORE_THRESHOLD, attempt, task_id,
            )
            break

        # If this was the last attempt, log but still generate and store the
        # reflection (useful for cross-session memory even if we won't retry).
        if attempt == MAX_REFLEXION_ATTEMPTS:
            logger.info("Max attempts reached for task %s", task_id)

        # Generate a verbal reflection on the failure.
        # Only the critique (evaluation.summary) is passed — the reflector does
        # not see the numeric score or binary flag (Fix 6).
        reflection = generate_reflection(
            task=instruction,
            trajectory=trajectory,
            critique=evaluation.summary,
            llm_call=llm_call,
        )
        logger.info(
            "[reflexion] Reflection for attempt %d (%d chars): %.200s",
            attempt, len(reflection), reflection,
        )

        # Track in-session for numbered prompt injection on the next attempt.
        session_reflections.append(reflection)

        # Also persist to cross-session memory for future tasks.
        memory.store(
            task_id=f"{task_id}-attempt-{attempt}",
            task_description=instruction,
            reflection=reflection,
            score=evaluation.score,
        )

    return final_answer


def main():
    parser = argparse.ArgumentParser(description="Run OpenHands agent in Docker")
    parser.add_argument("-i", "--instruction", required=True, help="Task instruction for the agent")
    parser.add_argument("-m", "--mount_dir", default="", help="Paths to mount under workspace")
    args = parser.parse_args()
    runtime(repo_dir=args.mount_dir, instruction=args.instruction, mount_dir=args.mount_dir)


if __name__ == "__main__":
    main()
