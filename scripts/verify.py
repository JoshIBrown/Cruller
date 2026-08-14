"""Two-stage duplicate verification.

Stage one asks whether two frames show the same scene, by matching ORB
keypoints and fitting a homography with RANSAC. The count of geometrically
consistent inliers is evidence that needs no per-folder threshold: on real
material, genuine duplicates score in the hundreds and different subjects that
merely share a layout score under ten.

Stage two asks whether anything in the scene moved, by warping one frame onto
the other with that homography and measuring what is left over. Warping absorbs
rotation, zoom and perspective as well as translation, so the residual is
subject movement rather than camera movement.

When a frame is too smooth to yield keypoints — a bird against empty sky — there
is no geometric evidence either way, and the caller is told to fall back to the
plain pixel comparison.
"""
import threading

import cv2
import numpy as np

# RANSAC draws random samples from one global generator that every thread
# shares, so in principle a fit could depend on what else was running.
#
# Precaution, not a fix for a demonstrated bug — and the distinction is
# recorded because it was nearly filed as the latter. Repeated runs over the
# same burst, unseeded, produced identical plans every time; the score
# differences that prompted this came from comparing a large run against
# an 11-file one, which is two different contexts rather than two runs of the
# same thing. Those differences remain unexplained.
#
# Kept because it is nearly free: only the fit is serialised, and decoding,
# warping and the residual — the expensive parts — stay parallel.
_ransac_lock = threading.Lock()


def _homography(dst, src):
    """RANSAC homography, same answer every time it is asked."""
    with _ransac_lock:
        cv2.setRNGSeed(0)
        return cv2.findHomography(dst, src, cv2.RANSAC, 3.0)

# A residual block is 1/200th of the long edge — which is 8 pixels at the 1600
# the full look works at, so nothing changes for the 97% of photographs bigger
# than that. It matters only for the ones smaller, which keep their own size:
# a fixed 8 pixels there covers a larger share of the picture, so their scores
# were never comparable with everything else. Expressed as a fraction they are.
BLOCKS_LONG = 200
MIN_KEYPOINTS = 150              # below this, the frame is too smooth to judge
MIN_INLIERS = 60                 # below this, no evidence of a shared scene
MIN_INLIER_RATIO = 0.04

# 2,000 and not fewer or more. Tested against 79 labelled pairs:
# 500 and 1,000 find fewer of the culls he wanted, and 4,000 finds fewer still
# — the extra landmarks are weaker ones that muddy the alignment. All four
# counts hold zero false culls, and dropping to 500 would save under 1% of a
# run, so this is an optimum rather than a ceiling.
_orb = cv2.ORB_create(nfeatures=2000)
_matcher = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)

def features(gray):
    kp, des = _orb.detectAndCompute(gray, None)
    return kp, des


def block_px(shape):
    """Block size for a frame: always 200 blocks along its long edge."""
    return max(2, round(max(shape) / BLOCKS_LONG))


def _residual(a, b):
    """Texture-masked block residual between two aligned frames.

    Two hundred blocks across the long edge, wherever that lands in pixels. It
    was once a 32x18 grid whatever the resolution — 576 blocks for a whole
    photograph — which is why a changed expression scored 4.5% and a bird's
    turned head a couple of percent: the evidence was averaged away before
    anything looked at it. Two hundred is fine enough to keep that evidence and
    fixed enough that a small photograph is judged like a large one.
    """
    BLOCK = block_px(a.shape)
    h, w = a.shape
    gy, gx = h // BLOCK, w // BLOCK
    if gy < 2 or gx < 2:
        return 1.0, 99.0, None
    a = a[:gy * BLOCK, :gx * BLOCK].astype(np.float32)
    b = b[:gy * BLOCK, :gx * BLOCK].astype(np.float32)
    valid = (a > 0) & (b > 0)                      # ignore area outside the overlap
    d = np.abs(a - b) * valid
    blocks = d.reshape(gy, BLOCK, gx, BLOCK)
    cover = valid.reshape(gy, BLOCK, gx, BLOCK).mean(axis=(1, 3))
    bd = blocks.mean(axis=(1, 3))
    tex = a.reshape(gy, BLOCK, gx, BLOCK).std(axis=(1, 3))
    seen = cover > 0.5                              # only judge blocks mostly inside the overlap
    if not seen.any():
        return 1.0, 99.0, None
    masked = np.where(seen, bd, -1.0)
    wy, wx = np.unravel_index(int(np.argmax(masked)), masked.shape)
    # Where the worst block sits, as fractions of the frame — so a person can be
    # shown the exact spot the score came from, at full size, instead of being
    # left to search two whole photographs for it.
    where = (round(float(wx) * BLOCK / w, 4), round(float(wy) * BLOCK / h, 4))
    return float(bd[seen].max() / 255), float((bd[seen] / (tex[seen] + 2.0)).max()), where



SCREEN_FEATURES = 400            # keypoints kept per frame for the cheap screen
_screen_orb = cv2.ORB_create(nfeatures=SCREEN_FEATURES)


def screen_features(gray):
    """Keypoint positions and descriptors, as plain arrays.

    Computed once per file while it is already in memory, and small enough to
    keep for a whole folder: 400 keypoints is about 16 KB of descriptors, so
    8,000 files cost roughly 160 MB. cv2.KeyPoint objects cannot cross a
    process boundary, hence the bare coordinates.
    """
    kp, des = _screen_orb.detectAndCompute(gray, None)
    if des is None or not kp:
        return None, None
    pts = np.float32([k.pt for k in kp])
    return pts, des


def screen(pa, da, pb, db, shape):
    """Do these two frames show the same scene, from keypoints alone?

    No pixels, no warping, no decode — this is what makes a folder of bursts
    affordable. Most candidate pairs in a burst are genuinely different frames,
    and answering that costs a descriptor match instead of two raw decodes.

    Returns "same" (worth a proper look), "different", or "unknown" (too few
    keypoints to say).
    """
    if da is None or db is None:
        return dict(scene="unknown", inliers=0, keypoints=0)
    n = min(len(pa), len(pb))
    if n < MIN_KEYPOINTS * SCREEN_FEATURES // 2000:
        return dict(scene="unknown", inliers=0, keypoints=n)
    matches = _matcher.match(da, db)
    if len(matches) < 12:
        return dict(scene="different", inliers=0, keypoints=n)
    src = np.float32([pa[m.queryIdx] for m in matches]).reshape(-1, 1, 2)
    dst = np.float32([pb[m.trainIdx] for m in matches]).reshape(-1, 1, 2)
    H, mask = _homography(dst, src)
    inl = int(mask.sum()) if mask is not None else 0
    # Scaled down for the smaller keypoint budget: the full check wants 60 of
    # 2000, so this wants the same proportion of 400.
    if H is None or inl < MIN_INLIERS * SCREEN_FEATURES // 2000 or inl / n < MIN_INLIER_RATIO:
        return dict(scene="different", inliers=inl, keypoints=n)
    h_, w_ = shape
    centre = np.float32([[[w_ / 2, h_ / 2]]])
    disp = float(np.linalg.norm(cv2.perspectiveTransform(centre, H) - centre)) / min(h_, w_)
    scale = float(np.sqrt(abs(np.linalg.det(H[:2, :2]))))
    # A large shift or rezoom is not rejected here; recomposition is not
    # grounds to skip the full look. See `compare` for the measurement.
    return dict(scene="same", inliers=inl, keypoints=n, shift=disp, zoom=scale)


def compare(ga, gb, ka=None, da=None, kb=None, db=None):
    """Return a verdict dict for two grayscale frames.

    scene: "same" | "different" | "unknown"
    block, ratio: residual after alignment (only meaningful when scene == "same")
    """
    if ka is None:
        ka, da = features(ga)
    if kb is None:
        kb, db = features(gb)
    n = min(len(ka), len(kb))
    if da is None or db is None or n < MIN_KEYPOINTS:
        return dict(scene="unknown", inliers=0, keypoints=n, block=None, ratio=None)
    matches = _matcher.match(da, db)
    if len(matches) < 12:
        return dict(scene="different", inliers=0, keypoints=n, block=None, ratio=None)
    src = np.float32([ka[m.queryIdx].pt for m in matches]).reshape(-1, 1, 2)
    dst = np.float32([kb[m.trainIdx].pt for m in matches]).reshape(-1, 1, 2)
    H, mask = _homography(dst, src)
    inl = int(mask.sum()) if mask is not None else 0
    if H is None or inl < MIN_INLIERS or inl / n < MIN_INLIER_RATIO:
        return dict(scene="different", inliers=inl, keypoints=n, block=None, ratio=None)
    # The homography is the camera motion. It is recorded, but it is not a
    # verdict. Rejecting a pair for a shift or rezoom past a fixed limit —
    # "recomposed, therefore a different photograph" — costs real culls: of 46
    # labelled recomposed pairs a reviewer culled 31 — "I can only tell the
    # difference because of the rotation" — and the overlap residual separates
    # cullable from keep-both among them at AUC 0.802, close to what it
    # scores on ordinary pairs. So the residual decides here too, and
    # `_residual` masks to the overlap, which is what makes that honest.
    h_, w_ = ga.shape
    centre = np.float32([[[w_ / 2, h_ / 2]]])
    moved = cv2.perspectiveTransform(centre, H)
    disp = float(np.linalg.norm(moved - centre)) / min(h_, w_)
    scale = float(np.sqrt(abs(np.linalg.det(H[:2, :2]))))
    # Which way, not just how far. A point in the first frame sits this much
    # further along in the second, as a fraction of the frame — enough to put a
    # marker drawn on one photograph over the same ground in the other.
    dx = float(moved[0][0][0] - centre[0][0][0]) / w_
    dy = float(moved[0][0][1] - centre[0][0][1]) / h_
    # Measured both ways round, and the larger difference wins.
    #
    # Warping is not symmetric: resampling softens the frame being moved, and
    # the overlap each fit leaves behind is different, so "how different are
    # these two" quietly depended on which one was named first. On one group of
    # eleven frames the two answers differed by up to 10.8 points and **four of
    # ten pairs changed verdict** depending on the order — and the order was
    # just whichever file happened to rank as keeper.
    #
    # Taking the larger is the safe direction rather than the average: if
    # either way of looking says these are two different photographs, they are
    # kept. It costs a second warp on pairs that reach the full look, which is
    # the small minority the cheap tiers could not settle.
    warped = cv2.warpPerspective(gb, H, (ga.shape[1], ga.shape[0]))
    block, ratio, where = _residual(ga, warped)
    try:
        Hi = np.linalg.inv(H)
        back = cv2.warpPerspective(ga, Hi, (gb.shape[1], gb.shape[0]))
        b2, r2, w2 = _residual(gb, back)
        if b2 > block:
            block, where = b2, w2
        ratio = max(ratio, r2)
    except Exception:
        pass
    # Derivative evidence, for classification rather than membership: the
    # rotation the warp absorbed, whether either frame's view lands entirely
    # inside the other (a crop), and how far the light moved at identical
    # geometry (a tonal edit). All read from work already done.
    rot = float(np.degrees(np.arctan2(H[1, 0], H[0, 0])))
    hb_, wb_ = gb.shape
    tol_a, tol_b = 0.02 * max(w_, h_), 0.02 * max(wb_, hb_)
    cb = cv2.perspectiveTransform(
        np.float32([[[0, 0]], [[wb_, 0]], [[wb_, hb_]], [[0, hb_]]]), H).reshape(4, 2)
    b_in_a = float(np.mean((cb[:, 0] >= -tol_a) & (cb[:, 0] <= w_ + tol_a)
                           & (cb[:, 1] >= -tol_a) & (cb[:, 1] <= h_ + tol_a)))
    try:
        ca = cv2.perspectiveTransform(
            np.float32([[[0, 0]], [[w_, 0]], [[w_, h_]], [[0, h_]]]), Hi).reshape(4, 2)
        a_in_b = float(np.mean((ca[:, 0] >= -tol_b) & (ca[:, 0] <= wb_ + tol_b)
                               & (ca[:, 1] >= -tol_b) & (ca[:, 1] <= hb_ + tol_b)))
    except Exception:
        a_in_b = 0.0
    ov = (ga > 0) & (warped > 0)
    if ov.any():
        af, wf = ga[ov].astype(np.float32), warped[ov].astype(np.float32)
        lum_off = float(af.mean() - wf.mean())
        contrast = float(af.std() / (wf.std() or 1.0))
    else:
        lum_off, contrast = 0.0, 1.0
    # shift and zoom are reported on every verdict: they are the camera-motion
    # record the open half of that rule (motion gradually tightening the test) will be
    # fitted from.
    return dict(scene="same", inliers=inl, keypoints=n, block=block, ratio=ratio,
                shift=disp, zoom=scale, dx=dx, dy=dy, where=where, rot=rot,
                b_in_a=b_in_a, a_in_b=a_in_b, lum_off=lum_off, contrast=contrast)
