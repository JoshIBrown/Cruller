"""duplicate — the same bytes under another name.

Named `duplicate` rather than `copy` so the file does not share a name with
a standard-library module. Nothing breaks either way — a name inside a
package is only reachable as derived.<name> — but a reader who sees copy.py
has to work that out, and the reason a name exists is to save them the
trouble.
"""
import numpy as np

from .rule import Rule


class Duplicate(Rule):
    name = "duplicate"
    says = "byte-identical to the one being kept"

    def holds(self, pair):
        return pair.other["md5"] == pair.keeper["md5"]
