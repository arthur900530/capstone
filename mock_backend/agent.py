import argparse
import os
import platform
import socket
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
from openhands.tools.file_editor import FileEditorTool
from openhands.tools.task_tracker import TaskTrackerTool
from openhands.tools.terminal import TerminalTool
from openhands.workspace import DockerWorkspace

from reflexion import evaluate_trajectory, generate_reflection, ReflexionMemory


# Reflexion configuration (read from .env, disabled by default)
ENABLE_REFLEXION = False
MAX_REFLEXION_ATTEMPTS = 3

logger = logging.getLogger(__name__)


dotenv.load_dotenv()
base_url = os.getenv("BASE_URL")
api_key = os.getenv("API_KEY")
model = os.getenv("MODEL")


def _detect_platform():
    m = platform.machine().lower()
    return "linux/arm64" if "arm" in m or "aarch64" in m else "linux/amd64"


def _find_port(start=8010):
    port = start
    while True:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("localhost", port)) != 0:
                return port
        port += 1
        

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


def runtime(
    repo_dir: str,
    instruction: str,
    mount_dir: str = None,
    event_callback: Callable | None = None,
):
    if mount_dir:
        abs_mount = str(Path(mount_dir).resolve())
        volumes = [f"{abs_mount}:/workspace:rw"]
    else:
        volumes = []

    callbacks = [event_callback] if event_callback else []

    llm = LLM(model=model, api_key=SecretStr(api_key), base_url=base_url, service_id="agent")
    skills = load_project_skills(work_dir=repo_dir)
    agent_context = AgentContext(skills=skills)
    agent = Agent(
        llm=llm,
        tools=[
            Tool(name="terminal"),
            Tool(name="file_editor"),
            Tool(name="task_tracker"),
        ],
        agent_context=agent_context,
    )
    logger.info("model=%s, base_url=%s, mounted_dir=%s", model, base_url, mount_dir)
    with DockerWorkspace(
        server_image="ghcr.io/openhands/agent-server:latest-python",
        host_port=_find_port(),
        platform=_detect_platform(),
        volumes=volumes,
    ) as workspace:
        if ENABLE_REFLEXION:
            _run_with_reflexion(agent, llm, instruction, workspace, callbacks=callbacks)
        else:
            _run_without_reflexion(agent, instruction, workspace, callbacks=callbacks)


def _run_without_reflexion(agent, instruction, workspace, callbacks=None):
    """Single attempt, optionally streaming events via callbacks."""
    conversation = Conversation(agent=agent, workspace=workspace, callbacks=callbacks or [])
    conversation.send_message(instruction)
    conversation.run()

    conversation.send_message("According to the history of this task, summarize the preferences of the user, or key memories, and save them in AGENT.md and MEMORY.md.")
    conversation.run()


def _run_with_reflexion(agent, llm, instruction, workspace, callbacks=None):
    """Reflexion loop: attempt -> evaluate -> reflect -> retry with memory."""
    MEMORY_PATH = "reflexion_memory.json"
    memory = ReflexionMemory(MEMORY_PATH) if MEMORY_PATH else ReflexionMemory()
    llm_call = _make_llm_call(llm)
    task_id = str(uuid.uuid4())[:8]

    # Check if we have relevant past reflections to inject
    past_context = memory.format_for_prompt(instruction)

    for attempt in range(1, MAX_REFLEXION_ATTEMPTS + 1):
        logger.info("Reflexion attempt %d/%d for task %s", attempt, MAX_REFLEXION_ATTEMPTS, task_id)

        # Build the full prompt: original instruction + any past reflections
        full_instruction = instruction
        if past_context:
            full_instruction = past_context + "\n\n---\n\nNow, perform the following task:\n" + instruction

        conversation = Conversation(agent=agent, workspace=workspace, callbacks=callbacks or [])
        conversation.send_message(full_instruction)
        conversation.run()

        # Capture the trajectory as a string (event log)
        trajectory = str(list(conversation.state.events))

        # Evaluate the trajectory
        evaluation = evaluate_trajectory(
            task=instruction,
            trajectory=trajectory,
            llm_call=llm_call,
        )
        logger.info(
            "Attempt %d result: success=%s score=%.2f",
            attempt, evaluation.success, evaluation.score,
        )

        # If the task succeeded, we're done
        if evaluation.success:
            logger.info("Task succeeded on attempt %d", attempt)
            break

        # If this was the last attempt, store the reflection but don't retry
        if attempt == MAX_REFLEXION_ATTEMPTS:
            logger.info("Max attempts reached for task %s", task_id)

        # Generate a verbal reflection on the failure
        reflection = generate_reflection(
            task=instruction,
            trajectory=trajectory,
            evaluation=evaluation,
            llm_call=llm_call,
        )

        # Store the reflection in episodic memory for future use
        memory.store(
            task_id=f"{task_id}-attempt-{attempt}",
            task_description=instruction,
            reflection=reflection,
            score=evaluation.score,
        )

        # Update the context for the next attempt
        past_context = memory.format_for_prompt(instruction)


def main():
    parser = argparse.ArgumentParser(description="Run OpenHands agent in Docker")
    parser.add_argument("-i", "--instruction", required=True, help="Task instruction for the agent")
    parser.add_argument("-m", "--mount_dir", default="", help="Paths to mount under workspace")
    args = parser.parse_args()
    runtime(repo_dir=args.mount_dir, instruction=args.instruction, mount_dir=args.mount_dir)


if __name__ == "__main__":
    main()