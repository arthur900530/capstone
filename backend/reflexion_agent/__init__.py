"""
Reflexion — self-improvement framework for the OpenHands agent runtime.

Inspired by the Reflexion paper (Shinn et al., 2023):
  https://arxiv.org/abs/2303.11366

This __init__.py defines the ONLY public surface that external code
should import.  Follow the import discipline:

    ALWAYS:  from reflexion import evaluate_trajectory, generate_reflection, ReflexionMemory
    NEVER:   from reflexion.evaluator import evaluate_trajectory
    NEVER:   import reflexion.memory
"""

from .evaluator import evaluate_trajectory, EvaluationResult
from .reflector import generate_reflection
from .memory import ReflexionMemory

__all__ = [
    "evaluate_trajectory",
    "EvaluationResult",
    "generate_reflection",
    "ReflexionMemory",
]
