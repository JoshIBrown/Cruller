"""crop — a crop of the frame being kept.

Proven by containment: the alignment fits one frame wholly inside the other and
the zoom says which way round. Same instant only — seconds apart, a crop
signature is as often a burst shot while zooming, and a subject who moved
between the frames would then leave by a rule no limit can reach. Measured at
50/50 on the labels.
"""
from .evidence import pictures_agree
from .rule import Rule


class Crop(Rule):
    name = "crop"
    says = "a crop of the frame being kept"

    def holds(self, pair):
        v, dt = pair.aligned, pair.apart
        if v is None or dt is None or dt >= 2.0 or v.get("scene") != "same":
            return False
        if not pictures_agree(v):
            return False
        z = v.get("zoom") or 1.0
        return ((v.get("b_in_a") == 1.0 and z <= 0.91)
                or (v.get("a_in_b") == 1.0 and z >= 1.10))

    def proves_membership(self, pair):
        return self.holds(pair)
