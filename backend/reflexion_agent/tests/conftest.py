"""
conftest.py — pytest configuration that runs BEFORE any test module imports.

Problem: agent.py imports heavy SDK modules (openhands.workspace) and a local
config module (config.py) at the top level.  These are unavailable in the
test environment because:
  - openhands.workspace is not part of the installed SDK version
  - config.py contains secrets and is gitignored (only config.py.example exists)

Solution: Inject lightweight fake modules into sys.modules so Python's import
machinery finds them and never tries to locate the real packages.  This lets
us import _parse_score_threshold, _serialize_trajectory, and other pure
functions from agent.py without pulling in Docker or API keys.

This file MUST live in the tests/ directory (or a parent conftest) so pytest
loads it before collecting test_reflexion_fixes.py.
"""

import sys
import types


def _create_stub_module(name, **attrs):
    """Create a fake module with the given attributes and register it in sys.modules."""
    mod = types.ModuleType(name)
    for key, value in attrs.items():
        setattr(mod, key, value)
    sys.modules[name] = mod
    return mod


def _ensure_stubs():
    """Register all stub modules needed by agent.py's top-level imports."""

    # ── openhands.sdk.workspace.local (may fail in minimal environments) ─
    # agent.py does: from openhands.sdk.workspace import LocalWorkspace
    # If the SDK workspace sub-package isn't fully importable, stub it.
    try:
        from openhands.sdk.workspace import LocalWorkspace  # noqa: F401
    except (ImportError, ModuleNotFoundError):
        if "openhands.sdk.workspace" not in sys.modules:
            _create_stub_module("openhands.sdk.workspace", LocalWorkspace=None)

    # ── config (local secrets file, gitignored) ────────────────────────
    # agent.py does: from config import BASE_URL, API_KEY, AGENT_MODEL
    if "config" not in sys.modules:
        _create_stub_module(
            "config",
            BASE_URL="http://fake-test-url",
            API_KEY="fake-test-key",
            AGENT_MODEL="fake-model",
            SKILL_MODEL="fake-skill-model",
        )


# Run stubs immediately when conftest is loaded (before test collection)
_ensure_stubs()
