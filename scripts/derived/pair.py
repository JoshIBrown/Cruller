"""The two files a rule is asked about."""
from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class Pair:
    """One file that would be kept, and one that would go.

    `keeper` and `other` are the records read from each photograph — pixels
    reduced to a sketch, dimensions, capture time, and the marks its camera
    left. `aligned` is what the full look measured when one frame was warped
    onto the other, or None where no alignment was made. `apart` is the gap
    between the two capture times in seconds.

    A rule may read all four and nothing else. Everything it needs to justify
    itself is here, which is what lets each one be read, tested and argued with
    on its own.
    """

    keeper: Dict[str, Any]
    other: Dict[str, Any]
    aligned: Optional[Dict[str, Any]] = None
    apart: Optional[float] = None

    @property
    def one_capture(self) -> bool:
        """Did one press of the shutter produce both of these?"""
        from .evidence import ONE_CAPTURE
        return self.apart is not None and self.apart < ONE_CAPTURE
