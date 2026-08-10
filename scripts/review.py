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
import http.server
import json
import os
import socket
import threading
import webbrowser

from loaders import open_image

THUMB_LONG = 1100          # generous: the point is to see whether it is a duplicate


def _thumbs(pairs, out_dir):
    """One image per file, however many pairs name it."""
    made = {}
    os.makedirs(out_dir, exist_ok=True)
    for pair in pairs:
        for path in (pair["keeper_path"], pair["culled_path"]):
            if path in made:
                continue
            name = f"{len(made):04d}.jpg"
            try:
                im = open_image(path).convert("RGB")
                im.thumbnail((THUMB_LONG, THUMB_LONG))
                im.save(os.path.join(out_dir, name), quality=86)
                made[path] = name
            except Exception:
                made[path] = None
    return made


BLIND_FOOT = """
  <button class="go" onclick="finish('audit')">Done \u2014 score me</button>"""
JUDGE_FOOT = """
  <button class="go" onclick="finish('apply')">Apply the rest</button>
  <button onclick="finish('quit')">Quit \u2014 move nothing</button>"""


def _page(pairs, thumbs, title, subtitle, blind=False):
    foot = BLIND_FOOT if blind else JUDGE_FOOT
    blind_js = "true" if blind else "false"
    rows = []
    for n, p in enumerate(pairs):
        ka, kb = thumbs.get(p["keeper_path"]), thumbs.get(p["culled_path"])
        if not ka or not kb:
            continue
        if blind:
            # Nothing on the page may say which frame the tool chose, or which
            # side it is on: the answer to the question must not be visible
            # while the question is being asked.
            if p.get("flip"):
                ka, kb = kb, ka
            rows.append(f"""
<section class="pair" data-n="{n}" data-group="{n}">
  <div class="head"><span class="num">{n + 1}</span>
    <span class="state" id="s{n}"></span></div>
  <div class="frames">
    <figure><a href="img/{ka}" target="_blank">
      <img src="img/{ka}" loading="lazy"></a></figure>
    <figure><a href="img/{kb}" target="_blank">
      <img src="img/{kb}" loading="lazy"></a></figure>
  </div>
  <div class="acts">
    <button type="button" onclick="same({n})">The same photograph</button>
    <button type="button" onclick="differ({n})">Different photographs</button>
    <input id="r{n}" placeholder="anything worth noting? (optional)"
           oninput="note({n})">
  </div>
</section>""")
            continue
        diff = "" if p.get("difference") is None else f"{p['difference']:.0f}% different"
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
      <img src="img/{ka}" loading="lazy"></a>
      <figcaption><b>keeping</b> {os.path.basename(p['keeper_path'])}</figcaption></figure>
    <figure class="drop"><a href="img/{kb}" target="_blank">
      <img src="img/{kb}" loading="lazy"></a>
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
    ? (a.denied ? 'different' : (a.swapped ? 'the same' : ''))
    : (a.denied ? 'will not be culled'
                : (a.swapped ? (kin ? 'this one becomes the keeper'
                                    : 'the other one goes')
                             : ''));
  const d = Object.values(A).filter(x => x.denied).length;
  const s = Object.values(A).filter(x => x.swapped && !x.denied).length;
  document.getElementById('tally').textContent = BLIND
    ? `${{d + s}} of {len(pairs)} judged · ${{d}} different, ${{s}} the same`
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
        ? 'Scoring. Your answer is in the terminal.'
        : (action === 'apply'
            ? 'Applying. You can close this page.'
            : 'Nothing moved, your answers are kept. Back to the settings.');
    }});
}}
</script>"""


def ask(pairs, out_dir, title, subtitle, blind=False):
    """Show the page, wait for an answer, return it.

    Returns `(action, answers)` where action is "apply", "quit" or "audit", or
    `(None, {})` if the page was closed without answering.
    """
    if not pairs:
        return None, {}
    thumbs = _thumbs(pairs, os.path.join(out_dir, "img"))
    with open(os.path.join(out_dir, "index.html"), "w", encoding="utf-8") as fh:
        fh.write(_page(pairs, thumbs, title, subtitle, blind))

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
    return answer.get("action"), answer.get("answers") or {}
