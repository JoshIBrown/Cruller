"""export — a JPEG whose raw original is here too.

A raw is not made from a JPEG, so the direction needs no argument. What does
need one is that the two hold the same picture — a raw beside an unrelated
JPEG is two photographs, and being a raw says nothing about a relationship.
"""
from .evidence import structure_agrees
from .rule import Rule


class Export(Rule):
    name = "export"
    says = "a JPEG whose raw original is also here"

    def holds(self, pair):
        return (pair.keeper["raw"] and not pair.other["raw"]
                and structure_agrees(pair.keeper, pair.other))
