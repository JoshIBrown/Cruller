"""edited — the same frame with the tone moved.

Geometry untouched, light changed. A true edit inherits its source's capture
instant exactly, so this asks for the identical timestamp as well as unmoved
geometry — but that is not sufficient on its own, because many cameras record
only whole seconds and frames of a burst then share an instant too. "Same
geometry, different light" describes a changing face as readily as a brightness
edit, so the pictures still have to agree.
"""
from .evidence import pictures_agree
from .rule import Rule


class Edited(Rule):
    name = "edited"
    says = "the same geometry with the tone moved"

    def holds(self, pair):
        v, dt = pair.aligned, pair.apart
        if v is None or dt is None or dt >= 2.0 or v.get("scene") != "same":
            return False
        if not (pictures_agree(v) and dt <= 0.01):
            return False
        z = v.get("zoom") or 1.0
        moved = (v.get("shift", 1.0) < 0.02 and abs(z - 1.0) < 0.03
                 and abs(v.get("rot") or 0.0) < 1.0)
        relit = (abs(v.get("lum_off") or 0.0) > 6
                 or abs((v.get("contrast") or 1.0) - 1.0) > 0.08)
        return moved and relit

    def proves_membership(self, pair):
        return self.holds(pair)
