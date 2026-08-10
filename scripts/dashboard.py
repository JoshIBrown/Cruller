#!/usr/bin/env python3
"""dashboard.py - one page: what Cruller has reclaimed, job by job.

Reads the logs in the working folder's Records and writes Cruller.html there.
Safe to run any time; it only reads. cull.py refreshes it after every apply.
"""
import argparse, csv, datetime, html, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config
from loaders import IMG_EXT as PHOTO_EXT     # one list of what counts as a photo


def folder_stats(path):
    files = 0; size = 0
    for dp, dn, fn in os.walk(path):
        dn[:] = [d for d in dn if not d.startswith('.')]
        for f in fn:
            if f.startswith('.'): continue
            if os.path.splitext(f)[1].lower() not in PHOTO_EXT: continue
            try:
                size += os.path.getsize(os.path.join(dp, f)); files += 1
            except OSError:
                pass
    return files, size


def read_jobs(records, culled_root):
    """A job is anything with a log, plus any folder of culled files without one."""
    jobs = []
    seen = set()
    for f in sorted(os.listdir(records)):
        if not f.endswith(" - log.csv"):
            continue
        name = f[:-len(" - log.csv")]
        rows = list(csv.DictReader(open(os.path.join(records, f), errors="replace")))
        mb = 0.0
        reasons = {}
        for r in rows:
            try: mb += float(r.get("MB") or 0)
            except ValueError: pass
            why = r.get("why") or "near-duplicate"
            reasons[why] = reasons.get(why, 0) + 1
        d = os.path.join(culled_root, name)
        on_disk = folder_stats(d)[1] if os.path.isdir(d) else 0
        jobs.append(dict(name=name, files=len(rows), bytes=on_disk or int(mb * 1e6),
                         reasons=reasons))
        seen.add(name)
    if os.path.isdir(culled_root):
        for d in sorted(os.listdir(culled_root)):
            p = os.path.join(culled_root, d)
            if not os.path.isdir(p) or d in seen or d.startswith('.'):
                continue
            f, s = folder_stats(p)
            if f:
                jobs.append(dict(name=d, files=f, bytes=s,
                                 reasons={"moved before logging began": f}))
    return jobs


def bar(pct, colour="#4ea1ff"):
    pct = max(0.0, min(100.0, pct))
    return f'<div class="bar"><span style="width:{pct:.1f}%;background:{colour}"></span></div>'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--working", default=config.working_dir())
    a = ap.parse_args()
    if not a.working:
        sys.exit("no working folder configured. Set it in scripts/settings.conf "
                 "('working folder = /path'), or set CRULLER_DIR.")
    records = os.path.join(a.working, "Records")
    culled = os.path.join(a.working, "Culled Photos")
    checks = os.path.join(a.working, "Reviews")
    jobs = read_jobs(records, culled) if os.path.isdir(records) else []

    total_files = sum(j["files"] for j in jobs)
    total_bytes = sum(j["bytes"] for j in jobs)
    n_checks = 0
    if os.path.isdir(checks):
        for d in os.listdir(checks):
            p = os.path.join(checks, d)
            if os.path.isdir(p):
                n_checks += len([x for x in os.listdir(p) if not x.startswith('.')])

    gb = lambda b: f"{b/1e9:.1f} GB" if b >= 1e9 else f"{b/1e6:.0f} MB"
    rows = []
    biggest = max([j["bytes"] for j in jobs], default=1)
    for j in sorted(jobs, key=lambda x: -x["bytes"]):
        why = ", ".join(f"{v} {k}" for k, v in sorted(j["reasons"].items(), key=lambda x: -x[1]))
        rows.append(f"""<tr><td class="name">{html.escape(j['name'])}</td>
            <td class="num">{j['files']:,}</td>
            <td class="num">{gb(j['bytes'])}</td>
            <td class="barcell">{bar(100*j['bytes']/biggest)}</td>
            <td class="why">{html.escape(why)}</td></tr>""")

    now = datetime.datetime.now().strftime("%d %B %Y, %H:%M")
    doc = f"""<!doctype html><html><head><meta charset="utf-8">
<title>Cruller</title>
<style>
 :root {{ color-scheme: dark; }}
 body {{ margin:0; background:#14141a; color:#e8e8ef;
        font:16px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,Arial,sans-serif; }}
 .wrap {{ max-width:1000px; margin:0 auto; padding:48px 28px 80px; }}
 h1 {{ font-size:44px; margin:0 0 4px; letter-spacing:-1px; }}
 h1 span {{ color:#4ea1ff; }}
 .sub {{ color:#8b8b9a; margin:0 0 40px; }}
 .cards {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(180px,1fr)); gap:14px; margin-bottom:44px; }}
 .card {{ background:#1d1d26; border-radius:14px; padding:22px; }}
 .card .big {{ font-size:38px; font-weight:700; letter-spacing:-1px; }}
 .card .lbl {{ color:#8b8b9a; font-size:13px; text-transform:uppercase; letter-spacing:.08em; }}
 .card.accent .big {{ color:#3ddc84; }}
 h2 {{ font-size:15px; text-transform:uppercase; letter-spacing:.1em; color:#8b8b9a;
      margin:38px 0 14px; font-weight:600; }}
 table {{ width:100%; border-collapse:collapse; }}
 td, th {{ padding:11px 10px; border-bottom:1px solid #26262f; text-align:left; font-size:14px; }}
 th {{ color:#8b8b9a; font-weight:600; font-size:12px; text-transform:uppercase; letter-spacing:.06em; }}
 .num {{ text-align:right; font-variant-numeric:tabular-nums; white-space:nowrap; }}
 .name {{ font-weight:600; }}
 .why {{ color:#8b8b9a; font-size:13px; }}
 .barcell {{ width:180px; }}
 .bar {{ background:#26262f; border-radius:5px; height:9px; overflow:hidden; }}
 .bar span {{ display:block; height:100%; border-radius:5px; }}
 .note {{ background:#1d1d26; border-left:3px solid #4ea1ff; border-radius:0 10px 10px 0;
         padding:16px 20px; color:#b9b9c6; font-size:14px; margin-top:34px; }}
 .foot {{ color:#5a5a66; font-size:12px; margin-top:36px; }}
</style></head><body><div class="wrap">
<h1>Cru<span>ller</span></h1>
<p class="sub">Culling redundant photos. Nothing is ever deleted — everything below was moved here and can be put back.</p>

<div class="cards">
  <div class="card accent"><div class="big">{gb(total_bytes)}</div><div class="lbl">reclaimed</div></div>
  <div class="card"><div class="big">{total_files:,}</div><div class="lbl">files culled</div></div>
  <div class="card"><div class="big">{len(jobs)}</div><div class="lbl">jobs run</div></div>
  <div class="card"><div class="big">{n_checks:,}</div><div class="lbl">reviews on file</div></div>
</div>

<h2>Jobs</h2>
<table><tr><th>Job</th><th class="num">Files</th><th class="num">Size</th><th></th><th>Why</th></tr>
{''.join(rows) or '<tr><td colspan="5" class="why">no jobs recorded yet</td></tr>'}</table>

<div class="note"><strong>Everything culled is still on the drive</strong>, in
<code>{os.path.basename(a.working)}/Culled Photos</code>, organised by job with the original folder structure kept.
Each job has a plan, a log naming what was kept in its place, and thumbnails of everything that left.
Emptying that folder is the only irreversible step, and it is yours to take.</div>

<p class="foot">Generated {now} · ./crull --dashboard</p>
</div></body></html>"""
    out = os.path.join(a.working, "Cruller.html")
    with open(out, "w") as fh:
        fh.write(doc)
    print(f"{total_files:,} files, {gb(total_bytes)} reclaimed across {len(jobs)} jobs")
    print("dashboard:", out)


if __name__ == "__main__":
    main()
