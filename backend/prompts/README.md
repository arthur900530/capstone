# Trajectory annotation prompts

These prompts mirror the `profiling/prompts/` directory of
[zorazrw/ai4work-resources](https://github.com/zorazrw/ai4work-resources/tree/main/profiling/prompts)
and are used by `backend/trajectory_llm.py` to post-process a segmented
trajectory tree into an "induced workflow" view.

- `get_node_goal.txt` — summarize a sequence node's subgoals into a single goal
- `get_node_status.txt` — judge whether the action sequence achieves the goal
