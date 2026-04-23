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
    """Find a host port we can actually bind on 127.0.0.1.

    We test by binding (with SO_REUSEADDR off) rather than ``connect_ex``:
    ``connect_ex`` only detects "someone is listening", but Docker needs the
    port to be free to bind — which also excludes ports held by zombie
    containers, ports reserved by the OS, and ports bound on different
    interfaces. Matching DockerWorkspace's own check avoids races where we
    pick a port it then rejects.
    """
    for port in range(start, end):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(("127.0.0.1", port))
                return port
        except OSError:
            continue
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
            # OpenHands SDK's _wait_for_health uses a 120s default; there is
            # no `health_check_timeout` attribute on DockerWorkspace in v1.15+.
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
        Path(abs_mount, "conversations").mkdir(parents=True, exist_ok=True)
        Path(abs_mount, "bash_events").mkdir(parents=True, exist_ok=True)
        volumes = [f"{abs_mount}:/workspace:rw"]
    else:
        volumes = []
    os.environ.setdefault("OH_CONVERSATIONS_PATH", "/workspace/conversations")
    os.environ.setdefault("OH_BASH_EVENTS_DIR", "/workspace/bash_events")
    return BrowserDockerWorkspace(
        server_image="ghcr.io/openhands/agent-server:latest-python",
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


def runtime(
    repo_dir: str,
    instruction: str,
    mount_dir: str = None,
    event_callback: Callable | None = None,
    use_reflexion: bool | None = None,
    workspace=None,
    session_id: str | None = None,
):
    """
    Run one agent conversation against a DockerWorkspace.

    ``session_id`` (optional): stable chat-session identifier. When supplied
    and reflexion is disabled, subsequent turns reuse the same OpenHands
    conversation so the LLM remembers prior turns. Reflexion retries still
    spin up fresh conversations per trial — that's intentional and matches
    the paper's per-trial isolation.
    """
    callbacks = [event_callback] if event_callback else []
    if repo_dir:
        Path(repo_dir, "conversations").mkdir(parents=True, exist_ok=True)
        Path(repo_dir, "workspace", "conversations").mkdir(parents=True, exist_ok=True)
    if workspace is not None and hasattr(workspace, "execute_command"):
        try:
            workspace.execute_command("mkdir -p /workspace/conversations /workspace/bash_events")
        except Exception:
            logger.debug("Failed to pre-create OpenHands server directories", exc_info=True)

    llm = LLM(model=model, api_key=SecretStr(api_key), base_url=base_url, service_id="agent")
    skills = load_project_skills(work_dir=repo_dir)
    logger.info(
        "project_skills_count=%d work_dir=%s",
        len(skills),
        repo_dir or "(empty)",
    )
    agent_context = AgentContext(skills=skills, system_message_suffix=MEMORY_MD_INSTRUCTION)
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


def _extract_trajectory_text(obj) -> str:
    """Extract plain text from whatever the SDK puts in a content field.

    Handles: str, a single TextContent-like object (.text), a list of them,
    and arbitrary objects (fallback to empty string rather than crashing).
    This is a local mirror of server.py's _extract_text so agent.py has no
    import dependency on server.py.
    """
    if obj is None:
        return ""
    if isinstance(obj, str):
        return obj
    if hasattr(obj, "text") and isinstance(getattr(obj, "text"), str):
        return obj.text
    if isinstance(obj, (list, tuple)):
        parts = []
        for item in obj:
            if hasattr(item, "text") and isinstance(getattr(item, "text"), str):
                parts.append(item.text)
            elif isinstance(item, str):
                parts.append(item)
        return " ".join(parts)
    return ""


def _serialize_trajectory(events) -> str:
    """Convert OpenHands event objects into a clean, labeled text transcript.

    Replaces the raw Python repr dump — str(list(events)) — with a
    human-readable log that the LLM judge can evaluate reliably.

    Design principles
    -----------------
    - Pure function: events in → string out.  Both the evaluator and the
      reflector receive this same string; neither module needs to change.
    - Defensive: every attribute access uses getattr so an unexpected SDK
      event type never crashes the loop — it just increments the 'other'
      counter and is skipped silently.
    - Dual-attribute checks: the SDK has evolved (e.g. 'action' → 'tool_call',
      'result' → 'observation'), so we check both names for each event type.

    Event type detection (duck typing, no SDK class imports needed)
    ---------------------------------------------------------------
    MessageEvent   → has a non-None 'role' attribute
    ActionEvent    → has 'tool_call' or 'action' (older SDK) attribute
    ObservationEvent → has 'observation' or 'result' (older SDK) attribute
    Error events   → has 'error' or 'message' attribute
    """
    lines = []
    turn = 0
    counts = {"message": 0, "action": 0, "observation": 0, "error": 0, "other": 0}

    for event in events:

        # ── MessageEvent ──────────────────────────────────────────────
        role = getattr(event, "role", None)
        if role is not None:
            text = _extract_trajectory_text(getattr(event, "extended_content", None))
            if not text:
                text = getattr(event, "reasoning_content", None) or ""
            if not text:
                text = _extract_trajectory_text(getattr(event, "content", None))
            if text:
                lines.append(f"[{str(role).upper()}] {text.strip()}")
            counts["message"] += 1
            continue

        # ── ActionEvent (tool call) ───────────────────────────────────
        tool_call = getattr(event, "tool_call", None)
        action_attr = getattr(event, "action", None)  # older SDK fallback

        if tool_call is not None or action_attr is not None:
            turn += 1
            tool_name = (
                getattr(event, "tool_name", None)
                or getattr(event, "tool", None)
                or "unknown"
            )
            lines.append(f"[Turn {turn}] [ACTION] {tool_name}")

            # Parse structured args from the tool_call (current SDK)
            if tool_call is not None:
                fn = getattr(tool_call, "function", None)
                args_str = (getattr(fn, "arguments", None) or "") if fn else ""
                try:
                    args_dict = json.loads(args_str) if args_str else {}
                except (json.JSONDecodeError, TypeError):
                    args_dict = {}
                if args_dict:
                    args_display = ", ".join(
                        f"{k}={repr(str(v))[:80]}" for k, v in args_dict.items()
                    )
                    lines.append(f"  Arguments: {args_display}")
                elif args_str:
                    lines.append(f"  Arguments: {args_str[:300]}")
            else:
                # Older SDK: action is an object like BashAction(command='ls -la')
                lines.append(f"  Arguments: {str(action_attr)[:300]}")

            # Capture any reasoning the agent attached to this action
            thought = _extract_trajectory_text(getattr(event, "thought", None))
            if not thought:
                thought = getattr(event, "reasoning_content", None) or ""
            if thought:
                lines.append(f"  [Agent reasoning] {thought.strip()[:400]}")

            counts["action"] += 1
            continue

        # ── ObservationEvent (tool result) ────────────────────────────
        observation = getattr(event, "observation", None)
        result_attr = getattr(event, "result", None)  # older SDK fallback

        if observation is not None or result_attr is not None:
            tool_name = getattr(event, "tool_name", None) or ""

            if observation is not None:
                raw = (
                    getattr(observation, "content", None)
                    or getattr(observation, "text", None)
                )
                content = _extract_trajectory_text(raw) or str(observation)
            else:
                content = _extract_trajectory_text(result_attr) or str(result_attr)

            content = content.strip()
            # Truncate long outputs (e.g. full file contents) to stay readable
            if len(content) > 800:
                content = content[:800] + f"\n  ... [{len(content) - 800} chars truncated]"

            prefix = f"[OBSERVATION] {tool_name}: " if tool_name else "[OBSERVATION] "
            lines.append(f"{prefix}{content}")
            counts["observation"] += 1
            continue

        # ── Error events ──────────────────────────────────────────────
        error_msg = getattr(event, "error", None) or getattr(event, "message", None)
        if error_msg:
            lines.append(f"[ERROR] {str(error_msg)[:400]}")
            counts["error"] += 1
            continue

        counts["other"] += 1

    total = sum(counts.values())
    logger.info(
        "[trajectory] Serialized %d events — message=%d action=%d observation=%d error=%d other=%d",
        total,
        counts["message"],
        counts["action"],
        counts["observation"],
        counts["error"],
        counts["other"],
    )

    if not lines:
        logger.warning(
            "[trajectory] No serializable events found after processing %d raw events — "
            "returning placeholder",
            total,
        )
        return "[trajectory: no events captured]"

    return "\n".join(lines)


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
