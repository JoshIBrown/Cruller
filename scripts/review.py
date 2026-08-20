"""The review page: every cull, side by side, answered one at a time.

Kept on the left, going on the right, and under each pair a way to say *no, not
that one* with a reason, or *you have these the wrong way round*. Answering
each cull separately is the point: a verdict on the whole plan at once leaves a
disagreement about one pair nowhere to go.

`blind=True` asks the opposite question for the audit — same photographs, but
no labels, no filenames, and the sides swapped by a coin, so the page cannot
hint at which frame the tool chose.

It runs on a local address, serving only the folder being judged, and stops the
moment the page answers.
"""
import datetime
import hashlib
import html
import shutil
import http.server
import json
import os
import socket
import threading
import time
import webbrowser

from loaders import open_image
from sift import progress

THUMB_LONG = 1100          # generous: the point is to see whether it is a duplicate


#: The key the group page sets when a person has actually decided about a
#: group. Named here rather than spelled out at both ends, because the two ends
#: drifted once already: the page said one word and the caller read another,
#: and nothing failed — round two simply moved nothing, quietly.
REVIEWED = "reviewed"


def _srgb(im):
    """Convert to sRGB, because that is what the page will be read as.

    A phone writes its JPEGs in Display P3 and tags them; the same picture as
    HEIC arrives untagged. Writing both without a profile hands the browser two
    sets of numbers it reads alike, which is only correct for one of them.

    The shift this removes is small — a fraction of a level on the pairs
    measured — so it is a correctness fix rather than a visible one. It matters
    because the page exists to be judged by eye, and a difference the review
    introduces is indistinguishable from one the photographs have.
    """
    icc = im.info.get("icc_profile")
    im = im.convert("RGB")
    if not icc:
        return im
    try:
        import io
        from PIL import ImageCms
        return ImageCms.profileToProfile(
            im, ImageCms.ImageCmsProfile(io.BytesIO(icc)),
            ImageCms.createProfile("sRGB"), outputMode="RGB") or im
    except Exception:
        return im            # an unreadable profile is not worth losing the page over


def _fresh_dir(items):
    """A directory name no earlier round has used.

    Every round writes 0000.jpg upward into the same place, and the pages are
    served from a new port each time but the paths repeat. A browser holding
    one of those paths from a previous round can answer from its own cache, and
    then the photograph on screen is not the one being judged — which turns a
    person's careful answers into answers about the wrong pair.
    """
    seed = f"{time.time()}{len(items)}".encode()
    return "img-" + hashlib.md5(seed).hexdigest()[:8]


def _sweep_old(out_dir, keep):
    """Throw away earlier rounds' images, so they cannot be served again."""
    try:
        for f in os.listdir(out_dir):
            if f.startswith("img") and f != keep:
                shutil.rmtree(os.path.join(out_dir, f), ignore_errors=True)
    except OSError:
        pass


def _thumbs(pairs, out_dir):
    """One image per file, however many pairs name it."""
    made = {}
    os.makedirs(out_dir, exist_ok=True)
    # Every photograph is decoded and written once. On a big group that is a
    # slow stage, and a slow stage without a bar reads as a hang — the run had
    # already handed the cursor back after the stage before it.
    want = len({p for pair in pairs
                for p in (pair["keeper_path"], pair["culled_path"])})
    for pair in pairs:
        for path in (pair["keeper_path"], pair["culled_path"]):
            if path in made:
                continue
            name = f"{len(made):04d}.jpg"
            try:
                im = _srgb(open_image(path))
                im.thumbnail((THUMB_LONG, THUMB_LONG))
                im.save(os.path.join(out_dir, name), quality=86)
                made[path] = name
            except Exception:
                made[path] = None
            progress(len(made), want, "preparing the review")
    return made


# Two footers, and which one shows depends on what pressing it will do. A page
# that is only collecting judgements must not offer to apply anything: the word
# reads as "move my photographs", and someone who does not want that quits
# instead — which throws the judgements away. Josh, 2026-08-19: "the button
# wording implies files will actually be moved."
REVIEW_FOOT = """
  <button class="go" onclick="finish('audit')">Done \u2014 send my answers</button>"""
JUDGE_FOOT = """
  <button class="go" onclick="finish('apply')">Apply the rest</button>
  <button onclick="finish('quit')">Quit \u2014 move nothing</button>"""


DETAIL_HALF = 240          # the patch is shown at 1:1, so this is real pixels


def _details(pairs, out_dir):
    """The patch where each pair differs most, cropped from both originals at 1:1.

    Nobody should have to search two photographs for a difference the tool has
    already located, and at page size a small change is invisible — which is
    the whole question when the pair is a burst frame.
    """
    made = {}
    want = sum(1 for p in pairs if p.get("detail")) or 1
    for n, pair in enumerate(pairs):
        spot = pair.get("detail")
        if not spot:
            continue
        progress(len(made) + 1, want, "cropping the differences")
        fx, fy, dx, dy = spot
        try:
            a, wa = _patch(pair["keeper_path"], fx, fy)
            # The same physical patch in the other frame: shifted by the
            # measured camera motion, and scaled if the resolutions differ.
            b, wb = _patch(pair["culled_path"], fx - dx, fy - dy)
            if wa and wb != wa:
                b = b.resize((int(b.width * wa / wb) or 1,
                              int(b.height * wa / wb) or 1))
            names = (f"{n:04d}-a.jpg", f"{n:04d}-b.jpg")
            a.save(os.path.join(out_dir, names[0]), quality=90)
            b.save(os.path.join(out_dir, names[1]), quality=90)
            made[n] = names
        except Exception:
            continue
    return made


def _patch(path, fx, fy):
    im = open_image(path).convert("RGB")
    x, y = int(fx * im.width), int(fy * im.height)
    return im.crop((max(0, x - DETAIL_HALF), max(0, y - DETAIL_HALF),
                    min(im.width, x + DETAIL_HALF),
                    min(im.height, y + DETAIL_HALF))), im.width


def _serve(out_dir):
    """Open the page written in `out_dir` and wait for it to answer.

    Local only, serving that one folder, and gone the moment the page
    replies.
    """
    answer = {}
    ready = threading.Event()

    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *a, **kw):
            super().__init__(*a, directory=out_dir, **kw)

        def do_POST(self):
            length = int(self.headers.get("Content-Length") or 0)
            try:
                answer.update(json.loads(self.rfile.read(length) or b"{}"))
            except ValueError:
                pass
            self.send_response(204)
            self.end_headers()
            ready.set()

        def log_message(self, *a):
            pass                            # the run's own output is the log

    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    server = http.server.ThreadingHTTPServer(("127.0.0.1", port), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{port}/index.html"
    print(f"  review open in your browser — {url}")
    webbrowser.open(url)
    try:
        ready.wait()
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown()
    return answer.get("action"), answer


def _page(pairs, thumbs, title, subtitle, blind=False, details=None,
          verdicts=("The same photograph", "Different photographs"),
          where="img", moves=True):
    foot = JUDGE_FOOT if moves and not blind else REVIEW_FOOT
    blind_js = "true" if blind else "false"
    details = details or {}
    yes, no = verdicts
    yes_js, no_js = json.dumps(yes.lower()), json.dumps(no.lower())
    rows = []
    for n, p in enumerate(pairs):
        ka, kb = thumbs.get(p["keeper_path"]), thumbs.get(p["culled_path"])
        if not ka or not kb:
            continue
        if blind:
            # Nothing on the page may say which frame the tool chose, or which
            # side it is on: the answer to the question must not be visible
            # while the question is being asked.
            da, db = details.get(n, (None, None))
            if p.get("flip"):
                ka, kb = kb, ka
                da, db = db, da
            has = "" if not da else " with-spot"
            spot = ("" if not da else f"""
  <div class="spot"><div class="lbl">where they differ most, at full size</div>
    <div class="frames"><figure><img src="{where}/{da}" loading="lazy"></figure>
      <figure><img src="{where}/{db}" loading="lazy"></figure></div></div>""")
            rows.append(f"""
<section class="pair{has}" data-n="{n}" data-group="{n}">
  <div class="head"><span class="num">{n + 1}</span>
    <span class="state" id="s{n}"></span></div>
  <div class="frames">
    <figure><a href="img/{ka}" target="_blank">
      <img src="{where}/{ka}" loading="lazy"></a></figure>
    <figure><a href="img/{kb}" target="_blank">
      <img src="{where}/{kb}" loading="lazy"></a></figure>
  </div>{spot}
  <div class="acts">
    <button type="button" onclick="same({n})">{yes}</button>
    <button type="button" onclick="differ({n})">{no}</button>
    <input id="r{n}" placeholder="anything worth noting? (optional)"
           oninput="note({n})">
  </div>
</section>""")
            continue
        # Coerced rather than formatted straight. Every thumbnail is already
        # made by the time this runs, so a caller handing over the string a CSV
        # holds used to end the review here and throw all of that away.
        try:
            diff = f"{float(p['difference']):.0f}% different"
        except (KeyError, TypeError, ValueError):
            diff = ""
        kin = p.get("siblings") or 1
        also = (f"<span class=\"kin\">this frame is kept in place of "
                f"{kin} others</span>" if kin > 1 else "")
        rows.append(f"""
<section class="pair" data-n="{n}" data-group="{p.get('group', n)}">
  <div class="head"><span class="num">{n + 1}</span>
    <span class="why">{p['why']}</span>
    <span class="diff">{diff}</span>
    {also}
    <span class="state" id="s{n}"></span></div>
  <div class="frames">
    <figure class="keep"><a href="img/{ka}" target="_blank">
      <img src="{where}/{ka}" loading="lazy"></a>
      <figcaption><b>keeping</b> {os.path.basename(p['keeper_path'])}</figcaption></figure>
    <figure class="drop"><a href="img/{kb}" target="_blank">
      <img src="{where}/{kb}" loading="lazy"></a>
      <figcaption><b>moving out</b> {os.path.basename(p['culled_path'])}</figcaption></figure>
  </div>
  <div class="acts">
    <button type="button" onclick="deny({n})">Do not cull this</button>
    <button type="button" onclick="swap({n})">Wrong way round</button>
    <input id="r{n}" placeholder="why? (optional)" oninput="note({n})">
  </div>
</section>""")
    return f"""<meta charset="utf-8"><meta name="viewport"
 content="width=device-width,initial-scale=1"><title>{title}</title>
<style>
 :root {{ color-scheme: dark }}
 body {{ background:#16161a; color:#e8e8ea; margin:0;
        font:15px/1.5 -apple-system,BlinkMacSystemFont,sans-serif }}
 header {{ position:sticky; top:0; background:#16161aee; backdrop-filter:blur(6px);
          padding:14px 20px; border-bottom:1px solid #2a2a30; z-index:5 }}
 h1 {{ font-size:17px; margin:0 }} .sub {{ color:#9a9aa2; font-size:13px; margin-top:2px }}
 .pair {{ padding:18px 20px; border-bottom:1px solid #23232a }}
 .pair.denied {{ background:#2a1c1c }} .pair.swapped {{ background:#1c2419 }}
 .head {{ display:flex; gap:12px; align-items:baseline; margin-bottom:8px }}
 .num {{ color:#6f6f78; font-variant-numeric:tabular-nums }}
 .why {{ color:#c9c9d1 }} .diff {{ color:#8a8a93; font-size:13px }}
 .kin {{ color:#8a8a93; font-size:13px }}
 .spot {{ margin-top:10px }}
 .spot .lbl {{ color:#8a8a93; font-size:12px; margin-bottom:5px }}
 /* The whole pair still has to fit one screen, so the frames give up the
    room the patch needs rather than pushing the buttons off the bottom. */
 .with-spot .frames > figure > a > img {{ max-height:42vh }}
 .spot img {{ max-height:22vh; width:auto; max-width:100%; margin:0 auto }}
 .state {{ margin-left:auto; font-size:13px }}
 .frames {{ display:grid; grid-template-columns:1fr 1fr; gap:10px }}
 /* Grid items refuse to shrink below their content, and a photograph's
    content is 1100px wide, so without this the second frame runs off. */
 figure {{ margin:0; min-width:0 }}
 /* Both frames and the buttons on one screen: judging means comparing, and
    comparing means not scrolling between the two. */
 img {{ width:100%; height:auto; max-height:66vh; object-fit:contain;
       border-radius:5px; display:block; cursor:zoom-in }}
 figcaption {{ color:#8a8a93; font-size:12px; margin-top:5px; word-break:break-all }}
 .drop img {{ outline:2px solid #7a3b3b }}
 .acts {{ display:flex; gap:8px; margin-top:10px; flex-wrap:wrap }}
 button {{ background:#26262e; color:#e8e8ea; border:1px solid #37373f;
          border-radius:5px; padding:6px 11px; font-size:13px; cursor:pointer }}
 button:hover {{ background:#30303a }}
 input {{ background:#1d1d23; color:#e8e8ea; border:1px solid #33333b;
         border-radius:5px; padding:6px 9px; font-size:13px; flex:1; min-width:180px }}
 footer {{ position:sticky; bottom:0; background:#16161aee; backdrop-filter:blur(6px);
          border-top:1px solid #2a2a30; padding:12px 20px; display:flex; gap:10px;
          align-items:center }}
 .go {{ background:#2f6d3a; border-color:#3d8a4b }} .go:hover {{ background:#387f45 }}
 #tally {{ color:#9a9aa2; font-size:13px; margin-left:auto }}
 #done {{ padding:60px 20px; font-size:16px; display:none }}
 @media (max-width:700px) {{ .frames {{ grid-template-columns:1fr }} }}
</style>
<header><h1>{title}</h1><div class="sub">{subtitle}</div></header>
<main id="list">{''.join(rows)}</main>
<footer>{foot}<span id="tally"></span></footer>
<div id="done"></div>
<script>
const A = {{}}, BLIND = {blind_js};
function get(n) {{ return A[n] || (A[n] = {{denied:false, swapped:false, reason:""}}); }}
function paint(n) {{
  const a = get(n), el = document.querySelector(`[data-n="${{n}}"]`);
  el.classList.toggle('denied', a.denied);
  el.classList.toggle('swapped', a.swapped && !a.denied);
  const kin = el.querySelectorAll('.kin').length;
  document.getElementById('s' + n).textContent = BLIND
    ? (a.denied ? {no_js} : (a.swapped ? {yes_js} : ''))
    : (a.denied ? 'will not be culled'
                : (a.swapped ? (kin ? 'this one becomes the keeper'
                                    : 'the other one goes')
                             : ''));
  const d = Object.values(A).filter(x => x.denied).length;
  const s = Object.values(A).filter(x => x.swapped && !x.denied).length;
  document.getElementById('tally').textContent = BLIND
    ? `${{d + s}} of {len(pairs)} judged · ${{d}} / ${{s}}`
    : `${{d}} refused · ${{s}} turned round`;
}}
function group(n) {{
  return document.querySelector(`[data-n="${{n}}"]`).dataset.group;
}}
function deny(n) {{
  const a = get(n); a.denied = !a.denied;
  if (a.denied) a.swapped = false;                 // one answer per pair
  paint(n);
}}
// The blind audit asks one question with two answers, so they are exclusive.
function same(n) {{ const a = get(n); a.denied = false; a.swapped = !a.swapped;
                   paint(n); }}
function differ(n) {{ const a = get(n); a.swapped = false; a.denied = !a.denied;
                     paint(n); }}
function swap(n) {{
  const a = get(n), on = !a.swapped;
  // A group has one keeper, so turning a pair round makes that frame the
  // keeper of the group. Two at once would ask for two keepers.
  if (on) document.querySelectorAll(`[data-group="${{group(n)}}"]`).forEach(el => {{
    const m = el.dataset.n;
    if (m !== String(n) && A[m]) {{ A[m].swapped = false; paint(m); }}
  }});
  a.swapped = on;
  if (on) a.denied = false;
  paint(n);
}}
function note(n) {{ get(n).reason = document.getElementById('r' + n).value; }}
function finish(action) {{
  fetch('/done', {{method:'POST', headers:{{'Content-Type':'application/json'}},
    body: JSON.stringify({{action, answers: A}})}}).then(() => {{
      document.getElementById('list').style.display = 'none';
      document.querySelector('header').style.display = 'none';
      document.querySelector('footer').style.display = 'none';
      const d = document.getElementById('done');
      d.style.display = 'block';
      d.textContent = action === 'audit'
        ? 'Your answers are saved. You can close this page.'
        : (action === 'apply'
            ? 'Applying. You can close this page.'
            : 'Nothing moved, your answers are kept. Back to the settings.');
    }});
}}
</script>"""


def ask(pairs, out_dir, title, subtitle, blind=False,
        verdicts=("The same photograph", "Different photographs"),
        moves=True):
    """Show the page, wait for an answer, return it.

    Returns `(action, answers)` where action is "apply", "quit" or "audit", or
    `(None, {})` if the page was closed without answering.

    `moves` says whether saying yes will move files. Pass False when the caller
    only wants judgements, so the page offers to send them rather than to apply
    anything.
    """
    if not pairs:
        return None, {}
    where = _fresh_dir(pairs)
    os.makedirs(out_dir, exist_ok=True)
    _sweep_old(out_dir, where)
    img_dir = os.path.join(out_dir, where)
    thumbs = _thumbs(pairs, img_dir)
    details = _details(pairs, img_dir) if blind else {}
    with open(os.path.join(out_dir, "index.html"), "w", encoding="utf-8") as fh:
        fh.write(_page(pairs, thumbs, title, subtitle, blind, details,
                       verdicts, os.path.basename(img_dir), moves))

    _, answer = _serve(out_dir)

    # A pair that could not be rendered was never on the page, so it was never
    # agreed to. Left alone it would carry no answer, read as accepted, and be
    # culled unseen — which is the one thing the review exists to prevent.
    given = answer.get("answers") or {}
    unshown = [n for n, p in enumerate(pairs)
               if not thumbs.get(p["keeper_path"])
               or not thumbs.get(p["culled_path"])]
    for n in unshown:
        given[str(n)] = {"denied": True, "swapped": False,
                         "reason": "could not be shown, so never judged"}
    if unshown:
        print(f"  {len(unshown)} could not be displayed \u00b7 kept, unjudged")
    return answer.get("action"), given


GROUP = """
<section class="group" data-g="%(gi)d" data-n="%(n)d">
  <div class="head"><span class="num">%(gi_1)s</span>
    <span class="why">%(n)d photographs%(over)s</span>
    <span class="state" id="t%(gi)d"></span>
    <button type="button" class="all" onclick="all(%(gi)d,true)">keep all</button>
    <button type="button" class="all" onclick="all(%(gi)d,false)">keep none</button>
  </div>
  <div class="pane">
    <div class="stage" id="s%(gi)d">%(frames)s<div class="tag" id="g%(gi)d"></div></div>
    <div class="rail">%(rail)s</div>
  </div>
  <div class="foot">
    <label class="choose"><input type="checkbox" id="k%(gi)d"
      onchange="setkeep(%(gi)d, this.checked)"> keep this one</label>
    <span id="f%(gi)d"></span>
    <input class="note" id="r%(gi)d" placeholder="anything worth noting? (optional)"
           oninput="note(%(gi)d)"></div>
</section>"""


PAGE = """<meta charset="utf-8"><meta name="viewport"
 content="width=device-width,initial-scale=1"><title>%(title)s</title>
<style>
 :root { color-scheme: dark }
 body { background:#16161a; color:#e8e8ea; margin:0;
        font:15px/1.5 -apple-system,BlinkMacSystemFont,sans-serif }
 header { position:sticky; top:0; background:#16161aee; backdrop-filter:blur(6px);
          padding:14px 20px; border-bottom:1px solid #2a2a30; z-index:5 }
 h1 { font-size:17px; margin:0 } .sub { color:#9a9aa2; font-size:13px; margin-top:2px }
 .group { padding:16px 20px 20px; border-bottom:1px solid #23232a }
 .head { display:flex; gap:12px; align-items:center; margin-bottom:10px }
 .num { color:#6f6f78; font-variant-numeric:tabular-nums }
 .why { color:#c9c9d1 }
 .state { margin-left:auto; font-size:13px; color:#9a9aa2 }
 .all { background:#26262e; color:#c9c9d1; border:1px solid #37373f;
        border-radius:5px; padding:3px 9px; font-size:12px; cursor:pointer }
 .pane { display:grid; grid-template-columns:1fr 200px; gap:10px }
 /* One frame large: a thumbnail is enough to recognise a picture and not
    enough to agree to losing it. */
 .stage { position:relative; height:64vh; background:#0e0e11; border-radius:6px;
          overflow:hidden; outline:3px solid transparent; outline-offset:-3px }
 .stage img { position:absolute; inset:0; margin:auto; max-width:100%%;
              max-height:100%%; display:none }
 .stage img.on { display:block }
 .stage.keep { outline-color:#3d8a4b } .stage.cull { outline-color:#7a3b3b }
 .tag { position:absolute; left:10px; top:10px; padding:3px 9px; border-radius:4px;
        font-size:12px; background:#000a }
 /* The rail carries the whole group: what stays, what goes, at a glance. */
 .rail { display:grid; grid-template-columns:1fr 1fr; gap:6px; height:64vh;
         overflow-y:auto; align-content:start }
 .pip { position:relative; padding:0; border:0; background:none; cursor:pointer;
        border-radius:4px; overflow:hidden; outline:2px solid transparent;
        outline-offset:-2px }
 .pip img { width:100%%; aspect-ratio:1; object-fit:cover; display:block }
 .pip span { position:absolute; inset:auto 0 0 0; height:5px; background:#7a3b3b }
 .pip.keep span { background:#3d8a4b }
 .pip.here { outline-color:#e8e8ea }
 .pip.chosen img { box-shadow:inset 0 0 0 2px #e8e8ea }
 .pip.cull img { opacity:.45 }
 .foot { display:flex; gap:12px; align-items:center; margin-top:10px;
         color:#8a8a93; font-size:12px }
 .choose { display:flex; gap:6px; align-items:center; color:#e8e8ea;
           font-size:13px; white-space:nowrap; cursor:pointer }
 .note { background:#1d1d23; color:#e8e8ea; border:1px solid #33333b;
         border-radius:5px; padding:6px 9px; font-size:13px; flex:1;
         min-width:160px }
 footer { position:sticky; bottom:0; background:#16161aee; backdrop-filter:blur(6px);
          border-top:1px solid #2a2a30; padding:12px 20px; display:flex; gap:10px;
          align-items:center }
 button.go { background:#2f6d3a; border:1px solid #3d8a4b; color:#e8e8ea;
             border-radius:5px; padding:6px 11px; font-size:13px; cursor:pointer }
 button.plain { background:#26262e; border:1px solid #37373f; color:#e8e8ea;
                border-radius:5px; padding:6px 11px; font-size:13px; cursor:pointer }
 #tally { color:#9a9aa2; font-size:13px; margin-left:auto }
 #done { padding:60px 20px; font-size:16px; display:none }
 @media (max-width:760px) { .pane { grid-template-columns:1fr }
                            .rail { height:auto; grid-template-columns:repeat(4,1fr) } }
</style>
<header><h1>%(title)s</h1><div class="sub">%(subtitle)s</div></header>
<main id="list">%(blocks)s</main>
<footer>
  <button class="go" onclick="finish('apply')">Apply</button>
  <button class="plain" onclick="finish('quit')">Quit &mdash; move nothing</button>
  <span id="tally"></span>
</footer>
<div id="done"></div>
<script>
const G = %(state)s;
const AT = G.map(g => { const i = g.findIndex(p => !p.keep); return i < 0 ? 0 : i; });
const NOTE = {};
const KEPT = {"not the raw":"this is the raw", "fewer pixels":"more pixels",
  "less metadata":"keeps more of its metadata", "more compressed":"compressed less",
  "less sharp":"sharper", "smaller file":"the larger file",
  "an edit":"untouched by an editor"};
// Choosing what to look at and deciding its fate are separate acts.
function pick(gi, i) { AT[gi] = i; paint(gi); }
// Whether this group was decided about at all. An empty set of keepers is an
// answer — "none of these" — and saying nothing is not, so the two cannot be
// sent as the same thing. Without this a scene scrolled past arrives looking
// exactly like a scene somebody emptied on purpose.
// A group is in one of four states, and only three can be read off the
// checkboxes: keeping some, keeping all, keeping none. The fourth is
// unreviewed, which looks exactly like keeping none — nothing ticked — and
// means the opposite. So it is held here and shown, never inferred.
const REVIEWED = {};
function reviewed(gi) { REVIEWED[gi] = true; }
function setkeep(gi, keep) { reviewed(gi); G[gi][AT[gi]].keep = keep; paint(gi); }
function all(gi, keep) { reviewed(gi); G[gi].forEach(p => p.keep = keep); paint(gi); }
function note(gi) { reviewed(gi); NOTE[gi] = document.getElementById('r' + gi).value; }
function why(g, p) {
  if (!p.keep) return p.why + (p.because ? ' \\u00b7 ' + p.because : '');
  const beaten = g.filter(x => !x.keep && x.because).map(x => x.because)[0];
  return 'kept \\u00b7 ' + (KEPT[beaten] || beaten || "the tool's pick");
}
function paint(gi) {
  const g = G[gi], i = AT[gi], p = g[i];
  const box = document.getElementById('s' + gi);
  box.querySelectorAll('img').forEach(im =>
    im.classList.toggle('on', +im.dataset.i === i));
  box.classList.toggle('keep', p.keep);
  box.classList.toggle('cull', !p.keep);
  document.getElementById('k' + gi).checked = p.keep;
  document.getElementById('g' + gi).textContent =
    !REVIEWED[gi] ? 'unreviewed'
    : (p.keep ? 'keeping' : 'moving out') + (p.chosen ? " \\u00b7 the tool's pick" : '');
  document.querySelectorAll('[data-g="' + gi + '"] .pip').forEach(el => {
    const n = +el.dataset.i;
    el.classList.toggle('keep', g[n].keep);
    el.classList.toggle('cull', !g[n].keep);
    el.classList.toggle('here', n === i);
    el.classList.toggle('chosen', g[n].chosen);
  });
  const when = p.when ? new Date(p.when * 1000).toLocaleString() : '';
  const said = why(g, p);
  document.getElementById('f' + gi).textContent =
    (i + 1) + '/' + g.length + ' \\u00b7 ' + p.file + ' \\u00b7 ' + p.dim
    + ' \\u00b7 ' + p.size + ' MB' + (when ? ' \\u00b7 ' + when : '')
    + (said ? ' \\u00b7 ' + said : '');
  const kept = g.filter(x => x.keep).length;
  document.getElementById('t' + gi).textContent =
    !REVIEWED[gi] ? 'unreviewed' :
    kept === 0 ? 'keeping none' :
    kept === g.length ? 'keeping all' : 'keeping ' + kept + ' of ' + g.length;
  const sec2 = document.querySelector('[data-g="' + gi + '"]');
  if (sec2) sec2.classList.toggle('unreviewed', !REVIEWED[gi]);
  let moved = 0, groups = 0, waiting = 0;
  G.forEach((gg, n) => {
    if (!REVIEWED[n]) { waiting++; return; }     // unreviewed moves nothing
    const m = gg.filter(x => !x.keep).length;
    moved += m; if (m) groups++;
  });
  document.getElementById('tally').textContent =
    moved + ' to move, from ' + groups + ' group' + (groups === 1 ? '' : 's')
    + (waiting ? ' \\u00b7 ' + waiting + ' unreviewed' : '');
}
// Arrows walk the group under the pointer; space keeps or drops what is shown.
document.addEventListener('keydown', e => {
  const sec = document.querySelector('.group:hover') ||
              [...document.querySelectorAll('.group')].find(s => {
                const r = s.getBoundingClientRect();
                return r.top < innerHeight / 2 && r.bottom > innerHeight / 2;
              });
  if (!sec) return;
  const gi = +sec.dataset.g, n = +sec.dataset.n;
  if (e.key === 'ArrowRight' || e.key === 'ArrowLeft') {
    pick(gi, Math.min(n - 1, Math.max(0, AT[gi] + (e.key === 'ArrowRight' ? 1 : -1))));
    e.preventDefault();
  } else if (e.key === ' ') { setkeep(gi, !G[gi][AT[gi]].keep); e.preventDefault(); }
});
function finish(action) {
  const answers = {};
  document.querySelectorAll('.group').forEach(sec => {
    const i = +sec.dataset.g;
    answers[i] = {keep: G[i].filter(p => p.keep).map(p => p.file),
                  reviewed: !!REVIEWED[i],
                  reason: (NOTE[i] || '').trim()};
  });
  fetch('/done', {method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({action, answers})}).then(() => {
      document.getElementById('list').style.display = 'none';
      document.querySelector('header').style.display = 'none';
      document.querySelector('footer').style.display = 'none';
      const d = document.getElementById('done');
      d.style.display = 'block';
      d.textContent = action === 'apply'
        ? 'Applying. You can close this page.'
        : 'Nothing moved, your answers are kept. Back to the settings.';
    });
}
G.forEach((_, i) => paint(i));
</script>"""


def _group_page(groups, thumbs, title, subtitle, where="img"):
    """One section per group: a rail of every frame, and one shown large.

    The rail carries the whole group and its state at a glance — what stays,
    what goes, which one the tool picked. The large frame is where a person
    actually confirms a photograph, because a thumbnail is enough to recognise
    a picture and not enough to agree to losing it.

    Choosing a frame and deciding its fate are separate acts: clicking the rail
    only changes what is on screen, and a checkbox says whether it stays. A
    click that did both would change a verdict every time somebody looked.

    Every frame says why it is going, and the survivor says what it won on.
    Both phases of a run use this same page — the copies, where the reason is
    the whole argument, and the grouping, where it is worth knowing which rung
    made the choice being overridden.

    Biggest groups first, chronological within.
    """
    blocks = []
    for gi, g in enumerate(groups):
        photos = [p for p in g["photos"] if thumbs.get(p["path"])]
        if len(photos) < 2:
            continue
        start_at = next((i for i, p in enumerate(photos) if not p["keep"]), 0)
        frames, rail = [], []
        for i, p in enumerate(photos):
            on = " class='on'" if i == start_at else ""
            frames.append('<img src="%s/%s" data-i="%d"%s>'
                          % (where, thumbs[p["path"]], i, on))
            rail.append(
                '<button type="button" class="pip" data-i="%d" '
                'onclick="pick(%d,%d)"><img src="%s/%s" loading="lazy">'
                '<span></span></button>'
                % (i, gi, i, where, thumbs[p["path"]]))
        gap = photos[-1]["taken"] - photos[0]["taken"]
        over = ("" if gap <= 0 else " over %.0fs" % gap if gap < 90
                else " over %.0f min" % (gap / 60))
        blocks.append(GROUP % dict(gi=gi, gi_1=gi + 1, n=len(photos),
                                   over=over,
                                   frames="".join(frames), rail="".join(rail)))

    state = json.dumps([[{"file": p["file"], "keep": p["keep"],
                          "chosen": p["keep"], "why": p["why"],
                          "because": p["because"], "when": p["taken"],
                          "dim": p["dimensions"], "size": p["size"]}
                         for p in g["photos"] if thumbs.get(p["path"])]
                        for g in groups])
    return PAGE % dict(title=html.escape(title), subtitle=html.escape(subtitle),
                       blocks="".join(blocks), state=state)


def ask_groups(groups, out_dir, title, subtitle):
    """Show every group, take a verdict per photograph, return them.

    Returns `(action, answers)` with answers keyed by group index, each
    `{"keep": [filename, ...], "reason": str}`.
    """
    if not groups:
        return None, {}
    photos = [p for g in groups for p in g["photos"]]
    made_in = _fresh_dir(photos)
    os.makedirs(out_dir, exist_ok=True)
    _sweep_old(out_dir, made_in)
    thumbs = _thumbs([{"keeper_path": p["path"], "culled_path": p["path"]}
                      for p in photos], os.path.join(out_dir, made_in))
    page = _group_page(groups, thumbs, title, subtitle, made_in)
    with open(os.path.join(out_dir, "index.html"), "w", encoding="utf-8") as fh:
        fh.write(page)
    action, answer = _serve(out_dir)

    given = answer.get("answers") or {}
    # A photograph that could not be rendered was never on the page, so nobody
    # agreed to losing it. It is kept whatever the plan said — culling it would
    # be culling unseen, which is the one thing the review exists to prevent.
    missing = {p["file"] for p in photos if not thumbs.get(p["path"])}
    if missing:
        print(f"  {len(missing)} could not be displayed \u00b7 kept, unjudged")
        for gi, g in enumerate(groups):
            said = given.get(str(gi))
            if said is None:
                continue
            here = [p["file"] for p in g["photos"] if p["file"] in missing]
            said["keep"] = sorted(set(said.get("keep") or []) | set(here))
    return action, given
