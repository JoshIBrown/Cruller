"""The reviews of a finished job, opened again.

A run answers a question once and then the answer is gone: the page was served
from a temporary folder and the folder is swept. What is left is a heap of
files in the culled folder, which shows what happened but not what the choice
looked like — and undoing the whole job was the only way back from a single
wrong call.

Dragging that folder onto the app opens both rounds again, exactly as they were
decided, so one photograph can be put back without disturbing the other sixty.

Nothing is stored to make this work. The pages are built when they are asked
for, from the two records the job already keeps: the review, which says which
photographs were weighed against each other, and the log, which says where each
one ended up. Anything stored alongside would be a third account of the same
facts, free to disagree with them.
"""

import base64
import csv
import io
import os

from loaders import open_image
import review
from review import _srgb


# Round one is derivatives of one photograph; round two is scenes there are too
# many photographs of. These are the words Josh uses for them.
NAMES = {"copies": "derivatives", "scenes": "scenes"}

# Small enough that a hundred of them fit in one page that opens at once, large
# enough to recognise the picture and be sure about putting it back. The
# photograph itself is one click away — it is on this disk either way.
THUMB_LONG = 560
QUALITY = 78


def rounds_of(records, job):
    """Which rounds this job can show again, in the order they ran."""
    review = os.path.join(records, f"{job} - review.csv")
    if not os.path.exists(review):
        return []
    seen = {r.get("setting") for r in _rows(review)}
    return [s for s in ("copies", "scenes") if s in seen]


def _rows(path):
    try:
        with open(path, newline="", errors="replace") as fh:
            return list(csv.DictReader(fh))
    except OSError:
        return []


def _where(records, job):
    """Every photograph the job moved: where it was -> where it is now."""
    moves = {}
    for r in _rows(os.path.join(records, f"{job} - log.csv")):
        if r.get("from") and r.get("to"):
            moves[r["from"]] = r
    return moves


def groups_of(records, job, setting, source):
    """Rebuild one round's groups from what the job wrote down.

    The review says which photographs were put side by side and judged against
    each other; the log says which of them left. Together that is the page.

    Where a photograph is *now* is read from the log every time rather than
    from what the review said should happen, so a decision changed since — or a
    move that failed — shows as it really is rather than as it was intended.
    """
    rows = _rows(os.path.join(records, f"{job} - review.csv"))
    rows = [r for r in rows if r.get("setting") == setting
            and r.get("action") != "revise" and r.get("group") != ""]
    if not rows:
        return []
    # Only the last time this round was judged. Reviewing a folder twice
    # appends both, and the earlier one is not what the folder looks like.
    last = max(r["judged_at"] for r in rows)
    rows = [r for r in rows if r["judged_at"] == last]

    moves = _where(records, job)
    by_group = {}
    for r in rows:
        was = os.path.join(source, r["file"]) if source else r["file"]
        move = moves.get(was)
        by_group.setdefault(r["group"], []).append({
            "file": r["file"], "was": was,
            "now": move["to"] if move else was,
            "gone": move is not None,
            # What is true now, not what was decided then: the two agree unless
            # somebody has been back since, and then it is this that is right.
            "keep": move is None,
            # The review holds the rule that named it — "crop", "non-hdr".
            # The log's reason is bookkeeping and only stands in when the
            # review has nothing to say.
            # `path` is where the picture is read from; the page keys its
            # thumbnails by it. `was` and `now` are what a change of mind
            # needs, and they are what the two ends of a move are.
            "path": move["to"] if move else was,
            "why": r.get("why") or (move or {}).get("why") or "",
            "because": r.get("reason") or "",
            "chosen": False, "difference": None,
            "taken": 0.0, "when": 0.0, "dimensions": "", "dim": "",
            "size": ""})
    out = []
    for gid in sorted(by_group, key=lambda g: (len(by_group[g]), g),
                      reverse=True):
        photos = [p for p in by_group[gid] if os.path.exists(p["now"])]
        if len(photos) >= 2:
            out.append({"id": gid, "photos": photos})
    return out


def _thumb(photo):
    """One picture, small, as a data URI. Fills in its size on the way past.

    Asked for a small picture, a JPEG decoder can skip most of its own work and
    come back at an eighth the width. Nothing here needs the full frame — a
    page of sixty took twenty seconds without this and three with it — and
    every reader gets the same picture either way, just sooner.
    """
    try:
        raw = open_image(photo["now"])
        # Read before drafting: asking for a small picture changes what the
        # image says its size is, and what belongs on the page is the size of
        # the photograph, not of the copy being made to show it.
        photo["dim"] = photo["dimensions"] = "%d×%d" % raw.size
        photo["size"] = "%.1f" % (os.path.getsize(photo["now"]) / 1e6)
        try:
            raw.draft("RGB", (THUMB_LONG, THUMB_LONG))
        except (AttributeError, ValueError):
            pass                    # not a JPEG, or already decoded
        im = _srgb(raw)
        im.thumbnail((THUMB_LONG, THUMB_LONG))
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=QUALITY)
        return ("data:image/jpeg;base64,"
                + base64.b64encode(buf.getvalue()).decode("ascii"))
    except Exception:
        return None


def render(out_dir, job, setting, state, progress=None):
    """Draw one round as a page in `out_dir`. Returns its path, or None.

    The same page the review itself uses. Looking at a group of photographs and
    saying which to keep is one act whether it is happening for the first time
    or the second, and two pages would be two sets of keyboard shortcuts, two
    ideas of what green means, and one of them always the neglected one.
    """
    os.makedirs(out_dir, exist_ok=True)
    total = sum(len(g["photos"]) for g in state)
    done = 0
    groups, thumbs = [], {}
    for g in state:
        photos = []
        for p in g["photos"]:
            pic = _thumb(p)
            done += 1
            if progress:
                progress(done, total, "opening the review")
            if pic:
                thumbs[p["path"]] = pic
                photos.append(p)
        if len(photos) >= 2:
            groups.append({"id": g["id"], "worst": None, "photos": photos})
    if not groups:
        return None

    gone = sum(1 for g in groups for p in g["photos"] if p["gone"])
    stayed = sum(len(g["photos"]) for g in groups) - gone
    what = NAMES[setting]
    # The pictures travel inside the page, so there is no folder to name: the
    # one they were served from is swept when the run that made them ends.
    page = review._group_page(
        groups, thumbs, f"{job} — {what}",
        f"{gone:,} moved out · {stayed:,} kept · "
        f"{len(groups):,} group{'' if len(groups) == 1 else 's'} · "
        f"arrows to step through · double-click a picture to keep or drop it",
        where=None, proposed=True, revisit=True)
    path = os.path.join(out_dir, f"{what}.html")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(page)
    return path
