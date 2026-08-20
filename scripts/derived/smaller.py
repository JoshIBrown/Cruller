"""smaller — the same picture at a lower resolution.

Holding fewer pixels is a fact about a file, not a relationship between two, so
this may only claim lineage once the pictures agree. Without that it is just
two photographs of different sizes.

What it still cannot see is an enlargement. Ranking by resolution assumes a
copy is never larger than its source, which an upscaled export breaks. Spot
checks say that is not live in this library — keepers read as full-resolution
frames rather than enlargements — but it is the one way this rule can be wrong.
"""
from .evidence import structure_agrees
from .rule import Rule


class Smaller(Rule):
    name = "smaller"
    says = "the same picture at a lower resolution"

    def holds(self, pair):
        k, o = pair.keeper, pair.other
        kp, op = k["w"] * k["h"], o["w"] * o["h"]
        return (op and kp and op < kp * 0.9
                and structure_agrees(k, o))
