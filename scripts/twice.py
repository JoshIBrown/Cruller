"""Has this JPEG been saved more than once?

A JPEG stores each block as coefficients divided by a quantization table and
rounded to whole numbers. Save it again with a *finer* table and every stored
value is multiplied up and re-divided by a smaller step, which can only land on
some of the new integers: the histogram grows a comb of empty bins, with a
period set by the ratio of the two tables. A single pass cannot produce that,
so a comb is evidence rather than a preference.

This reads the integers as stored — see coefficients.py for why decoding to
pixels first destroys them.

It only detects the finer-second-pass case. Saving again more coarsely collapses
values together instead, which leaves a narrower histogram and no comb, and is
indistinguishable from a photograph that simply had less detail. That is the
right half to catch: a coarser re-save already loses to its source on the
compression rungs, while a finer one beats them, which is how a Windows Photo
Viewer re-save came to be kept over its iPhone original.
"""
import numpy as np

from coefficients import Unsupported, luma_coefficients

# The low-frequency band, skipping DC. DC carries brightness and is coded as a
# difference between blocks, so its histogram says nothing about quantization.
BANDS = ((0, 1), (1, 0), (1, 1), (0, 2), (2, 0), (2, 1), (1, 2), (2, 2))
SPAN = 24          # bins either side of zero; beyond this a photograph is empty
MIN_FILLED = 9     # a histogram narrower than this cannot show a period


def _comb(counts):
    """How strongly this histogram alternates full and empty, 0 to 1.

    Zero for a smooth curve. One when every other bin is empty and the rest
    are not, which is what a second, finer quantization leaves behind.
    """
    lo, hi = counts.nonzero()[0].min(), counts.nonzero()[0].max()
    counts = counts[lo:hi + 1]
    if counts.size < MIN_FILLED:
        return None
    best = 0.0
    for period in (2, 3, 4, 5):
        for phase in range(period):
            on = counts[phase::period]
            off = np.delete(counts, np.arange(phase, counts.size, period))
            if on.size < 3 or off.size < 3 or on.sum() == 0:
                continue
            # Everything on the period, nothing off it.
            best = max(best, (on.sum() - off.sum()) / counts.sum())
    return float(max(best, 0.0))


PROVEN = 0.40      # a comb this clean cannot come from one quantization
CLEAN = 0.20       # below this a file shows no comb at all

_cache = {}


def saved_again(path):
    """How strongly this file shows a second, finer save. None if unreadable.

    Near zero for a file saved once. Approaching one for a re-save whose comb
    is clean. Memoised, because a file in a group is asked about once per
    comparison it takes part in, and reading the scan costs about 100ms.
    """
    if path in _cache:
        return _cache[path]
    _cache[path] = v = _score(path)
    return v


def _score(path):
    try:
        c = luma_coefficients(path)
    except Exception:
        return None
    scores = []
    for u, v in BANDS:
        x = c[:, u, v]
        x = x[np.abs(x) <= SPAN]
        if x.size < 500:
            continue
        counts = np.bincount(x - x.min(), minlength=1).astype(float)
        if not counts.any():
            continue
        s = _comb(counts)
        if s is not None:
            scores.append(s)
    return float(np.median(scores)) if len(scores) >= 3 else None
