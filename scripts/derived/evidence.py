"""What the rules are allowed to call proof.

Kept in one place because several rules lean on the same test, and a rule that
quietly used a slightly different idea of "the pictures agree" would be a rule
nobody could check. Each of these was arrived at from a failure — the comments
say which.
"""
import numpy as np

from loaders import open_image

# A lineage claim needs the pictures to agree, by one of two readings: what is
# left after warping one frame onto the other is small in absolute terms, or it
# is small against the texture already in the frame. Two readings because
# cropping magnifies, and magnifying resamples, which inflates the absolute
# residual on frames that are plainly one picture — two genuine crops here read
# 19.9% and 23.4% while matching their keeper exactly.
DERIVED_MAX, DERIVED_RATIO = 10.0, 5.0

# Both frames a camera writes for one capture carry the same capture time, to
# the second. Anything further apart is a second press of the shutter — a cull
# went out under a camera-pair reason before this was checked, an HDR merge at
# 18:12:05 deleting an untouched frame from 18:12:07.
ONE_CAPTURE = 0.5

# EXIF CustomRendered, for the two cases where a camera saves both the frame it
# computed and the frame it computed from. Measured over 25,728 photographs, an
# HDR capture writes 3 beside 4 and a Portrait capture writes 8 beside 9, and
# no other combination occurs.
HDR_MERGE, HDR_SPARE, BLUR, BLUR_SOURCE = 3, 4, 8, 9


def pictures_agree(aligned):
    """Do these two hold the same picture, by the alignment's own numbers?"""
    if not aligned:
        return False
    block, rel = aligned.get("block"), aligned.get("ratio")
    return ((block is not None and block * 100 <= DERIVED_MAX)
            or (rel is not None and rel <= DERIVED_RATIO))


def structure_agrees(a, b, floor=0.97):
    """Do these two hold the same picture, tone set aside?

    Brightness is the first thing an export changes and the last thing that
    matters: resizing, re-encoding and tone-mapping all move it, while the
    picture stays put. Removing each sketch's mean and scale before comparing
    asks "the same picture?" without also asking "the same tone?", which is the
    wrong question to ask of a copy.

    Free at this point — both sketches are already in hand — and it is what
    separates a real derivative from two photographs that merely differ in
    resolution or compression.
    """
    ta = np.asarray(a["thumb"], dtype=np.float32)
    tb = np.asarray(b["thumb"], dtype=np.float32)
    if ta.shape != tb.shape:
        return False
    va, vb = ta.ravel() - ta.mean(), tb.ravel() - tb.mean()
    na, nb = float(np.sqrt(va @ va)), float(np.sqrt(vb @ vb))
    if na < 1e-3 or nb < 1e-3:                 # a blank frame agrees with anything
        return False
    return float(va @ vb) / (na * nb) >= floor


def same_picture(pa, pb):
    """Decode both and compare every pixel. The only test that cannot be wrong.

    Reserved for frames the sketch has already found identical at the same
    size, because it is the one place a full decode of both files is paid for.
    """
    try:
        with open_image(pa) as ia, open_image(pb) as ib:
            if ia.size != ib.size:
                return False
            return np.array_equal(np.asarray(ia.convert("RGB")),
                                  np.asarray(ib.convert("RGB")))
    except Exception:
        return False
