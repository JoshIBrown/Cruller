"""non-hdr — the frame a camera merged its HDR exposure from.

Shooting HDR writes two files for one press of the shutter and marks them in
EXIF: 3 on the merged exposure, 4 on the untouched frame it was merged from.
Josh judged ten of these pairs and kept the merge every time — nine of the ten
saying he could not tell the two apart, and the tenth preferring the merge for
not blowing out the background.

The marks alone are not enough. Two different captures minutes apart can carry
a 3 and a 4, and one cull went out that way before this asked for a shared
capture instant: a merge at 18:12:05 deleting a frame from 18:12:07.
"""
from .evidence import HDR_MERGE, HDR_SPARE
from .rule import Rule


class NonHdr(Rule):
    name = "non-hdr"
    says = "the frame the camera merged its HDR exposure from"

    def holds(self, pair):
        if not pair.one_capture:
            return False
        return (pair.keeper.get("rendered") == HDR_MERGE
                and pair.other.get("rendered") == HDR_SPARE)
