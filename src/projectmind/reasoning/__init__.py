"""Auditable reasoning helpers that never persist private chain-of-thought."""

from projectmind.reasoning.confidence import confidence_score
from projectmind.reasoning.devils_advocate import (
    CounterArgument,
    DevilsAdvocateResult,
    play_devils_advocate,
)
from projectmind.reasoning.post_mortem import PostMortemResult, record_learning
from projectmind.reasoning.react_loop import ReActLoop, react_step
from projectmind.reasoning.self_critique import (
    PERSPECTIVES,
    SelfCritiqueEngine,
    critique_code_change,
    critique_plan,
    self_reflect,
)
from projectmind.reasoning.sequential_thinking import (
    SequentialThinkingEngine,
    sequential_think,
    validate_step,
)
from projectmind.reasoning.similar_solutions import (
    MemoryStoreSolutionAdapter,
    SimilarSolution,
    SimilarSolutionAdapter,
    SimilarSolutionsResult,
    find_similar_past_solutions,
)
from projectmind.reasoning.tree_of_thoughts import (
    AlternativeGenerator,
    challenge_plan,
    explore_alternatives,
)

__all__ = [
    "PERSPECTIVES",
    "AlternativeGenerator",
    "CounterArgument",
    "DevilsAdvocateResult",
    "MemoryStoreSolutionAdapter",
    "PostMortemResult",
    "ReActLoop",
    "SelfCritiqueEngine",
    "SequentialThinkingEngine",
    "SimilarSolution",
    "SimilarSolutionAdapter",
    "SimilarSolutionsResult",
    "challenge_plan",
    "confidence_score",
    "critique_code_change",
    "critique_plan",
    "explore_alternatives",
    "find_similar_past_solutions",
    "play_devils_advocate",
    "react_step",
    "record_learning",
    "self_reflect",
    "sequential_think",
    "validate_step",
]
