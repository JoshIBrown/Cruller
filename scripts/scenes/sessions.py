"""A shoot: the photographs taken on one outing.

The cheap half of finding a scene. Capture time costs nothing to read and it
divides a library almost for free — you were pointed at one thing for a while,
then you stopped.

Where the line falls is read off the library rather than chosen. Across 7,994
nature photographs the gaps between consecutive shots run smoothly from
fractions of a second upward, with no natural cliff — until about ninety
minutes, where the largest single jump in the sorted gaps sits and 96% of all
gaps fall below. That is the difference between pausing and going home.
"""

GAP = 90 * 60.0


def split(records, gap=GAP):
    """Indices grouped into shoots, in the order they were taken.

    Every record is in exactly one shoot, including the ones taken alone: a
    shoot of one is still a shoot, and it is the scene stage that decides
    nothing came of it.
    """
    order = sorted(range(len(records)), key=lambda i: records[i]["t"])
    if not order:
        return []
    shoots, current = [], [order[0]]
    for previous, this in zip(order, order[1:]):
        if records[this]["t"] - records[previous]["t"] <= gap:
            current.append(this)
        else:
            shoots.append(current)
            current = [this]
    shoots.append(current)
    return shoots
