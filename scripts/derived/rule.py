"""What a rule is.

A rule answers one question: is `other` a copy of `keeper`, made this
particular way? It says yes only when it can point at the evidence — the
pictures agreeing, a containment warp, a mark the camera wrote. Where it cannot
prove its own case it says nothing and the next rule is asked.

Every rule carries the name that will appear in the plan, and that name says
what is wrong with the file being removed rather than how the two are related:
`crop`, `smaller`, `resave`. Read as an instruction it is "this one is a crop,
delete it".
"""


class Rule:
    #: what the plan calls a file this rule removes
    name = ""

    #: one line, shown wherever the reasons are listed
    says = ""

    def holds(self, pair) -> bool:
        raise NotImplementedError

    def proves_membership(self, pair) -> bool:
        """Does this rule prove the two belong together, whatever the residual?

        Most rules do not. They name a copy the funnel has *already* accepted,
        and if the funnel says two frames are different photographs, a coarser
        quantization table is no argument against it.

        Three do. A crop, a quarter turn and a tone change are relationships
        read out of the alignment itself, and each is a change that pushes the
        residual past any limit by its own nature — a crop magnifies, an edit
        moves the light. Refusing them for reading far apart would be refusing
        them for being what they are.
        """
        return False

    def __repr__(self):
        return f"<{self.name}>"
