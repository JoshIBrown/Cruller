# Running PhotoCruller yourself

## One-time setup

Double-click **mac_install.command** in this folder. Re-run it after any change
that mentions new libraries — it is safe to run as often as you like.

If macOS refuses ("no permission", or nothing happens) — which occurs when the
folder arrived via Dropbox or a download, both of which strip the run
permission — open Terminal, type `bash ` (with the space), drag
mac_install.command into the window, and press Enter. That works regardless, and
the script then repairs the permissions on itself and on `crull` for good.

One command: installs the Python libraries, builds `PhotoCruller.app`, and checks
that each library imports. You should see `numpy`, `PIL` and `cv2` reported as
ok. HEIC support is optional — without it, iPhone HEIC files are skipped and
the run says so.

What the libraries are for, in case one ever needs attention:

| Library | Needed for | Without it |
|---|---|---|
| `numpy` | **Required.** All image math — comparing photographs, ranking them, sharpness | The tool won't start |
| `pillow` | **Required.** Reading JPEG/PNG/TIFF, raw previews, review images | The tool won't start |
| `opencv-python-headless` | **Required.** Aligning two frames and judging what changed — the core of every decision | Falls back to the coarse thumbnail test, which is what the 07-29 rewrite replaced. Install it |
| `pillow-heif` | iPhone HEIC/HEIF photos | HEIC files are skipped, with a note in the run |

The tool has one setting: the working folder, where everything it produces
goes. The first time you run or drop anything, a folder dialog asks you to
choose it (make a new folder right in the dialog if you like) — answered once,
remembered in `scripts/settings.conf`. Clicking the PhotoCruller.app icon with
nothing dropped asks which folder of photos to look through, the same way.

## Using it — the tested way

Two commands per folder.

**1. Look:**

    ./crull "/path/to/some/photos"

Changes nothing on its own. It reads the folder, settles the copies it can
prove, and gathers the rest into scenes for you to choose from.

While it works you'll see a progress bar for each stage:

    checking files         [################################] 100%  5,000/5,000
    reading photos         [##########################------]  83%  4,150/5,000
    comparing photos       [#########-----------------------]  28%  1,400/5,000   4m10s left
    grouping by scene      [################################] 100%

### Round one — the copies

Where one file came from another that is also here, a rule names it. Ten rules,
and each says what is wrong with the file being removed rather than how the two
are related, so the list reads as instructions:

    ROUND ONE · copies
    21 files here came from another file that is also here · 118 MB
           8  crop        a crop of the frame being kept
           7  resave      the same picture, more heavily compressed
           5  smaller     the same picture at a lower resolution
           1  rotated     a quarter turn of it, with the orientation flag reset

    each one is provable, and named. nothing else is touched.
    [r]eview them  ·  [a]pply  ·  [s]kip  ·  [q]uit

One keypress, no Enter. **r** opens the same page round two uses, with the
tool's plan already in it, so you can disagree with any of it. **a** takes the
plan as it stands. **s** leaves the copies alone and goes on to the scenes.

Every one of these has been checked against your own library — 279 culls across
ten folders, none of them wrong — which is why looking is optional here and not
in round two.

### Round two — the scenes

What survived is gathered into scenes: one shoot's worth of one subject. A
shoot is photographs within ninety minutes of each other, and a scene is the
ones inside it that look alike.

    ROUND TWO · scenes
    44 scenes · 209 photographs · the biggest holds 31
    nothing is chosen for you here. keep what you want from each;
    a scene you do not review is left alone.

A page opens with **one section per scene, biggest first** — the scene there are
most photographs of is where your attention buys the most. Every photograph of a
scene is on screen at once, in the order they were taken, because choosing
between thirty frames means looking back and forth between them.

Click a photograph to keep it. **keep all** and **keep none** decide a whole
scene at once.

Each scene shows which of four states it is in: **unreviewed**, **keeping
some**, **keeping all**, **keeping none**. Unreviewed is the important one — it
looks exactly like keeping none and means the opposite — so it is shown rather
than guessed at, dimmed with a grey edge, against green for a scene you have
decided. **An unreviewed scene cannot lose a photograph.**

At the bottom: **Move what I did not keep** moves the rest of every scene you
reviewed. **Quit** moves nothing. Both write down every judgement.

## How it decides two photos are the same — round one

Every judgement is made by lining the two frames up — rotation, zoom and
perspective, not just a shift — and then looking at what is left over, at a
resolution where things you care about are still visible.

That sounds obvious, and it is not what a naive comparison does. A naive one decides
on a thumbnail 256 pixels wide. A face in a group shot is twenty pixels there,
so two frames of the same person with completely different expressions measured
**4.5% different** — well inside "identical". The same pair, lined up and read
properly, measures **62%**.

Two frames of the same person doing the same thing are still duplicates, and the
redundant one still goes. That part has not changed.

Most pairs never get that far. A thumbnail throws out anything nowhere near a
match, then a keypoint check throws out anything that is not the same scene —
neither of which opens the photograph at all. Only what survives both is read
properly. That is what keeps a folder of bursts affordable.

**When it can't line two frames up** — a bird against blank sky, an eclipse
against black, anything too dark or too smooth to find landmarks in — it says so
and keeps both. It would rather leave you two photos than cull on a guess.

## How it gathers a scene — round two

None of the above. Round two asks a softer question — *have I taken too many of
this?* — and the machinery that answers "are these the same photograph" answers
it badly. On a folder of 8,000 nature photographs, the longest burst in it came
out as no group at all: fifty-five frames of a bird in flight, and no two of
them the same photograph.

So a scene is built from two cheap things instead. **One shoot:** photographs
within ninety minutes of each other, a number taken from your own library —
the gaps between shots run smoothly with no natural cliff until about ninety
minutes, where the biggest jump sits and 96% of gaps fall below. **One scene:**
within a shoot, a photograph joins when it looks like the scene's *average*, not
like whichever frame sits next to it. That is what lets a sunset stay whole
while its colour moves, and an eagle stay whole while it turns its head — and
what stops a scene wandering off into unrelated photographs one step at a
time.

## Changed your mind?

**Drag the job's folder out of `Culled Photos` and drop it on
PhotoCruller.app.** The tool recognises its own output, tells you what the job was
and how many files it holds, and asks before putting anything back:

    ● 2024.03 - Holiday
      a finished job — 1,204 files (18.3 GB) can go back where they came from.
      put 1,204 files back?  [y/n]

Dropping a folder from *inside* one of those jobs works too — it finds the job
it belongs to.

It offers two things. **Review it again** rebuilds both rounds exactly as you
decided them: every group still assembled, every photograph marked with where
it actually is now. Change your mind about any one of them — tick a photograph
that went, untick one that stayed — and pressing the button moves that file and
nothing else. A change of mind is itself logged, so it can be undone tomorrow
like anything else.

**Undo the job** is the blunt instrument, still there: it puts back everything
that job moved, exactly where it came from, using the job's own log. Nothing is
overwritten; anything that can't go back is reported.

By name, if you prefer typing:

    ./crull --undo "<job name>"

Run it with a wrong name and it lists the jobs that can be undone.

Nothing is stored to make the review reopen. The pages are built when you ask
for them, out of the review and the log the job already keeps, so what they
show is the folder as it is rather than a third account of it that is free to
go stale. Each job keeps its own, so any number of finished folders can be
looked through again.

## Anything else

    ./crull --dashboard     refresh PhotoCruller.html
    ./crull --help

**Running without being asked anything.** Two ways, for scripting and for
measurement:

    ./crull "/folder" --block 32 --ratio 21.9    judge at exactly this limit
    ./crull "/folder" --no-prompt                report and stop, never ask

`--block` is round one's difference limit, 0-100,
given directly, so a plan can be reproduced later without anyone answering
anything. `--ratio` is the texture-relative limit that normally moves with it;
set both or neither. Neither moves a file on its own — `--apply` still does
that. `--no-prompt` skips every question, including the one before an undo.


## On Windows

Same tool, two different starters: double-click **pc_install.bat** once (needs
Python from python.org, with "Add to PATH" ticked during its install), then
**drag a photo folder onto pc_crull.bat** — Windows treats that as running it on
that folder. First run pops the working-folder dialog, same as Mac. The review
opens in your default browser; everything else is identical. No PhotoCruller.app on
Windows — the .bat file IS the drop target. (Built blind from a Mac; if
anything misbehaves, say what it printed.)

## The drag-and-drop version

Drag a photo folder onto `PhotoCruller.app` (built by `./mac_install.command`) and a Terminal
window opens sized to the tool, cleared, and runs the cull there — progress
bars, both rounds, and the review page before anything moves.

**Dropping several folders at once** is fine: they queue and run one at a time
in a single window. Drop more while it's running and they join the end.

**Dropping loose files works too** — select any photos in Finder and drop the
selection on the app. They are judged together as one set, named `<date> -
<their folder> selection` in the records. One difference from a folder run:
`--apply` cannot be pointed at a selection afterwards, so it is applied from
its own review page — to look again later, drop the same files again. Anything
dropped that isn't a photo is skipped with a note.

**Dropping when nothing is running always starts fresh.** Tickets left behind
by an interrupted session are discarded; only what you just dropped runs.

**Dropping a folder from the working folder means looking at it again**, never
culling — see "Changed your mind?" above. The tool will not cull its own
output.

**Rebuilds are rarely needed.** The app runs the live scripts, so code changes
reach it immediately; only a change to the drop-handling inside
`mac_install.command` needs `./mac_install.command` re-run.

## What a run looks like

    ./crull "/some/folder"

    ● 2020.01 - NYC
      reading photos    [############--------------------]  38%  1,900/5,000   1m20s left
      comparing photos  [################################] 100%  145/145      2m04s

      ROUND ONE · copies
      21 files here came from another file that is also here · 118 MB
             8  crop        a crop of the frame being kept
             7  resave      the same picture, more heavily compressed
             5  smaller     the same picture at a lower resolution
             1  rotated     a quarter turn of it, with the orientation flag reset

      each one is provable, and named. nothing else is touched.
      [r]eview them  ·  [a]pply  ·  [s]kip  ·  [q]uit
      > a
      21 copies moved · 118 MB

      ROUND TWO · scenes
      grouping by scene [################################] 100%
      44 scenes · 209 photographs · the biggest holds 31
      nothing is chosen for you here. keep what you want from each;
      a scene you do not review is left alone.

      review open in your browser — http://127.0.0.1:52118/index.html
      12 scenes unreviewed · left whole
      done · 71 moved · 0.9 GB · Photo Bin holds 12.4 GB

Round one is a single keypress — no Enter. Round two opens a page in your
browser, biggest scene first, and everything after that happens there. Quit it
and nothing moves.

**Nothing closes on its own.** A folder with nothing in it still waits for `q`,
so a run can never flash past before you have read what it found. Dropped onto
the app, the window closes once you have quit every folder in the queue.
`--verbose` restores the full diagnostics when something needs debugging.

## If something looks wrong

**In round one**, a copy you disagree with can be answered on the spot: click
the frame you would rather keep, or keep both and the pair is left alone.

**In round two** there is nothing to disagree with — the tool has chosen
nothing. If a scene has gathered badly, keep everything in it with **keep all**
and it is left whole, or simply skip it: an unreviewed scene loses nothing.

Scenes that gather badly are worth telling me about. Too loose and unrelated
photographs arrive together; too tight and one burst becomes four. There is no
measurement for either — only looking at them.

Nothing is at stake in getting it wrong the first time. `--undo` reverses an
applied job completely — files, sidecars and videos alike.

## Starting again from nothing

    ./crull --reset

Puts every photograph an applied job moved back where it came from, then clears
everything the tool has produced: the cache, the review pages, the plans and
logs. It asks first and tells you what it is about to do.

Your judgements are never deleted, and neither is anything else it does not
recognise — only the files a run itself produces. Everything cleared can be
worked out again from your photographs; a judgement cannot.

Worth doing after the tool changes how it decides, or any time you want to be
sure a run's answer came from the photographs rather than from something
remembered.

## How often is it wrong?

**Round one** can be checked exactly, because its claim is either true or false:
this file came from that one. It has been. Across ten folders, all 279 of its
culls were either verified without the tool's help — every `identical` decoded
and compared pixel by pixel, every `smaller` checked by shrinking the keeper —
or looked at by eye. None was wrong.

**Round two** has no error rate, because it decides nothing. Its mistake is a
scene gathered badly, and the only test for that is opening one.

## What it will not do

- Delete anything. Ever. Emptying `Culled Photos` is your decision
  alone, made in the Finder.
- Touch the folder it scans, other than removing files you approved moving.
- Judge that five distinct sunsets are redundant because you only need one.
  That's taste, and it isn't trying.
