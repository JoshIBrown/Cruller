"""copy — the same bytes under another name."""
import numpy as np

from .rule import Rule


class Copy(Rule):
    name = "copy"
    says = "byte-identical to the one being kept"

    def holds(self, pair):
        return pair.other["md5"] == pair.keeper["md5"]
