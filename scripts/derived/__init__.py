"""Round one: the photographs that were derived from another one here.

Named for what every rule proves — this file came from that file — rather
than for any one of them. `copy` is a rule inside it, not the whole idea.

A photograph is removed here only when a rule can prove it is a copy of one
that stays. The rules are asked in order and the first that holds gives the
answer; a pair no rule can account for is a near-duplicate, which is not this
round's business — it goes to the second round for a person to decide.

**The order is the priority, and it is not arbitrary.** Cheap and certain
first: the same bytes, then the marks a camera wrote about its own pair, then
the same pixels proven by a full decode. Then the relationships that have to be
argued from geometry, and last the two that rest on file properties alone.

Adding a rule means adding a file here and a line to ORDER. The suite checks
that every name a rule can return is one the first round is allowed to act on,
so a rule that belongs to neither round fails rather than quietly deleting
photographs nobody agreed to.
"""
from .copy import Copy
from .crop import Crop
from .fake_blur import FakeBlur
from .non_hdr import NonHdr
from .pair import Pair
from .export import Export
from .resave import Resave
from .rule import Rule
from .identical import Identical
from .smaller import Smaller
from .edited import Edited
from .rotated import Rotated

#: Asked in this order; the first that holds wins.
ORDER = (
    Copy(),      # the same bytes
    NonHdr(),      # the camera said so
    FakeBlur(),     # the camera said so
    Identical(),    # the same pixels, proven
    Export(),     # a raw is not made from a JPEG
    Crop(),          # containment, measured
    Rotated(),        # a quarter turn, in the alignment or in the stored shape
    Edited(),      # geometry held, light moved
    Smaller(),       # fewer pixels, and the pictures agree
    Resave(),        # coarser quantization, and the pictures agree
)

#: What the first round is allowed to act on without asking.
SETTLED = frozenset(rule.name for rule in ORDER)

#: Everything else, left to the second round.
UNSETTLED = "near-duplicate"


def belong_together(pair):
    """Is this pair one photograph by a relationship the alignment itself shows?

    Asked when the residual has already said no. A crop, a turn or a tone
    change each move the residual by their own nature, so a limit is the wrong
    instrument for them.
    """
    return any(rule.proves_membership(pair) for rule in ORDER)


def reason(pair):
    """Why `other` is a copy of `keeper`, or `UNSETTLED` if no rule can say."""
    for rule in ORDER:
        if rule.holds(pair):
            return rule.name
    return UNSETTLED
