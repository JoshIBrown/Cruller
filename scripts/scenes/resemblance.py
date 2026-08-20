"""Whether two photographs look like each other.

Not whether they are the same photograph — that question belongs to round one,
and asking it here is what made the tool blind to a burst. Fifty frames of a
bird in flight are one scene and no two of them are the same photograph; asked
the round one way, the longest burst in a folder of 8,000 came out as no group
at all.

So this reads the sketch, which is already in hand for every photograph and
carries composition rather than detail. Measured across six bursts: frames of
one burst agree at 0.918, frames of different bursts at 0.343. The two are far
apart and the line between them is not delicate.
"""
import numpy as np


def look(record, _cache={}):
    """A photograph's sketch as a unit vector, so agreement is a dot product."""
    key = id(record)
    got = _cache.get(key)
    if got is None:
        v = np.asarray(record["thumb"], dtype=np.float32).ravel()
        v = v - v.mean()
        size = float(np.linalg.norm(v))
        got = _cache[key] = v / size if size else v
    return got


def agreement(a, b):
    """How much two photographs look alike, from -1 to 1."""
    return float(look(a) @ look(b))


def middle(records):
    """The look a set of photographs has in common."""
    stack = np.array([look(r) for r in records])
    centre = stack.mean(axis=0)
    size = float(np.linalg.norm(centre))
    return centre / size if size else centre
