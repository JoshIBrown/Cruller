"""resave — the same picture, saved again more heavily.

The weakest of the ten, and the only one whose direction rests on nothing but
compression: the geometry is untouched, so nothing about the pictures says
which came first. What guards it is elsewhere — the keeper order reads whether
a file proves it was saved a second time, and demotes it if so.

Josh reviewed every cull this rule made and kept all of them.
"""
from .evidence import structure_agrees
from .rule import Rule


class Resave(Rule):
    name = "resave"
    says = "the same picture, more heavily compressed"

    def holds(self, pair):
        return (pair.other["tier"] > pair.keeper["tier"] + 1
                and structure_agrees(pair.keeper, pair.other))
