"""identical — the same picture in a different file.

Same size, same sketch, and then every pixel of both decoded and compared. The
decode is the expensive part, so it is only reached once the cheap tests agree,
and it is the one rule here that cannot be wrong.
"""
import numpy as np

from .evidence import same_picture
from .rule import Rule


class Identical(Rule):
    name = "identical"
    says = "the same pixels in a different file"

    def holds(self, pair):
        k, o = pair.keeper, pair.other
        return (not k["raw"] and not o["raw"]
                and k["w"] == o["w"] and k["h"] == o["h"]
                and np.array_equal(k["thumb"], o["thumb"])
                and same_picture(k["path"], o["path"]))
