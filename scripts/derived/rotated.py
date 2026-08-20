"""rotated — a quarter turn of the frame being kept.

Two ways to see one thing, because the obvious way is blind to the common case.

**In the alignment.** Where the pixels really are turned relative to each
other, the warp reports it, and a rotation within three degrees of a right
angle alongside agreeing pictures is a turned copy.

**In the stored shape.** Far more often the turn is baked in and the
orientation flag cleared, and then the alignment sees nothing at all:
orientation is applied before anything is measured, so a frame stored sideways
and its upright twin line up with *no rotation* — one such pair reads rot=0.0
and a residual of 0.8%. What gives it away is the stored dimensions being
transposes of each other. Nineteen captures in one library are that shape and
every one was reaching the review as a plain near-duplicate.

For the second, a shared capture instant carries more than the residual does. A
baked turn can sit 180 degrees from its original — the same photograph with the
same histogram, anti-correlated at every pixel, reading 16%. Turning a camera
through a right angle and shooting again inside one recorded second is not
something that happens.
"""
from .evidence import pictures_agree
from .rule import Rule


class Rotated(Rule):
    name = "rotated"
    says = "a quarter turn of it, with the orientation flag reset"

    def holds(self, pair):
        return self._in_alignment(pair) or self._in_storage(pair)

    def _in_alignment(self, pair):
        v, dt = pair.aligned, pair.apart
        if v is None or dt is None or dt >= 2.0 or v.get("scene") != "same":
            return False
        rot = v.get("rot")
        return (pictures_agree(v) and rot is not None
                and abs(abs(rot) - 90) < 3)

    def _in_storage(self, pair):
        k, o = pair.keeper, pair.other
        if not (k["w"] and k["h"]):
            return False
        if not (k["w"] == o["h"] and k["h"] == o["w"] and k["w"] != k["h"]):
            return False
        return pair.one_capture or pictures_agree(pair.aligned)

    def proves_membership(self, pair):
        # Only the half the alignment can see. A turn baked into the stored
        # shape is read from the dimensions, which says nothing about whether
        # the funnel was right to pair them in the first place.
        return self._in_alignment(pair)
