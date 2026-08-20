"""fake-blur — the depth blur a camera computed, beside the frame it came from.

Portrait mode writes 8 on the blurred render and 9 on the untouched frame.
Josh judged twenty of these and wanted the untouched frame every time — "the
left has the fake blurry background". The blur is an effect rather than a
photograph, which is why this points the opposite way to its HDR twin.
"""
from .evidence import BLUR, BLUR_SOURCE
from .rule import Rule


class FakeBlur(Rule):
    name = "fake-blur"
    says = "a depth blur the camera computed, not the frame it shot"

    def holds(self, pair):
        if not pair.one_capture:
            return False
        return (pair.keeper.get("rendered") == BLUR_SOURCE
                and pair.other.get("rendered") == BLUR)
