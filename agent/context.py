"""What the code knows while an agent works, which the model can't change."""

from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from threading import Lock


@dataclass(frozen=True)
class ClaimContext:
    """The claim a claim agent is working."""

    claim_id: str


@dataclass
class RunContext:
    """A run of the queue agent, and how it hands a claim to a claim agent."""

    run_id: str
    cap: int
    work_claim: Callable[[str], str]
    attempted: set[str] = field(default_factory=set)
    finished: bool = False
    one_at_a_time: AbstractContextManager[bool] = field(default_factory=Lock)

    def has_room_for(self, claim_id: str) -> bool:
        """Whether working the claim keeps the run within its cap."""
        return claim_id in self.attempted or len(self.attempted) < self.cap
