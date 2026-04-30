import base64
import json
import mimetypes
import os
import re
import subprocess
import tempfile

import openai

from typing import *
from pathlib import Path
from .prompts import MMSkillTrainer_PROMPT_TEMPLATE
from workflow import Workflow, save_workflow
import config


def _config_value(name: str, default: str = "") -> str:
    value = os.getenv(name)
    if value is not None:
        return value
    return getattr(config, name, default)


def _openrouter_api_key() -> str:
    key = _config_value("OPENROUTER_API_KEY") or _config_value("SKILL_API_KEY")
    if key:
        return key

    # Backward compatibility for the original all-OpenRouter config.py.
    base_url = getattr(config, "BASE_URL", "")
    if "openrouter.ai" in base_url:
        return getattr(config, "API_KEY", "")
    return ""


MODEL_NAME = (
    _config_value("OPENROUTER_SKILL_MODEL")
    or _config_value("SKILL_MODEL", "google/gemini-2.5-flash")
)
SKILL_BASE_URL = (
    _config_value("OPENROUTER_BASE_URL")
    or _config_value("SKILL_BASE_URL")
    or "https://openrouter.ai/api/v1"
)
SKILL_API_KEY = _openrouter_api_key()

client = openai.OpenAI(base_url=SKILL_BASE_URL, api_key=SKILL_API_KEY)


class MMSkillTrainer:
    skill_base_dir: Path = Path(__file__).resolve().parent.parent / "skills"
    skill_base_dir.mkdir(parents=True, exist_ok=True)

    def __init__(self) -> None:
        # Workflows recorded by the LLM via the ``record_workflow`` tool,
        # keyed by the (raw, un-normalized) skill_name argument the model
        # supplied. They are paired with parsed skills at the end of
        # training so the saved ``workflow.json`` matches the saved
        # ``SKILL.md``'s slug.
        self._workflows: dict[str, Workflow] = {}
        # Original (pre-compression) basenames of inputs, for the LLM to
        # reference when filling ``source_file`` in record_workflow calls.
        self._original_basenames: list[str] = []
        # Basenames that have already been bound to a workflow. Used by
        # ``_resolve_source_file`` to round-robin un-claimed files when
        # the model omits or garbles ``source_file`` in multi-file uploads.
        self._claimed_basenames: set[str] = set()

    def _save_skill(self, skill_name: str, skill_description: str):
        skill_file_path = self.skill_base_dir / skill_name / "SKILL.md"
        skill_file_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(skill_file_path, "w") as f:
            f.write(f"{skill_description}\n")
            
        print(f"[MMTrainer] Saved skill {skill_name} to {skill_file_path}")
        
    # Python's mimetypes maps .mov to video/quicktime, but OpenRouter
    # expects video/mov per their supported formats list.
    _MIME_OVERRIDES: dict[str, str] = {
        "video/quicktime": "video/mov",
    }

    @staticmethod
    def _compress_video(file_path: str) -> str:
        """Compress a video to mp4 to stay within API payload limits.

        Returns the path to a temporary compressed file. The caller is
        responsible for cleaning it up.
        """
        tmp = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
        tmp.close()
        print(f"[MMTrainer] Compressing video {file_path} -> {tmp.name}")
        subprocess.run(
            [
                "ffmpeg", "-y", "-i", file_path,
                "-c:v", "libx264", "-crf", "28", "-preset", "fast",
                "-c:a", "aac", "-b:a", "64k",
                tmp.name,
            ],
            check=True,
            capture_output=True,
        )
        orig = os.path.getsize(file_path)
        compressed = os.path.getsize(tmp.name)
        print(f"[MMTrainer] Compressed {orig // 1024}KB -> {compressed // 1024}KB")
        return tmp.name

    @staticmethod
    def _compress_audio(file_path: str) -> str:
        """Compress audio to mp3 to stay within API payload limits.

        Returns the path to a temporary compressed file. The caller is
        responsible for cleaning it up.
        """
        tmp = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
        tmp.close()
        print(f"[MMTrainer] Compressing audio {file_path} -> {tmp.name}")
        subprocess.run(
            [
                "ffmpeg", "-y", "-i", file_path,
                "-c:a", "libmp3lame", "-b:a", "64k",
                tmp.name,
            ],
            check=True,
            capture_output=True,
        )
        orig = os.path.getsize(file_path)
        compressed = os.path.getsize(tmp.name)
        print(f"[MMTrainer] Compressed {orig // 1024}KB -> {compressed // 1024}KB")
        return tmp.name

    @staticmethod
    def _encode_media(file_path: str) -> tuple[str, str]:
        """Read a media file and return its base64 encoding and MIME type."""
        mime_type, _ = mimetypes.guess_type(file_path)
        if mime_type is None:
            raise ValueError(f"Could not determine MIME type for {file_path}")
        mime_type = MMSkillTrainer._MIME_OVERRIDES.get(mime_type, mime_type)
        with open(file_path, "rb") as f:
            data = base64.b64encode(f.read()).decode("utf-8")
        return data, mime_type

    @staticmethod
    def _prepare_file(file_path: str) -> tuple[str, str | None]:
        """Compress if needed and return (usable_path, temp_path_or_None)."""
        mime_type, _ = mimetypes.guess_type(file_path)
        if mime_type and mime_type.startswith("video/"):
            compressed = MMSkillTrainer._compress_video(file_path)
            return compressed, compressed
        if mime_type and mime_type.startswith("audio/"):
            compressed = MMSkillTrainer._compress_audio(file_path)
            return compressed, compressed
        return file_path, None

    def train(self, input_file_paths: str | list[str]) -> dict:
        """Run the multimodal skill ingestor.

        Returns a dict ``{"skills": [slug, ...], "workflows": {slug: workflow_dict}}``
        capturing the new skills written to disk and any workflows the LLM
        recorded via the ``record_workflow`` tool. Callers (the train route
        handler) merge this into the HTTP response so the frontend can
        render the post-train video / workflow review.
        """
        if isinstance(input_file_paths, str):
            input_file_paths = [input_file_paths]

        # Snapshot original filenames before compression substitutes them.
        self._original_basenames = [os.path.basename(p) for p in input_file_paths]
        self._claimed_basenames = set()
        self._saved_slugs: list[str] = []
        self._saved_workflows: dict[str, dict] = {}

        prepared: list[tuple[str, str | None]] = []
        try:
            for path in input_file_paths:
                prepared.append(self._prepare_file(path))
            self._train_impl([p for p, _ in prepared])
        finally:
            for _, tmp in prepared:
                if tmp:
                    os.unlink(tmp)

        return {
            "skills": list(self._saved_slugs),
            "workflows": dict(self._saved_workflows),
        }

    @staticmethod
    def _build_media_part(data: str, mime_type: str) -> dict:
        """Build the correct OpenRouter content part for the media type.

        Video uses ``video_url`` with a data-URL.
        Audio uses ``input_audio`` with raw base64 + format.
        Docs: https://openrouter.ai/docs/features/multimodal/
        """
        if mime_type.startswith("video/"):
            return {
                "type": "video_url",
                "video_url": {"url": f"data:{mime_type};base64,{data}"},
            }
        if mime_type.startswith("audio/"):
            # Extract format from mime type (e.g. "audio/mp3" -> "mp3")
            audio_fmt = mime_type.split("/", 1)[1]
            return {
                "type": "input_audio",
                "input_audio": {"data": data, "format": audio_fmt},
            }
        raise ValueError(f"Unsupported media type: {mime_type}")

    @staticmethod
    def _is_text_file(file_path: str) -> bool:
        mime_type, _ = mimetypes.guess_type(file_path)
        return mime_type is not None and mime_type.startswith("text/")

    @staticmethod
    def _read_text_file(file_path: str) -> dict:
        with open(file_path, "r") as f:
            content = f.read()
        filename = os.path.basename(file_path)
        return {"type": "text", "text": f"[File: {filename}]\n{content}"}

    _STEP_SCHEMA: dict = {
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "Short label of the step."},
            "description": {
                "type": "string",
                "description": "Longer detail of what happens during this step.",
            },
            "start_time": {
                "type": "number",
                "description": "Start of the step in the source video, in seconds.",
            },
            "end_time": {
                "type": "number",
                "description": "End of the step in the source video, in seconds.",
            },
            "children": {
                "type": "array",
                "description": "Optional nested sub-steps.",
                "items": {"type": "object"},
            },
        },
        "required": ["title"],
    }

    _TOOLS = [
        {
            "type": "function",
            "function": {
                "name": "list_skills",
                "description": "List the names of all existing skills.",
                "parameters": {"type": "object", "properties": {}, "required": []},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "read_skill",
                "description": "Read the full content of a specific skill file.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "skill_name": {
                            "type": "string",
                            "description": "The name of the skill to read.",
                        },
                    },
                    "required": ["skill_name"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "record_workflow",
                "description": (
                    "Record the structured workflow + per-step video timestamps for "
                    "one identified skill. Call once per skill BEFORE returning the "
                    "<skill_name> / <skill_description> blocks. Use the same "
                    "skill_name string here that you will use inside <skill_name>."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "skill_name": {
                            "type": "string",
                            "description": "Skill name (matches the <skill_name> XML block).",
                        },
                        "title": {
                            "type": "string",
                            "description": "Human-readable title for the workflow.",
                        },
                        "summary": {
                            "type": "string",
                            "description": "1-2 sentence summary of what the workflow accomplishes.",
                        },
                        "source_file": {
                            "type": "string",
                            "description": (
                                "EXACT original uploaded filename (verbatim, including "
                                "extension, with no extra characters or timestamps "
                                "appended) that this workflow's steps were observed in. "
                                "Must match one of the filenames listed in the user "
                                "message. Required so the frontend can pair the "
                                "workflow with the right source video."
                            ),
                        },
                        "steps": {
                            "type": "array",
                            "description": (
                                "Ordered list of root-level workflow steps. Each step "
                                "may contain nested children for sub-steps."
                            ),
                            "items": _STEP_SCHEMA,
                        },
                    },
                    "required": ["skill_name", "title", "source_file", "steps"],
                },
            },
        },
    ]

    def _dispatch_tool(self, name: str, args: dict) -> str:
        if name == "list_skills":
            return json.dumps(_list_skills())
        if name == "read_skill":
            return _read_skill(args.get("skill_name", ""))
        if name == "record_workflow":
            return self._handle_record_workflow(args)
        return f"Unknown tool: {name}"

    @staticmethod
    def _normalize_basename(value: str | None) -> str:
        """Lower-case basename with trailing timestamp-ish noise stripped.

        Models occasionally append things like ``00:00`` or ``_t=12.3`` to a
        filename ("foo.mp400:00"). We tolerate that by trimming everything
        after the first known media extension.
        """

        if not value:
            return ""
        name = os.path.basename(str(value)).strip().lower()
        # If a recognizable extension appears in the middle, cut at its end.
        match = re.search(
            r"\.(mp4|mov|webm|m4v|avi|mp3|wav|m4a|txt|md|py|sh|json|yaml|yml|csv)",
            name,
        )
        if match:
            name = name[: match.end()]
        return name

    def _resolve_source_file(self, raw: str | None) -> str | None:
        """Pair a model-supplied ``source_file`` with an uploaded basename.

        Tries (in order):
          1. exact match against an original basename,
          2. case-insensitive / extension-trimmed match,
          3. the next un-claimed original basename (round-robin), so a 2-
             video upload yields one workflow per video by default.

        Returns ``None`` only when no files were uploaded.
        """

        if not self._original_basenames:
            return None

        if raw:
            raw_str = str(raw).strip()
            for name in self._original_basenames:
                if name == raw_str:
                    self._claimed_basenames.add(name)
                    return name
            raw_norm = self._normalize_basename(raw_str)
            if raw_norm:
                for name in self._original_basenames:
                    if self._normalize_basename(name) == raw_norm:
                        self._claimed_basenames.add(name)
                        return name

        for name in self._original_basenames:
            if name not in self._claimed_basenames:
                self._claimed_basenames.add(name)
                return name

        return self._original_basenames[0]

    def _handle_record_workflow(self, args: dict) -> str:
        try:
            workflow = Workflow.from_tool_args(**args)
        except Exception as exc:
            return f"Failed to record workflow: {exc}"

        # Normalize ``source_file`` against the actually-uploaded basenames
        # so the frontend can pair each workflow with its source video. The
        # model is asked to return the filename verbatim, but in practice
        # it sometimes:
        #   * omits the field entirely (single-file uploads used to rely
        #     on a one-shot fallback that broke with N>1 files),
        #   * tacks a timestamp onto the extension (e.g. ``foo.mp400:00``),
        #   * returns a different case or includes a path prefix.
        # A strict ``files.find(name === source_file)`` then misses, and
        # the frontend collapses every workflow onto the first video.
        resolved = self._resolve_source_file(workflow.source_file)
        if resolved is not None:
            workflow.source_file = resolved
        else:
            workflow.source_file = None

        self._workflows[workflow.skill_name] = workflow
        leaf_count = sum(1 for _ in _iter_workflow_leaves(workflow.root_steps))
        print(
            f"[MMTrainer] Recorded workflow for '{workflow.skill_name}' "
            f"({len(workflow.root_steps)} root steps, {leaf_count} leaves)"
        )
        return json.dumps(
            {
                "ok": True,
                "skill_name": workflow.skill_name,
                "step_count": len(workflow.root_steps),
                "leaf_count": leaf_count,
            }
        )

    def _train_impl(self, input_file_paths: list[str]):
        if not SKILL_API_KEY:
            raise RuntimeError(
                "OpenRouter API key is required for skill training. Set "
                "OPENROUTER_API_KEY or SKILL_API_KEY in backend/config.py or "
                "your environment."
            )

        content_parts: list[dict] = []
        for path in input_file_paths:
            if self._is_text_file(path):
                content_parts.append(self._read_text_file(path))
            else:
                data, mime_type = self._encode_media(path)
                content_parts.append(self._build_media_part(data, mime_type))

        # Surface the original filenames to the model so it can populate
        # ``source_file`` on record_workflow tool calls. This matters most
        # for multi-file uploads, where the frontend uses ``source_file``
        # to pair each extracted workflow with its source video.
        intro_lines = ["Please analyze this media and extract skills from it."]
        if self._original_basenames:
            quoted = ", ".join(f'"{b}"' for b in self._original_basenames)
            intro_lines.append(
                "Uploaded files: " + quoted + ". When you call record_workflow you "
                "MUST set source_file to one of these filenames EXACTLY (no "
                "trailing timestamps, no path prefix, no case changes). Each "
                "workflow must reference the file it was demonstrated in; do "
                "not reuse the same source_file for unrelated skills."
            )

        messages: list[dict] = [
            {"role": "system", "content": MMSkillTrainer_PROMPT_TEMPLATE},
            {"role": "user", "content": [
                {"type": "text", "text": "\n".join(intro_lines)},
                *content_parts,
            ]},
        ]

        print(f"[MMTrainer] Sending request to API to train the skill ({len(content_parts)} file(s))")
        while True:
            response = client.chat.completions.create(
                model=MODEL_NAME,
                messages=messages,
                tools=self._TOOLS,
            )
            if not response.choices:
                raise RuntimeError(
                    f"API returned no choices. Full response: {response.model_dump_json(indent=2)}"
                )

            choice = response.choices[0]
            if choice.finish_reason != "tool_calls":
                break

            messages.append({
                "role": "assistant",
                "content": choice.message.content or "",
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in choice.message.tool_calls
                ],
            })
            for tool_call in choice.message.tool_calls:
                fn_name = tool_call.function.name
                try:
                    fn_args = json.loads(tool_call.function.arguments or "{}")
                except json.JSONDecodeError:
                    fn_args = {}
                preview = {k: v for k, v in fn_args.items() if k != "steps"}
                if "steps" in fn_args:
                    preview["steps"] = f"[{len(fn_args.get('steps') or [])} steps]"
                print(f"[MMTrainer] Tool call: {fn_name}({preview})")
                result = self._dispatch_tool(fn_name, fn_args)
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": result,
                })

        # ``content`` is None when the model finishes a turn with only tool
        # calls (no assistant text) — coerce to "" so the regex parsing
        # below doesn't blow up with "expected string or bytes-like
        # object, got 'NoneType'".
        output = choice.message.content or ""
        print(f"[MMTrainer] Response: {output!r}")

        # Parse the output into skills using regex for robustness
        skill_names = []
        skill_descriptions = []

        name_pattern = re.compile(r"<skill_name>\s*(.*?)\s*</skill_name>", re.DOTALL)
        desc_pattern = re.compile(r"<skill_description>\s*(.*?)\s*</skill_description>", re.DOTALL)

        names_found = name_pattern.findall(output)
        descs_found = desc_pattern.findall(output)

        if not names_found:
            print(
                "[MMTrainer] WARNING: No <skill_name> tags found in LLM response. "
                f"finish_reason={choice.finish_reason!r}, recorded_workflows="
                f"{list(self._workflows.keys())}, raw output:\n{output}"
            )
            return
        
        if len(names_found) != len(descs_found):
            print(f"[MMTrainer] WARNING: Found {len(names_found)} skill names but {len(descs_found)} descriptions. Pairing what we can.")
        
        for i, name in enumerate(names_found):
            clean_name = re.sub(r"[^a-z0-9-]", "", name.lower().strip())[:60].rstrip("-")
            if not clean_name:
                print(f"[MMTrainer] WARNING: Skipping skill with empty name (raw: '{name}')")
                continue
            desc = descs_found[i] if i < len(descs_found) else f"# {name}\n\n(No description extracted)"
            skill_names.append(clean_name)
            skill_descriptions.append(desc)
        
        # Save results, pairing each skill with the workflow the LLM
        # recorded via record_workflow. The model is instructed to use the
        # same skill_name string in both places, but be defensive about
        # case / whitespace mismatches by also matching against the cleaned
        # slug.
        raw_skill_keys = list(names_found)
        for raw_name, clean_name, description in zip(
            raw_skill_keys, skill_names, skill_descriptions
        ):
            self._save_skill(clean_name, description)
            self._saved_slugs.append(clean_name)

            workflow = self._workflows.get(raw_name) or self._workflows.get(
                clean_name
            )
            if workflow is None:
                stripped = raw_name.strip()
                if stripped and stripped in self._workflows:
                    workflow = self._workflows[stripped]
            if workflow is not None:
                workflow.skill_name = clean_name
                save_workflow(clean_name, workflow)
                self._saved_workflows[clean_name] = workflow.to_dict()
                print(
                    f"[MMTrainer] Saved workflow.json for {clean_name}"
                )
            else:
                print(
                    f"[MMTrainer] WARNING: No workflow recorded for skill '{clean_name}'"
                )
        

def _iter_workflow_leaves(steps: Iterable) -> Iterable:
    for step in steps or []:
        children = list(step.children) if hasattr(step, "children") else []
        if not children:
            yield step
        else:
            yield from _iter_workflow_leaves(children)


def _skills_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "skills"


def _list_skills() -> list[str]:
    """Return sorted skill directory names."""
    sd = _skills_dir()
    if not sd.exists():
        return []
    return sorted(d.name for d in sd.iterdir() if d.is_dir())


def _read_skill(skill_name: str) -> str:
    """Read and return the contents of a skill's SKILL.md."""
    if not skill_name:
        return ""
    skill_path = _skills_dir() / skill_name / "SKILL.md"
    if not skill_path.exists():
        return f"Skill file not found: {skill_path}"
    return skill_path.read_text()


def _train_from_upload(files) -> str:
    """Handle file upload(s) from the Gradio UI and run training."""
    if not files:
        return "No file uploaded."
    if isinstance(files, str):
        files = [files]
    trainer = MMSkillTrainer()
    try:
        trainer.train(files)
        return "Training complete! New skills saved. Refresh the skill list to see them."
    except Exception as e:
        return f"Error during training:\n{e}"
