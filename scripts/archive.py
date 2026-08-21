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
import html
import io
import json
import os

from loaders import open_image
from review import GROUP, STYLE, _srgb


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
            "why": r.get("why") or (move or {}).get("why") or "",
            "because": r.get("reason") or "",
            "when": 0.0, "dim": "", "size": ""})
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
        photo["dim"] = "%d×%d" % raw.size
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
    """Draw one round as a page in `out_dir`. Returns its path, or None."""
    os.makedirs(out_dir, exist_ok=True)
    total = sum(len(g["photos"]) for g in state)
    done = 0
    blocks, kept = [], []
    for g in state:
        frames, rail, rows = [], [], []
        for p in g["photos"]:
            pic = _thumb(p)
            done += 1
            if progress:
                progress(done, total, "opening the review")
            if not pic:
                continue
            i = len(rows)
            on = " class='on'" if i == 0 else ""
            frames.append('<img src="%s" data-i="%d"%s>' % (pic, i, on))
            rail.append('<button type="button" class="pip" data-i="%d" '
                        'onclick="pick(%d,%d)"><img src="%s">'
                        '<span></span></button>' % (i, len(kept), i, pic))
            rows.append(p)
        if len(rows) < 2:
            continue
        gi = len(kept)
        blocks.append(GROUP % dict(gi=gi, gi_1=gi + 1, n=len(rows), over="",
                                   frames="".join(frames), rail="".join(rail)))
        kept.append(rows)
    if not kept:
        return None

    gone = sum(1 for g in kept for p in g if p["gone"])
    stayed = sum(len(g) for g in kept) - gone
    what = NAMES[setting]
    page = PAGE % dict(
        title=html.escape(f"{job} — {what}"),
        subtitle=html.escape(
            f"{gone:,} moved out · {stayed:,} kept · "
            f"{len(kept):,} group{'' if len(kept) == 1 else 's'} · "
            f"change anything here and it is carried out"),
        style=STYLE, blocks="".join(blocks), state=json.dumps(kept))
    path = os.path.join(out_dir, f"{what}.html")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(page)
    return path


PAGE = """<meta charset="utf-8"><meta name="viewport"
 content="width=device-width,initial-scale=1"><title>%(title)s</title>
<style>
%(style)s
 .pip.gone img { opacity:.34 }
 .fate { font-size:13px; font-weight:600 }
 .fate.gone { color:#d2544a }
 .fate.here { color:#79c07a }
 .fate.turn { color:#d9a441 }
 section.changed { box-shadow:inset 3px 0 0 #d9a441 }
 section.changed .head { background:#33290f }
 a.orig { color:#7aa7d8; font-size:12px; margin-left:12px;
          text-decoration:none }
 a.orig:hover { text-decoration:underline }
</style>
<header><h1>%(title)s</h1><div class="sub">%(subtitle)s</div></header>
<main id="list">%(blocks)s</main>
<footer>
  <button class="go" id="save" onclick="finish()" disabled>No changes yet</button>
  <button class="plain" onclick="finish(true)">Close &mdash; change nothing</button>
  <span id="tally"></span>
</footer>
<div id="done"></div>
<script>
const G = %(state)s;
const AT = G.map(() => 0);
// What the folder looks like now, and what it would look like if this page
// were carried out. The two differing is the only reason to have opened it.
const WANT = G.map(g => g.map(p => p.keep));

function pick(gi, i) { AT[gi] = i; paint(gi); }
function setkeep(gi, on) { WANT[gi][AT[gi]] = on; paint(gi); }
function all(gi, on) { WANT[gi] = WANT[gi].map(() => on); paint(gi); }
function note() {}

// A photograph kept and now unwanted goes out; one culled and now wanted comes
// back. Both are a single move, and both can be undone again tomorrow.
function changes() {
  const out = [];
  G.forEach((g, gi) => g.forEach((p, i) => {
    if (WANT[gi][i] !== p.keep)
      out.push({file: p.file, from: p.now, to: p.was, restore: p.gone});
  }));
  return out;
}

function paint(gi) {
  const g = G[gi], at = AT[gi];
  document.querySelectorAll('#s' + gi + ' img').forEach(im =>
    im.classList.toggle('on', +im.dataset.i === at));
  document.querySelectorAll('section[data-g="' + gi + '"] .pip').forEach(b => {
    const i = +b.dataset.i;
    b.classList.toggle('on', i === at);
    b.classList.toggle('keep', WANT[gi][i]);
    b.classList.toggle('gone', !WANT[gi][i]);
  });
  const p = g[at];
  document.getElementById('k' + gi).checked = WANT[gi][at];
  // Where it is, and where this page would put it. Saying only the first
  // reads as a contradiction the moment somebody ticks the box.
  const want = WANT[gi][at], now = p.gone ? 'moved out' : 'kept';
  const turn = want === p.keep ? ''
    : (p.gone ? ' \u2192 putting it back' : ' \u2192 moving it out');
  document.getElementById('g' + gi).innerHTML =
    '<span class="fate ' + (turn ? 'turn' : p.gone ? 'gone' : 'here') + '">'
    + now + turn + '</span>'
    + '<a class="orig" href="file://' + encodeURI(p.now) + '">open it</a>';
  document.getElementById('f' + gi).textContent =
    [p.dim, p.size + ' MB', p.why, p.because].filter(Boolean).join(' \\u00b7 ');
  const differs = g.some((q, i) => WANT[gi][i] !== q.keep);
  document.querySelector('section[data-g="' + gi + '"]')
          .classList.toggle('changed', differs);
  document.getElementById('t' + gi).textContent =
    (differs ? 'changed \\u2014 ' : '')
    + 'keeping ' + WANT[gi].filter(Boolean).length + ' of ' + g.length;
  tally();
}

function tally() {
  const c = changes(), b = document.getElementById('save');
  const back = c.filter(x => x.restore).length;
  document.getElementById('tally').textContent = c.length
    ? back + ' to put back \\u00b7 ' + (c.length - back) + ' to move out' : '';
  b.disabled = !c.length;
  b.textContent = c.length
    ? 'Carry out ' + c.length + ' change' + (c.length === 1 ? '' : 's')
    : 'No changes yet';
}

function finish(nothing) {
  const c = nothing ? [] : changes();
  fetch('', {method: 'POST', headers: {'Content-Type': 'application/json'},
             body: JSON.stringify({action: c.length ? 'revise' : 'close',
                                   changes: c})})
    .finally(() => {
      document.querySelector('footer').style.display = 'none';
      const d = document.getElementById('done');
      d.style.display = 'block';
      d.textContent = c.length
        ? 'Carrying out ' + c.length + ' change' + (c.length === 1 ? '' : 's')
          + '. You can close this page.'
        : 'Nothing changed. You can close this page.';
    });
}

G.forEach((_, i) => paint(i));
</script>"""
