#!/usr/bin/env python3
"""
cull.py - the whole job in one command.

Drop a folder on the app, or name it here. Nothing is ever deleted: what the
tool removes is moved to a holding folder with a log, and one command puts it
all back.

    python3 cull.py "/path/to/folder"          # the two rounds, with review
    python3 cull.py "/path/to/folder" --apply  # take the plan as it stands

**A run is two rounds, and they ask different questions.**

ROUND ONE is about copies. Every photograph is read, and where one file came
from another that is also here — the same bytes, the same pixels, a crop, a
turn, an export, a frame the camera itself wrote twice — a rule names it. Ten
rules, one per file, in `derived/`. These have one right answer, so the round
says how many and why, and looking is optional.

ROUND TWO is about choice. What survived is read again and gathered into
scenes: one shoot's worth of one subject, in `scenes/`. Nothing here is
provable, so the tool chooses nothing. It shows each scene, largest first, and
a person keeps what they want. What they did not keep moves out with the
copies, and a scene nobody reviewed is left whole.
"""
import argparse, csv, datetime, hashlib, math, os, shutil, subprocess, sys
import tempfile, time
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from loaders import open_image
import derived
import review
import scenes
import scenes.reading
import sift
from sift import progress

import config

WORKING_DIR = DEFAULT_CULL = DEFAULT_REVIEWS = DEFAULT_RECORDS = None


def set_working(wd):
    global WORKING_DIR, DEFAULT_CULL, DEFAULT_REVIEWS, DEFAULT_RECORDS
    WORKING_DIR = wd
    DEFAULT_CULL = os.path.join(wd, "Culled Photos")
    DEFAULT_REVIEWS = os.path.join(wd, "Reviews")
    DEFAULT_RECORDS = os.path.join(wd, "Records")


if config.working_dir():
    set_working(config.working_dir())


def job_for_folder(folder):
    """Is this dropped folder a finished job, rather than photos to cull?

    Dragging a folder out of `Culled Photos` onto the app plainly means "put
    this back", not "cull the culled photos again". The test is structural rather than
    a guess about contents: the folder must sit under the working folder, in
    `Culled Photos` or `Reviews`, and its job name must have a record.

    Returns (job, state) where state is one of `undoable`, `already undone`,
    `no record`, or (None, reason) when the folder is somewhere else entirely.
    """
    if WORKING_DIR is None:
        return None, None
    wd = os.path.realpath(WORKING_DIR)
    here = os.path.realpath(folder)
    if here == wd:
        return None, "the working folder itself"
    if os.path.commonpath([wd, here]) != wd:
        return None, None                      # an ordinary folder of photos
    rel = os.path.relpath(here, wd).split(os.sep)
    if rel[0] not in ("Culled Photos", "Reviews"):
        return None, f"inside the working folder ({rel[0]})"
    if len(rel) < 2:
        return None, rel[0]                    # the container, not one job
    job = rel[1]                               # deeper is fine: a job's subfolder
    if os.path.exists(os.path.join(DEFAULT_RECORDS, f"{job} - log.csv")):
        return job, "undoable"
    if os.path.exists(os.path.join(DEFAULT_RECORDS, f"{job} - log (undone).csv")):
        return job, "already undone"
    return job, "no record"


def undo_from_drop(folder, no_prompt=False):
    """Handle a folder that is a job rather than a library. Always asks first.

    Culling asks before it moves anything and so must this: a drop is one
    gesture, easy to make by accident, and it moves photographs.
    """
    job, state = job_for_folder(folder)
    if job is None:
        if state in ("Culled Photos", "Reviews"):
            jobs = sorted(f[:-len(" - log.csv")] for f in os.listdir(DEFAULT_RECORDS)
                          if f.endswith(" - log.csv")) if DEFAULT_RECORDS and \
                os.path.isdir(DEFAULT_RECORDS) else []
            print(f"  that is all of {state}, not one job.")
            if jobs:
                print("  drop one of these:")
                for j in jobs:
                    print(f"    {j}")
            return True
        if state:
            print(f"  that is {state} \u2014 nothing to look through.")
            return True
        return False                           # not ours; carry on and cull it

    if state == "already undone":
        print(f"● {job}")
        print("  already undone.")
        return True
    if state == "no record":
        print(f"● {job}")
        print("  no log \u2014 analysed but never applied, so nothing to undo.")
        return True

    log = os.path.join(DEFAULT_RECORDS, f"{job} - log.csv")
    rows = list(csv.DictReader(open(log, errors="replace")))
    gb = 0.0
    for r in rows:
        try:
            gb += float(r.get("MB") or 0) / 1024
        except ValueError:
            pass
    print(f"● {job}")
    print(f"  a finished job \u00b7 {len(rows):,} "
          f"file{'' if len(rows)==1 else 's'} ({size_text(gb * 1e9)})")
    if no_prompt:
        print("  --no-prompt: not undone. Use --undo.")
        return True
    print(f"  put {len(rows):,} file{'' if len(rows)==1 else 's'} back?  [y/n] ",
          end="", flush=True)
    answer = ""
    while answer not in ("y", "n"):
        try:
            answer = read_key()
        except (EOFError, KeyboardInterrupt):
            answer = "n"
    print(answer)
    if answer != "y":
        print("  left alone.")
        return True
    undo(job)
    return True


# How far one "be pickier" or "cull more" step moves the limit. Big enough to
# change the answer, small enough that a couple of steps do not fly past the
# setting you wanted.
# The range runs 0 to 100 and always means the same thing. At 0 nothing is
# culled for merely looking alike — only what is provably a copy, which no
# setting can spare. At 100 every pair that can be aligned at all is a
# duplicate. Past about 41 the score stops sorting what a reviewer can tell apart
# from what he cannot, so up there the choice is taste.
# More than nine and choosing one takes two keypresses, which the menu would
# act on after the first.
MAX_OPTIONS = 5




def size_text(nbytes):
    """Bytes as text. GB only when it really is gigabytes."""
    return f"{nbytes/1e9:.1f} GB" if nbytes >= 1e9 else f"{nbytes/1e6:.0f} MB"


def wait_to_close(message):
    """Say what happened, then hold the window until the person is finished.

    A folder with nothing to decide would otherwise flash past and vanish,
    taking its account of what happened with it.

    Unless more folders are queued behind it: then nothing is vanishing, the
    next one is about to draw over it, and waiting is one keypress per folder
    for no reason.
    """
    print(f"  {message}")
    if os.environ.get("PHOTOCRULLER_MORE_QUEUED"):
        return
    print("  [q]uit")
    while True:
        try:
            if read_key() == "q":
                return
        except (EOFError, KeyboardInterrupt):
            print()
            return


def read_key():
    """One keypress, no Enter. Falls back to a whole line when piped.

    The cursor is hidden while waiting. Nothing is being typed — one key is
    being pressed — so a block parked on the line below the menu is just a
    smudge on the screen.
    """
    if not sys.stdin.isatty():
        line = sys.stdin.readline()
        if not line:
            raise EOFError                    # nothing left to read: stop asking
        return line.strip().lower()[:1]
    try:
        import termios, tty
    except ImportError:                       # Windows
        import msvcrt
        return msvcrt.getch().decode(errors="ignore").lower()
    fd = sys.stdin.fileno()
    saved = termios.tcgetattr(fd)
    hide = sys.stdout.isatty()
    try:
        if hide:
            sys.stdout.write("\033[?25l")
            sys.stdout.flush()
        tty.setcbreak(fd)
        ch = sys.stdin.read(1)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, saved)
        if hide:
            sys.stdout.write("\033[?25h")     # always give it back
            sys.stdout.flush()
    if ch in ("\x03", "\x04"):                # Ctrl-C, Ctrl-D still mean that
        raise KeyboardInterrupt
    return ch.lower()














def analyse(folder, opts):
    argv = [folder, "--recursive", "--exclude", WORKING_DIR,
            "--block", str(opts["block"]), "--ratio", str(opts["ratio"]),
            "--csv", opts["manifest"]]
    if opts.get("files"):
        argv += ["--files", opts["files"]]
    if not opts.get("auto"):
        argv += ["--fixed"]
    if opts.get("quiet", True):
        argv += ["--quiet"]
    if opts.get("no_summary"):
        argv += ["--no-summary"]
    return sift.main(argv)


# What round one may settle on its own, asked of the rules rather than listed
# here. A second list is a second thing to forget: adding a rule and leaving it
# out of the set would quietly send its culls to the review, or worse, adding a
# name here that no rule produces would promise something nothing delivers.
MECHANICAL = derived.SETTLED

#: One line each, for the summary a person reads before deciding to look.
REASONS = {rule.name: rule.says for rule in derived.ORDER}


def groups_from(folder, manifest):
    """Every group the plan would cull from, in capture order, for the review.

    A group is the unit a person actually decides about: these are the same
    photograph, which of them survives? Presenting it as pairs asks the same
    question once per cull and repeats the keeper in every one of them.

    Members are ordered by capture time so the review can step through them
    the way they were taken. The plan's choice of keeper travels with the
    group as a starting position, not as a decision.
    """
    members = defaultdict(list)
    for r in csv.DictReader(open(manifest)):
        if r["group"] != "":
            members[r["group"]].append(r)

    groups = []
    for gid, rows in members.items():
        if not any(r["verdict"] == "REDUNDANT" for r in rows):
            continue                      # nothing to decide here
        photos = []
        for r in rows:
            try:
                diff = float(r["block_pct"])
            except (KeyError, TypeError, ValueError):
                diff = None
            try:
                taken = float(r["taken"])
            except (KeyError, TypeError, ValueError):
                taken = 0.0
            photos.append({"file": r["file"],
                           "path": os.path.join(folder, r["file"]),
                           "keep": r["verdict"] == "KEEP",
                           "why": r["why"], "difference": diff, "taken": taken,
                           "size": r["MB"], "dimensions": r["dimensions"],
                           "because": r.get("why_inferior", "")})
        photos.sort(key=lambda p: (p["taken"], p["file"]))
        spread = [p["difference"] for p in photos if p["difference"] is not None]
        groups.append({"id": gid, "photos": photos,
                       "worst": max(spread) if spread else None})
    # Biggest first: the review is where a person spends attention, and the
    # group of twelve is where it buys the most. Ordering by least confident
    # was right when the question was "is this cull safe" — that question now
    # belongs to the rules, which cull only what they can prove, so what is
    # left here is a choice about which frames to keep. Ties break on the
    # widest difference, which is the group most worth a second look.
    groups.sort(key=lambda g: (-len(g["photos"]), -(g["worst"] or 0)))
    return groups






def gather_scenes(folder, opts):
    """The scenes in what survived round one, largest first.

    Built from the photographs themselves rather than from a plan. Round two
    proposes nothing, so there is nothing to write down before a person has
    spoken — no verdicts, no keeper, no marks of any kind. A scene is a set of
    photographs and the question attached to it.
    """
    files = sift.scan(folder, recursive=True, exclude=[WORKING_DIR])
    records = scenes.reading.records(files, note=progress)
    found = scenes.gather(records)

    groups = []
    for gi, members in enumerate(found):
        photos = []
        for i in members:
            r = records[i]
            dims = f"{r['w']}x{r['h']}" if r["w"] else ("raw sensor" if r["raw"] else "?")
            photos.append({"file": os.path.relpath(r["path"], folder),
                           "path": r["path"],
                           # Nothing is chosen yet, and nothing pretends to be.
                           "keep": False,
                           "why": "", "difference": None, "taken": r["t"],
                           "size": f"{r['bytes']/1e6:.1f}", "dimensions": dims,
                           "because": ""})
        groups.append({"id": gi, "photos": photos, "worst": None})
    return groups


def unkept(groups, answers):
    """The photographs a person did not keep, and how many scenes they judged.

    Keeping is the only thing anybody does in round two, so everything else is
    defined against it: what goes is what was not kept, in the scenes that were
    actually answered.

    A scene scrolled past says nothing, and nothing is what it costs — silence
    cannot move a photograph, which is the whole reason round two writes no
    marks of its own.
    """
    out, opened = [], 0
    for gi, g in enumerate(groups):
        said = answers.get(str(gi)) or {}
        # The page reports every scene, so "keep nothing" and "said nothing"
        # arrive looking alike — both with an empty list of keepers. Only the
        # first is a decision, and the page says which it was.
        # A scene is unreviewed, keeping some, keeping all, or keeping none.
        # Three of those can be read from the keepers; unreviewed cannot, since
        # it arrives looking exactly like keeping none. The page says which.
        if not said.get(review.REVIEWED):
            continue
        opened += 1
        kept = set(said.get("keep") or [])
        for photo in g["photos"]:
            if photo["file"] not in kept:
                out.append({"file": photo["file"], "why": "one of many",
                            "kept_instead": ", ".join(sorted(kept)[:2]),
                            "MB": photo["size"]})
    return out, opened


def revise_groups(manifest, groups, answers):
    """Rewrite the plan to match what the review said about each group.

    The answers name which photographs survive, so the plan is written from
    them directly rather than inferred: a group can end up keeping one, several,
    all of them, or none.
    """
    rows = list(csv.DictReader(open(manifest)))
    by_file = {r["file"]: r for r in rows}
    changed = emptied = 0
    # Keyed by position, as the page numbers them. The plan's own group ids are
    # not positions — the review is ordered least-confident first — so looking
    # answers up by id hands each group another group's verdicts.
    for gi, g in enumerate(groups):
        said = (answers.get(str(gi)) or {}).get("keep")
        if said is None:
            continue                      # never answered: the plan stands
        keep = set(said)
        for photo in g["photos"]:
            row = by_file.get(photo["file"])
            if row is None:
                continue
            want = "KEEP" if photo["file"] in keep else "REDUNDANT"
            if row["verdict"] != want:
                changed += 1
                row["verdict"] = want
                if want == "KEEP":
                    row["why"] = ""
                elif not row["why"]:
                    row["why"] = "near-duplicate"
        if not keep:
            emptied += 1
    with open(manifest, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]) if rows else [])
        w.writeheader()
        w.writerows(rows)
    return changed, emptied


def copies_first(folder, opts, session, job, a):
    """Settle the copies before anything is grouped. Returns False to stop.

    Two jobs, and only the second needs judgement. A copy is a copy — the
    picture is the same one, and which file holds it is a question about
    filenames rather than photographs — so those are settled first, on their
    own, with the reasons named. What survives goes on to be grouped, where
    every remaining decision is a matter of taste.

    Separating them also keeps the grouping honest: a folder holding three
    copies of every photograph groups strangely until they are gone.
    """
    # Every copy, not only the ones proven outright. A resave and a smaller
    # copy are as much "the same picture in another file" as a byte copy is,
    # but their labels are only given once a pair is already a member — so
    # asking at the floor would find the provable derivations and miss those.
    # Judged at the default and then filtered to what the rules can name.
    session["result"] = session["regroup"](sift.DUP_BLOCK, sift.DUP_RATIO)
    groups = []
    for g in groups_from(folder, opts["manifest"]):
        copies = [p for p in g["photos"] if p["keep"] or p["why"] in MECHANICAL]
        if len(copies) > 1 and any(not p["keep"] for p in copies):
            groups.append(dict(g, photos=copies))
    n = sum(sum(1 for p in g["photos"] if not p["keep"]) for g in groups)
    if not n:
        return True

    why = defaultdict(int)
    for g in groups:
        for photo in g["photos"]:
            if not photo["keep"]:
                why[photo["why"]] += 1
    freed = sum(float(r["MB"] or 0) for r in csv.DictReader(open(opts["manifest"]))
                if r["verdict"] == "REDUNDANT") * 1e6
    print(f"\n  ROUND ONE \u00b7 copies")
    print(f"  {n:,} file{'' if n == 1 else 's'} here came from another file "
          f"that is also here \u00b7 {size_text(freed)}")
    width = max(len(k) for k in why) if why else 0
    for kind, count in sorted(why.items(), key=lambda x: -x[1]):
        print(f"      {count:>4}  {kind:<{width}}   {REASONS.get(kind, '')}")
    print(f"\n  each one is provable, and named. nothing else is touched.")
    print("  [r]eview them  \u00b7  [a]pply  \u00b7  [s]kip  \u00b7  [q]uit")

    while True:
        try:
            key = read_key()
        except (EOFError, KeyboardInterrupt):
            print()
            return False
        if key in ("r", "a", "s", "q"):
            print(f"  > {key}")
            break
    if key == "q":
        return False
    if key == "s":
        return True
    if key == "r":
        action, answers = review.ask_groups(
            groups, opts["reviewdir"], f"{job} \u2014 {n:,} copies",
            "the same picture in more than one file \u00b7 the reason each "
            "one goes is under it")
        record_review(job, groups, answers, action or "closed", "copies")
        changed, _ = revise_groups(opts["manifest"], groups, answers)
        if changed:
            print(f"  you changed {changed} verdict(s)")
        if action != "apply":
            print("  no copies moved")
            return True

    moved, freed, extra = apply_moves(
        folder, opts["manifest"], DEFAULT_CULL,
        os.path.join(DEFAULT_RECORDS, job + " - thumbnails"), job)
    refresh_dashboard()
    print(f"  {moved:,} cop{'y' if moved == 1 else 'ies'} moved \u00b7 "
          f"{size_text(freed)}{extra}")
    return True


def record_review(job, groups, answers, action, setting, proposed=True):
    """Keep every judgement, whether or not anything moved.

    One row per photograph: what the tool proposed, what the person said, and
    the group it belonged to. An opinion about a photograph is the one thing
    here that cannot be worked out again, so it is written down before the
    decision it informed. Passes accumulate — looking at one round and then
    another is two opinions about the same folder.

    `proposed` says whether the tool put a plan up to be judged. Round one did,
    and the two columns can be compared: a difference is the tool being told it
    was wrong, which is the whole record of how far it can be trusted. Round
    two proposes nothing, so `planned` stays empty rather than reading `cull`
    for every photograph and turning each keeper into an override of a
    proposal nobody made.
    """
    if not DEFAULT_RECORDS:
        return
    stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    path = os.path.join(DEFAULT_RECORDS, f"{job} - review.csv")
    fresh = not os.path.exists(path)
    with open(path, "a", newline="") as fh:
        w = csv.writer(fh)
        if fresh:
            w.writerow(["judged_at", "setting", "action", "group", "file",
                        "planned", "you_said", "why", "difference", "reason"])
        for gi, g in enumerate(groups):
            said = answers.get(str(gi)) or {}
            keep = set(said.get("keep") or [])
            answered = "keep" in said
            for photo in g["photos"]:
                w.writerow([stamp, setting, action, g["id"], photo["file"],
                            ("keep" if photo["keep"] else "cull")
                            if proposed else "",
                            ("keep" if photo["file"] in keep else "cull")
                            if answered else "",
                            photo["why"],
                            "" if photo["difference"] is None
                            else round(photo["difference"], 1),
                            (said.get("reason") or "").strip()])
    return path


def job_name(folder, source=None):
    """Identifier shared by every output of one run: date + source folder.

    Two folders can share a name — Trips/2024 and Garden/2024 — so a
    job records the path it came from, and a clashing name from a different
    folder gets a number rather than quietly overwriting the first one's record.

    The same folder run twice reuses the job only while that job is still open,
    so that `--apply` writes into the run that planned it. Once a log exists the
    job is finished, and a fresh run starts a numbered one instead — otherwise a
    second pass over an already-culled folder finds nothing and overwrites the
    first run's plan with an empty file. That happened to eight of the trip jobs
    on a run of eight trip folders.

    `source` overrides what the marker records — a dropped selection stores a
    tag distinct from its parent folder's path, so a selection job can never be
    mistaken for (or resumed as) a run over the whole folder.
    """
    folder = os.path.abspath(folder.rstrip('/'))
    tag = source or folder
    base = f"{datetime.datetime.now():%Y.%m.%d} - {os.path.basename(folder) or 'cull'}" \
           + (" selection" if source else "")
    os.makedirs(DEFAULT_RECORDS, exist_ok=True)
    name, n = base, 1
    while True:
        marker = os.path.join(DEFAULT_RECORDS, f"{name} - source.txt")
        if not os.path.exists(marker):
            with open(marker, "w") as fh:
                fh.write(tag + "\n")
            return name
        same = open(marker).read().strip() == tag
        applied = os.path.exists(os.path.join(DEFAULT_RECORDS, f"{name} - log.csv"))
        if same and not applied:
            return name                      # same source, job still open: reuse
        n += 1
        name = f"{base} ({n})"


def find_open_job(folder):
    """The job for this folder that has a plan but no log yet, newest first.

    `--apply` needs this because job names carry the date: a plan made last
    night must still be applyable this morning, and applying must never mint a
    fresh (empty) job marker of its own.
    """
    folder = os.path.abspath(folder.rstrip('/'))
    hits = []
    if not os.path.isdir(DEFAULT_RECORDS):
        return None
    for f in os.listdir(DEFAULT_RECORDS):
        if not f.endswith(" - source.txt"):
            continue
        name = f[:-len(" - source.txt")]
        try:
            src = open(os.path.join(DEFAULT_RECORDS, f)).read().strip()
        except OSError:
            continue
        if (src == folder
                and os.path.exists(os.path.join(DEFAULT_RECORDS, f"{name} - plan.csv"))
                and not os.path.exists(os.path.join(DEFAULT_RECORDS, f"{name} - log.csv"))):
            hits.append(name)
    return max(hits) if hits else None


def retire_stale_plans(folder, keep):
    """A fresh analysis supersedes any older unapplied plan for the same folder.

    The old plan is renamed, not removed, so `--apply` can never act on stale
    analysis — dragging a folder in again means "look at it again", and only
    the newest look can be applied.
    """
    folder = os.path.abspath(folder.rstrip('/'))
    for f in os.listdir(DEFAULT_RECORDS):
        if not f.endswith(" - source.txt"):
            continue
        name = f[:-len(" - source.txt")]
        if name == keep:
            continue
        try:
            src = open(os.path.join(DEFAULT_RECORDS, f)).read().strip()
        except OSError:
            continue
        plan = os.path.join(DEFAULT_RECORDS, f"{name} - plan.csv")
        log = os.path.join(DEFAULT_RECORDS, f"{name} - log.csv")
        if src == folder and os.path.exists(plan) and not os.path.exists(log):
            os.rename(plan, os.path.join(DEFAULT_RECORDS, f"{name} - plan (superseded).csv"))
            print(f"note: an unapplied plan from {name.split(' - ')[0]} was superseded by this run")


def apply_moves(folder, manifest, dest_root, thumbs_dir, job):
    """Round one's move: everything its plan marked redundant.

    Round one proposes, so it has a plan with verdicts in it and this reads
    them. Round two proposes nothing and has no verdicts to read — it names
    what is leaving and calls move_out directly.
    """
    rows = [r for r in csv.DictReader(open(manifest)) if r["verdict"] == "REDUNDANT"]
    keeper = {r["group"]: r["file"] for r in csv.DictReader(open(manifest))
              if r["verdict"] == "KEEP"}
    for r in rows:
        r["kept_instead"] = keeper.get(r["group"], "")
    return move_out(folder, rows, dest_root, thumbs_dir, job)


def move_out(folder, leaving, dest_root, thumbs_dir, job):
    """Move these files to the holding folder, with a log that can undo it.

    `leaving` is a list of what goes, each carrying its file, the reason, and
    what is kept in its place. Nothing else is read — no plan, no verdicts —
    so a round that never proposed anything can still say what it is moving.
    """
    rows = leaving
    dest = os.path.join(dest_root, job)
    os.makedirs(dest, exist_ok=True)
    os.makedirs(thumbs_dir, exist_ok=True)
    log = os.path.join(DEFAULT_RECORDS, f"{job} - log.csv")
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    moved = missing = failed = 0
    freed = 0
    with open(log, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["moved_at", "from", "to", "why", "kept_instead", "MB"])
        for n, r in enumerate(rows, 1):
            progress(n, len(rows), "moving files")
            src = os.path.join(folder, r["file"])
            if not os.path.exists(src):
                missing += 1
                continue
            dst = os.path.join(dest, r["file"])
            try:
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                if os.path.exists(dst):
                    base, ext = os.path.splitext(dst); k = 2
                    while os.path.exists(f"{base} ({k}){ext}"):
                        k += 1
                    dst = f"{base} ({k}){ext}"
                # keep a small record of what left, so it can be identified later
                try:
                    th = open_image(src).convert("RGB")
                    th.thumbnail((320, 320))
                    # keep the subfolder in the name, or 2019/IMG_1.jpg and
                    # 2020/IMG_1.jpg silently overwrite each other's thumbnail
                    tname = r["file"].replace(os.sep, "__") + ".jpg"
                    th.save(os.path.join(thumbs_dir, tname), quality=70)
                except Exception:
                    pass
                size = os.path.getsize(src)
                try:
                    os.rename(src, dst)                  # same volume: instant
                except OSError:
                    shutil.move(src, dst)                # different volume: copy
                moved += 1; freed += size
                w.writerow([now, src, dst, r.get("why", ""),
                            r.get("kept_instead", ""), r.get("MB", "")])
                # A photo's sidecar (edits, ratings) is useless without it: it
                # travels along, and is logged so undo brings it back too. The
                # same goes for a Live Photo's paired video — an orphaned .mov
                # whose still was culled is junk the library would keep forever.
                stem = os.path.splitext(src)[0]
                for sc in (src + ".xmp", stem + ".xmp", stem + ".XMP",
                           src + ".aae", stem + ".aae", stem + ".AAE",
                           stem + ".mov", stem + ".MOV"):
                    if os.path.exists(sc):
                        sdst = os.path.join(os.path.dirname(dst),
                                            os.path.basename(sc))
                        kind = ("live photo video"
                                if sc.lower().endswith(".mov") else "sidecar")
                        try:
                            try:
                                os.rename(sc, sdst)
                            except OSError:
                                shutil.move(sc, sdst)
                            w.writerow([now, sc, sdst, kind,
                                        os.path.basename(src), ""])
                        except Exception:
                            pass
            except Exception as e:
                failed += 1
                print("  failed:", r["file"], str(e)[:60])
    # Applying is a judgement: the person saw the proof pairs and said yes.
    # Those approvals accumulate in one file, as labelled data.
    #
    # Known unsound and unfixed: this records every shown pair as approved,
    # including ones nobody looked at. Reviewing and applying are not the same
    # act, and no mechanism inside the folder can tell them apart — see the
    # wrong-direction note in docs/dead-ends.md.
    _label(job, now, "applied")
    extra = ""
    if missing:
        extra += f" \u00b7 {missing} already gone"
    if failed:
        extra += f" \u00b7 {failed} failed"
    return moved, freed, extra


def _header_of(path):
    """The column names a CSV already uses, or None if it has none."""
    try:
        with open(path, newline="") as fh:
            return next(csv.reader(fh), None)
    except OSError:
        return None


def _label(job, stamp, outcome, every=False):
    """Add this job's review to the ledger that spans every folder.

    A single review answers one folder. The ledger is what a threshold can be
    fitted against, so it needs them all, and it needs to know which were acted
    on: an undo takes the approval back rather than leaving the record claiming
    those culls were endorsed.

    A pass is one round's worth of answers: when it was judged, and which
    round asked. Both are needed. Two rounds applied inside the same second
    share a timestamp, and keyed on that alone they merge into one pass —
    round one's plan would then be scored against round two's preferences.

    An apply folds in the pass that was just answered, which is the last one
    written. An undo puts every photograph of the job back, so it retracts
    every pass, not the latest: retracting round two alone would leave round
    one's rows claiming culls were endorsed while those files sit restored.

    The ledger also needs to know which round asked. Round one's rows are the only
    evidence of how often the tool is wrong, because only there did it propose
    something a person could contradict. Round two's rows are preferences about
    photographs nobody claimed were copies. Counted together, every keeper in a
    scene reads as a cull the tool got wrong.
    """
    reviewed = os.path.join(DEFAULT_RECORDS, f"{job} - review.csv")
    if not os.path.exists(reviewed):
        return
    labels = os.path.join(DEFAULT_RECORDS, "labels.csv")
    header = ["date", "job", "round", "group", "file", "planned", "you_said",
              "why", "difference", "reason", "outcome"]
    fresh = not os.path.exists(labels)
    if not fresh and _header_of(labels) != header:
        # The ledger is a record of somebody's opinions, and appending rows
        # shaped differently from the ones already there silently ruins every
        # one of them. Set the old file aside intact instead.
        aside = os.path.join(DEFAULT_RECORDS, "labels (earlier format).csv")
        n = 2
        while os.path.exists(aside):
            aside = os.path.join(DEFAULT_RECORDS,
                                 f"labels (earlier format {n}).csv")
            n += 1
        os.rename(labels, aside)
        print(f"  the label ledger changed shape \u00b7 the old one is kept as "
              f"{os.path.basename(aside)}")
        fresh = True
    try:
        with open(labels, "a", newline="") as fh:
            w = csv.writer(fh)
            if fresh:
                w.writerow(header)
            rows = list(csv.DictReader(open(reviewed)))
            # A review written before the ledger changed shape has different
            # columns. Its judgements are real and are kept as they are; only
            # the ones this ledger can read are folded in.
            rows = [r for r in rows if "group" in r and "file" in r]
            # Only the pass that was acted on. Looking at one round and then
            # another appends both, and marking the abandoned one "applied"
            # would put culls in the ledger that never happened. Rows are
            # appended in the order they were judged, so the last row names
            # the pass just answered.
            def _pass(r):
                return (r["judged_at"], r.get("setting", ""))

            last = _pass(rows[-1]) if rows else None
            for r in rows:
                if not every and _pass(r) != last:
                    continue
                w.writerow([stamp, job, r.get("setting", ""), r["group"],
                            r["file"], r["planned"], r["you_said"], r["why"],
                            r["difference"], r["reason"], outcome])
    except OSError:
        pass


def reset(no_prompt=False):
    """Put every photograph back and clear everything the tool has produced.

    For starting again from nothing: after a change to how culls are decided,
    or simply to be sure that what a run reports was worked out from the
    photographs rather than from something cached.

    Everything cached goes: what was read from each photograph, every pairwise
    verdict, every keypoint screen. That is the point — a run afterwards works
    everything out again from the photographs, so what it reports cannot have
    come from something stale.

    Judgements are never deleted. Everything else here can be produced again
    from the library, and a judgement cannot: it is somebody's opinion about
    two photographs, and there is no way back to it except asking again.

    Asks first, always. It moves photographs.
    """
    jobs = sorted(f[:-len(" - log.csv")] for f in os.listdir(DEFAULT_RECORDS)
                  if f.endswith(" - log.csv")) if os.path.isdir(DEFAULT_RECORDS) else []
    to_restore = 0
    for job in jobs:
        try:
            to_restore += sum(1 for _ in csv.DictReader(
                open(os.path.join(DEFAULT_RECORDS, f"{job} - log.csv"))))
        except OSError:
            pass

    def weigh(path):
        total = 0
        for dp, _, fn in os.walk(path):
            for f in fn:
                try:
                    total += os.path.getsize(os.path.join(dp, f))
                except OSError:
                    pass
        return total

    cache = os.path.join(WORKING_DIR, "Cache")
    reviews = DEFAULT_REVIEWS
    print(f"  {len(jobs)} applied job{'' if len(jobs) == 1 else 's'} to undo, "
          f"{to_restore:,} photograph{'' if to_restore == 1 else 's'} to put back")
    print(f"  {size_text(weigh(cache))} of cache \u2014 what was read from each "
          f"photograph, every pairwise verdict, every keypoint screen")
    print(f"  {size_text(weigh(reviews))} of review pages")
    print("  judgements are kept")
    if not no_prompt:
        print("  reset everything? [y]es  [n]o")
        while True:
            try:
                k = read_key()
            except (EOFError, KeyboardInterrupt):
                print("\n  left alone")
                return
            if k == "n":
                print("  left alone")
                return
            if k == "y":
                break

    for job in jobs:
        print(f"\n● {job}")
        undo(job, hint=False)      # the plan is about to be cleared too

    # Only what a run produces is cleared, named exactly. Everything else in
    # Records is somebody's judgement, or something unrecognised — and an
    # unrecognised file is kept. Deleting what you cannot name is how evidence
    # goes missing.
    made_by_a_run = (" - plan.csv", " - log.csv", " - log (undone).csv",
                     " - source.txt", " - settings.txt",
                     " - thumbnails")
    removed = 0
    for f in sorted(os.listdir(DEFAULT_RECORDS)) if os.path.isdir(DEFAULT_RECORDS) else []:
        if not any(f.endswith(suffix) for suffix in made_by_a_run):
            continue
        path = os.path.join(DEFAULT_RECORDS, f)
        try:
            shutil.rmtree(path) if os.path.isdir(path) else os.remove(path)
            removed += 1
        except OSError:
            pass

    for path in (cache, reviews, DEFAULT_CULL):
        if os.path.isdir(path):
            shutil.rmtree(path, ignore_errors=True)
        os.makedirs(path, exist_ok=True)

    refresh_dashboard()
    print(f"\n  reset · {to_restore:,} photograph"
          f"{'' if to_restore == 1 else 's'} back in place · "
          f"{removed} run record{'' if removed == 1 else 's'} cleared · "
          f"judgements kept")


def prune_empty(dest):
    """Leave no empty scaffolding behind in Culled Photos.

    A restore moves files out but not the directories they sat in, so an
    emptied job folder would squat in Culled Photos looking like a job.
    Finder drops `.DS_Store` into every folder it opens, which counts as
    empty — it is the reason a large undo once left its whole
    directory tree behind.
    """
    for dp, dn, fn in os.walk(dest, topdown=False):
        entries = os.listdir(dp)
        if all(e == ".DS_Store" for e in entries):
            for e in entries:
                try:
                    os.remove(os.path.join(dp, e))
                except OSError:
                    pass
            try:
                os.rmdir(dp)
            except OSError:
                pass


def undo(job, hint=True):
    """Put every file a job moved back where it came from, from its log.

    The log is the authority: each row records `from` and `to`. Afterwards the
    log is renamed `log (undone).csv` — the history is kept, but the job counts
    as open again, so the dashboard stops crediting it and the still-valid plan
    could be re-applied.
    """
    log = os.path.join(DEFAULT_RECORDS, f"{job} - log.csv")
    if not os.path.exists(log):
        done = sorted(f[:-len(" - log.csv")] for f in os.listdir(DEFAULT_RECORDS)
                      if f.endswith(" - log.csv"))
        sys.exit("no log for a job called: " + job +
                 ("\njobs that can be undone:\n  " + "\n  ".join(done) if done
                  else "\nno applied jobs found."))
    rows = list(csv.DictReader(open(log)))
    restored = missing = occupied = 0
    for n, r in enumerate(rows, 1):
        progress(n, len(rows), "restoring files")
        src, dst = r["to"], r["from"]          # reversed on purpose
        if not os.path.exists(src):
            missing += 1
            continue
        if os.path.exists(dst):
            occupied += 1                       # never overwrite; report instead
            continue
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        try:
            os.rename(src, dst)
        except OSError:
            shutil.move(src, dst)
        restored += 1
    os.rename(log, os.path.join(DEFAULT_RECORDS, f"{job} - log (undone).csv"))
    prune_empty(os.path.join(DEFAULT_CULL, job))
    print(f"\n  restored {restored:,} of {len(rows):,}")
    if missing:
        print(f"  {missing:,} already gone")
    if occupied:
        print(f"  {occupied:,} skipped \u2014 something is already there")
    if hint:
        print("  the plan stands; --apply would move them again")
    # The photographs are back and said to be back before any of this runs. An
    # undo's job is to move files; bookkeeping that fails afterwards must not
    # be able to make a finished undo look like a crash.
    try:
        _label(job, datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
               "retracted by undo", every=True)
    except Exception as e:
        print(f"  \u26a0 the label ledger was not updated: {str(e)[:60]}")
    refresh_dashboard()


def choose_folder(prompt):
    """A native folder-picker dialog; None if unavailable or cancelled.

    macOS gets AppleScript's chooser, Windows gets the PowerShell folder
    dialog. Both have a New Folder button, so 'create it first' is not a
    step the person has to know about.
    """
    safe = prompt.replace('"', "'")
    try:
        if sys.platform == "darwin":
            r = subprocess.run(
                ["osascript", "-e",
                 'tell application "System Events" to activate',
                 "-e", f'POSIX path of (choose folder with prompt "{safe}")'],
                capture_output=True, text=True, timeout=600)
            if r.returncode == 0 and r.stdout.strip():
                return r.stdout.strip()
        elif sys.platform == "win32":
            ps = ("Add-Type -AssemblyName System.Windows.Forms; "
                  "$d = New-Object System.Windows.Forms.FolderBrowserDialog; "
                  f"$d.Description = '{safe}'; "
                  "if ($d.ShowDialog() -eq 'OK') { Write-Output $d.SelectedPath }")
            r = subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                               capture_output=True, text=True, timeout=600)
            if r.returncode == 0 and r.stdout.strip():
                return r.stdout.strip()
    except Exception:
        pass
    return None


def refresh_dashboard():
    """Keep the one-page picture in the working folder current after every run."""
    try:
        subprocess.run([sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                                     "dashboard.py")],
                       capture_output=True, timeout=120)
    except Exception:
        pass


def reclaimed_total():
    """All-time GB in PhotoCruller, from the logs. Small files; fast enough."""
    gb = 0.0
    try:
        for f in os.listdir(DEFAULT_RECORDS):
            if f.endswith(" - log.csv"):
                for r in csv.DictReader(open(os.path.join(DEFAULT_RECORDS, f),
                                              errors="replace")):
                    try:
                        gb += float(r.get("MB") or 0) / 1024
                    except ValueError:
                        pass
    except OSError:
        pass
    return gb


def main():
    ap = argparse.ArgumentParser(description="Find redundant photos and move them out. Nothing is deleted.")
    ap.add_argument("folder", nargs="?")
    ap.add_argument("--reset", action="store_true",
                    help="undo every applied job and clear caches, reviews "
                         "and plans; judgements are kept")
    ap.add_argument("--undo", metavar="JOB",
                    help='reverse an applied job from its log, by its name')
    ap.add_argument("--files", metavar="LIST", default=None,
                    help="judge only the files named in LIST, one path per line "
                         "— how the app hands over a dropped selection")
    ap.add_argument("--block", type=float, default=None, metavar="N",
                    help="round one's difference limit (0-100); the default "
                         "is what every measurement here was made at")
    ap.add_argument("--ratio", type=float, default=None, metavar="N",
                    help="the texture-relative limit that moves with --block; "
                         "set both or neither")
    ap.add_argument("--apply", action="store_true", help="move the redundant files out")
    ap.add_argument("--no-prompt", action="store_true", help="never ask; just report")
    ap.add_argument("--verbose", action="store_true",
                    help="full diagnostics: thresholds and comparison counts")
    a = ap.parse_args()

    if a.reset:
        if WORKING_DIR is None:
            sys.exit("no working folder set yet, so there is nothing to reset")
        reset(no_prompt=a.no_prompt)
        return

    if a.undo:
        if WORKING_DIR is None:
            sys.exit("no working folder configured; nothing to undo from.")
        target = a.undo.strip()
        # A path is as good as a name: --undo accepts what you would have
        # dragged, so a name copied out of Finder works without editing.
        if os.path.isdir(target):
            job, _ = job_for_folder(os.path.abspath(target.rstrip('/')))
            if job:
                target = job
        undo(target)
        return
    if not a.folder and not a.files:
        ap.error("a folder is required (or --undo JOB, or --files LIST)")

    sel = None
    if a.files:
        # A dropped selection of photos rather than a folder. The plan is made
        # over exactly these files; their common parent stands in as the folder
        # so every record and relpath works as usual.
        if a.apply:
            sys.exit("a selection is applied from its review page; drop the "
                     "files again to look at them")
        with open(a.files) as fh:
            sel = [os.path.abspath(ln.rstrip("\n")) for ln in fh if ln.strip()]
        sel = [p for p in sel if os.path.isfile(p)]
        if not sel:
            sys.exit("none of the dropped items are files that exist")
        folder = os.path.commonpath([os.path.dirname(p) for p in sel])
    else:
        folder = os.path.abspath(a.folder.rstrip('/'))
        if not os.path.isdir(folder):
            sys.exit("no such folder: " + folder)
        # Dropped a folder from inside the working folder? That is not a request
        # to cull it. Usually it means "put this job back"; either way, culling
        # the tool's own output would be wrong.
        if WORKING_DIR is not None and undo_from_drop(folder, a.no_prompt):
            return
        if sift.is_library_package(folder):
            sys.exit(
                "that is a photo library managed by an app (Photos,\n"
                "Lightroom), not a folder of files. Culling inside it would\n"
                "corrupt the library. Export the photos to a plain folder\n"
                "first, then point PhotoCruller at that.")
    if WORKING_DIR is None:
        # First run on this machine: ask once, remember it. One working
        # folder, chosen before anything runs. A real folder dialog, because
        # nobody should have to type a path to answer "where should this go?".
        print("PhotoCruller needs one folder for what it produces \u2014")
        print("culled photos, reviews and records. Never your library.")
        wd = choose_folder(
            "Choose PhotoCruller's working folder — it will hold culled "
            "photos, reviews and records. Not your photo library.")
        if not wd and sys.stdin.isatty():           # dialog unavailable or cancelled
            wd = input("Working folder (will be created if needed): ").strip().rstrip(os.sep)
        if not wd:
            sys.exit("no working folder chosen; not running.")
        wd = os.path.abspath(os.path.expanduser(wd))
        os.makedirs(wd, exist_ok=True)
        config.save_working(wd)
        set_working(wd)
        print(f"working folder: {wd}\n")
    wd = os.path.abspath(WORKING_DIR)
    if sel:
        inside = [p for p in sel if p == wd or p.startswith(wd + os.sep)]
        if inside:
            print(f"  ({len(inside)} dropped file{'' if len(inside)==1 else 's'} "
                  f"live in the working folder — already culled, skipped)")
            sel = [p for p in sel if p not in set(inside)]
        if not sel:
            sys.exit("everything dropped was already-culled output; nothing to do.")
        folder = os.path.commonpath([os.path.dirname(p) for p in sel])
    if folder == wd or folder.startswith(wd + os.sep):
        sys.exit("that folder is inside the working folder — it holds files already "
                 "culled,\nnot a library to cull. Nothing to do here.")
    if wd.startswith(folder + os.sep):
        # Scanning a parent of the working folder is how cross-folder redundancy
        # is found — the tool's output just isn't part of the library.
        print(f"  ({os.path.basename(wd)} is inside this tree; skipped)")
    opts = dict(block=sift.DUP_BLOCK, ratio=sift.DUP_RATIO)
    opts["auto"] = (a.block is None and a.ratio is None)
    if a.block is not None: opts["block"] = a.block
    if a.ratio is not None: opts["ratio"] = a.ratio
    opts["quiet"] = not a.verbose
    os.makedirs(DEFAULT_RECORDS, exist_ok=True)
    # Applying resumes the job that planned — even if that was yesterday.
    # Only analysing may start a new one; job_name() creates the marker.
    if sel:
        digest = hashlib.md5("\n".join(sorted(sel)).encode()).hexdigest()[:8]
        job = job_name(folder, source=f"{folder} (selection {digest})")
        fd, lst = tempfile.mkstemp(prefix="photocruller_selection_", suffix=".txt")
        with os.fdopen(fd, "w") as fh:
            fh.write("\n".join(sel) + "\n")
        opts["files"] = lst
    else:
        job = find_open_job(folder) if a.apply else job_name(folder)
        if a.apply and not job:
            sys.exit("no open plan for this folder — run without --apply first, "
                     "and open the review")
        if not a.apply:
            retire_stale_plans(folder, keep=job)   # re-dragging a folder = fresh look
    opts["manifest"] = os.path.join(DEFAULT_RECORDS, f"{job} - plan.csv")
    opts["reviewdir"] = os.path.join(DEFAULT_REVIEWS, job)

    print(f"\n\u25cf {os.path.basename(folder)}"
          + (f" \u2014 a selection of {len(sel)} files" if sel else ""))
    if a.verbose and not opts["auto"]:
        print(f"  limit {opts['block']:.0f}/{opts['ratio']:.0f}, set by hand")
    apply_hint = (f'apply with:  ./crull "{folder}" --apply' if not sel else
                  "a selection applies from its review page \u2014 drop the "
                  "files again to look again")

    if a.apply:
        moved, freed, extra = apply_moves(
            folder, opts["manifest"], DEFAULT_CULL,
            os.path.join(DEFAULT_RECORDS, job + " - thumbnails"), job)
        refresh_dashboard()
        print(f"  done \u00b7 {moved:,} moved \u00b7 {size_text(freed)} \u00b7 "
              f"{os.path.basename(WORKING_DIR)} holds "
              f"{reclaimed_total():.1f} GB{extra}")
        return

    interactive = sys.stdin.isatty() and not a.no_prompt
    opts["no_summary"] = interactive
    session = analyse(folder, opts)
    total_pairs = sum(1 for r in csv.DictReader(open(opts["manifest"]))
                      if r["verdict"] == "REDUNDANT")
    if not total_pairs and not (interactive and session):
        if interactive:
            wait_to_close("no copies, nothing to group")
        return

    if interactive and session is None:
        # No options list is coming, so this is the only account of the run.
        wait_to_close(f"{total_pairs:,} could go \u00b7 {apply_hint}")
    elif interactive:
        if not copies_first(folder, opts, session, job, a):
            return
        # ROUND TWO — the scenes there are too many photographs of.
        #
        # A different question from round one, so nothing here proposes a cull.
        # The copies are gone; what is left is read again and gathered into
        # scenes, each one shoot's worth of one subject. The largest opens
        # first, because that is the thing there are most of.
        print(f"\n  ROUND TWO \u00b7 scenes")
        groups = gather_scenes(folder, opts)
        if not groups:
            print("  nothing gathers into a scene \u00b7 nothing more to do")
            return
        n_photos = sum(len(g["photos"]) for g in groups)
        biggest = len(groups[0]["photos"])
        print(f"  {len(groups):,} scene{'' if len(groups) == 1 else 's'} \u00b7 "
              f"{n_photos:,} photographs \u00b7 the biggest holds {biggest}")
        print(f"  nothing is chosen for you here. keep what you want from each;")
        print(f"  a scene you do not review is left alone.\n")

        action, answers = review.ask_groups(
            groups, opts["reviewdir"],
            f"{job} \u2014 {len(groups):,} scenes, {n_photos:,} photographs",
            "one scene at a time, biggest first \u00b7 keep what you want and "
            "the rest of that scene moves out \u00b7 a scene you skip is left "
            "whole",
            proposed=False)
        record_review(job, groups, answers, action or "closed", "scenes",
                      proposed=False)

        going, opened = unkept(groups, answers)
        skipped = len(groups) - opened
        if skipped:
            print(f"  {skipped:,} scene{'' if skipped == 1 else 's'} unreviewed "
                  f"\u00b7 left whole")
        if not going:
            print("  nothing to move \u00b7 you kept everything you looked at")
            return
        if action != "apply":
            print("  nothing moved \u00b7 your answers are kept")
            return

        moved, freed, extra = move_out(
            folder, going, DEFAULT_CULL,
            os.path.join(DEFAULT_RECORDS, job + " - thumbnails"), job)
        refresh_dashboard()
        print(f"  done \u00b7 {moved:,} moved \u00b7 {size_text(freed)} \u00b7 "
              f"{os.path.basename(WORKING_DIR)} holds "
              f"{reclaimed_total():.1f} GB{extra}")
        print(f'  to change your mind: --undo "{job}", or drop '
              f'that folder from Culled Photos on the app')
    else:
        print(f'  review, then: {apply_hint}')


def log_error():
    """Put the traceback in a file and say one plain line on screen.

    A stack trace answers a question nobody culling photographs is asking, and
    it buries the one fact that matters: nothing was moved. The detail still
    has to survive, so it goes to a log that can be read or sent on.
    """
    import datetime
    import traceback
    where = DEFAULT_RECORDS or os.path.dirname(os.path.abspath(__file__))
    path = None
    try:
        os.makedirs(where, exist_ok=True)
        path = os.path.join(where, "errors.log")
        with open(path, "a") as fh:
            fh.write("\n" + "=" * 72 + "\n")
            fh.write(f"{datetime.datetime.now():%Y-%m-%d %H:%M:%S}  "
                     f"{' '.join(sys.argv)}\n")
            traceback.print_exc(file=fh)
    except OSError:
        path = None                       # nowhere to write; the line below still lands
    print("\n  something went wrong \u2014 nothing was moved")
    if path:
        print(f"  the details are in {path}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print()                           # a deliberate stop is not an error
    except Exception:
        log_error()
        sys.exit(1)
