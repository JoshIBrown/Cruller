"""Round two: the scenes there are too many photographs of.

A different question from round one, and so a different instrument. Round one
asks whether one file is a copy of another and proves it. This asks something
softer and more useful — *have I taken too many of this?* — and it cannot be
proved, so nothing here is deleted on the tool's say-so. A scene is gathered
and shown, and a person keeps what they want.

Two steps, cheap one first.

**The shoot.** Capture time divides a library almost for free: photographs
taken within ninety minutes of each other belong to one outing. See
sessions.py for where that number came from.

**The scene.** Within a shoot, a photograph joins a scene when it agrees with
what the scene already looks like — the average of its members, not whichever
frame happens to sit next to it. That difference is the whole thing. Agreeing
with a neighbour lets a scene walk: a chain of neighbours ran from 2013 to 2019
and held pairs that were anti-correlated, one photograph at a time. Measured
against the middle, the worst pair inside the largest scene went from -0.06 to
0.53.

Growing from the middle is also what holds a scene together while it changes.
The sun goes down and the colour moves through it; the eagle turns its head,
opens its wings, and leaves. Every frame still agrees with what the scene is
about, so the scene stays whole — and a few close-ups of a turtle taken in the
middle of the evening do not join it.

Scenes come back largest first, because the one you took most photographs of is
the one worth opening.
"""
from . import resemblance, sessions
from .resemblance import agreement, middle
from .sessions import split

#: How much a photograph must agree with a scene to belong to it.
#:
#: Frames of one burst agree at 0.918 and frames of different bursts at 0.343,
#: so anything between is defensible and the line is not delicate. What settles
#: it is the difference between two real scenes: an evening of one sunset holds
#: together at 0.89, while eighteen views along a five-hour hike — all peaks and
#: trees under sky, and every one a different place — sit at 0.76. At 0.85 the
#: sunset stays whole and the hike disperses, which is the right way round: a
#: scene is meant to be photographs there are too many of, not photographs that
#: happen to be composed alike.
ALIKE = 0.85

#: A scene of one is not a scene. Nothing is gathered for a single photograph.
LEAST = 2


def gather(records, gap=sessions.GAP, alike=ALIKE):
    """Every scene in these photographs, largest first.

    `records` need a capture time and a sketch. Returns lists of indices into
    `records`, each list one scene, in capture order within it.
    """
    import numpy as np

    found = []
    for shoot in sessions.split(records, gap):
        grown = []
        waiting = list(shoot)
        while len(waiting) >= LEAST:
            seed = waiting.pop(0)
            members = [seed]
            centre = resemblance.look(records[seed])
            while True:
                best, score = None, alike
                for candidate in waiting:
                    agrees = float(resemblance.look(records[candidate]) @ centre)
                    if agrees >= score:
                        best, score = candidate, agrees
                if best is None:
                    break
                waiting.remove(best)
                members.append(best)
                centre = middle([records[m] for m in members])
            if len(members) >= LEAST:
                members.sort(key=lambda i: records[i]["t"])
                grown.append(members)
        found.extend(_join(records, grown, alike))
    found.sort(key=len, reverse=True)
    return found


def _join(records, grown, alike):
    """Fold together the scenes that turn out to be the same scene.

    A scene grows from wherever the first unclaimed photograph happens to be,
    so one subject shot in two spells becomes two scenes and there is nothing
    in the growing to notice. The eagle before it turned and the eagle after
    are the same bird and belong in one group; splitting them is the thing
    Josh could see and the algorithm could not.

    The test between two scenes is the test inside one: everything in the
    joined scene must still agree with its middle. Comparing the two middles
    instead is what lets a scene walk — join a scene, the middle shifts, and
    the shifted middle agrees with something the original never would. Guarded
    this way the largest scene in a folder of landscapes came to 28
    photographs; unguarded, the same folder produced one scene of 133 out of
    144, which is not a scene but a shrug.
    """
    import numpy as np

    scenes_here = [list(g) for g in grown]
    again = True
    while again:
        again = False
        for a in range(len(scenes_here)):
            for b in range(a + 1, len(scenes_here)):
                both = scenes_here[a] + scenes_here[b]
                centre = middle([records[i] for i in both])
                if min(float(resemblance.look(records[i]) @ centre)
                       for i in both) < alike:
                    continue
                scenes_here[a] = sorted(both, key=lambda i: records[i]["t"])
                del scenes_here[b]
                again = True
                break
            if again:
                break
    return scenes_here
