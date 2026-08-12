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

Changes nothing on its own. It works out what it would move, then hands you
the settings and the review.

While it works you'll see a progress bar for each stage:

    checking files         [################################] 100%  5,000/5,000
    reading photos         [##########################------]  83%  4,150/5,000
    comparing photos       [#########-----------------------]  28%  1,400/5,000   4m10s left

Checking is fast — it recognises photos it has read before, so a folder you
have run once mostly skips straight to comparing.

Reading is the slow part on a big folder — roughly a thousand photos a minute
for raws, faster for JPEGs. Comparing uses every core you have.

**2. Review**, in a page that opens in your browser.

**Every photograph it would move gets a pair**, the keeper on the left and the
one leaving on the right, both frames at the same size so a difference on
screen is a difference in the photograph. A group of six shows five pairs,
because five photographs are leaving and each is its own decision — and that
includes the ones the tool can prove are copies, since a proof you have never
looked at is only a claim.

**Ordered by how different the two photographs actually are**, most different
first. Work down and stop when it stops being interesting: what remains below
is more alike, not less examined. A pair whose difference could not be measured
comes first of all, because not knowing is the least confident state there is.

**Every pair can be answered on its own.** Under each one:

- **Do not cull this**, with a reason if you want to leave one. That frame
  stays and nothing else changes.
- **Wrong way round** — the frame on the right becomes the keeper instead. One
  keeper often stands for several frames, and the page says so when it does;
  turning a pair round moves the whole group, so only one per group can be
  turned.

Click either photograph to open it larger.

At the bottom: **Apply the rest** moves everything you did not refuse, and
**Quit** moves nothing and hands you back the settings. Both close the page,
and both write down every judgement you made.

**One menu, and you drive.** Before asking anything, the tool works out which
settings give genuinely different answers, and offers those:

        1   cull 48 of 200    24.0% of the folder    27 MB
        2   cull 50 of 200    25.0% of the folder    33 MB
        3   cull 51 of 200    25.5% of the folder   104 MB
        4   cull 54 of 200    27.0% of the folder   287 MB
        5   cull 60 of 200    30.0% of the folder   612 MB
      [1-5] review  ·  [q]uit

One keypress, no Enter. **Nothing is rendered until you ask for it.** Press a
number and that outcome is built and opened in the review page. Nothing can be
applied that you have not seen.

Applying finishes the folder. Drop several at once and it moves straight to the
next rather than asking to be let past each one. Changing your mind afterwards
is one gesture: drop the job's folder from `Culled Photos` back on the app, or
name it to `--undo`.

Settings that give the same answer are never offered twice, so there is
nothing in between to hunt for.

Working out the list is quick even on a large folder: culling can only ever
increase as the limit rises, so two settings that agree rule out everything
between them, and the tool checks a handful of boundaries instead of every
setting. Re-deciding then takes about a second, whatever the folder cost to
read.

The list is worth reading on its own. A folder that runs 48 to 60 across its
entire range, as this one does, has almost nothing to find.

**Applying finishes the folder**, so a queue of them moves straight to the
next rather than asking to be let past each one. Changing your mind is one
gesture afterwards: `--undo`, or drop the job's folder from `Culled Photos`
back on the app.

Each job's log is kept and numbered, so what moved where stays on record.

The limit applies to this folder only. It is written into the job's records so
you can see later what standard a cull was held to, and the next folder starts
from the default again.

**3. Move**, if you're happy:

    ./crull "/path/to/some/photos" --apply

Files go to `Culled Photos/<date> - <folder>` inside your working folder.
Nothing is deleted. The
dashboard refreshes itself. A culled photo's sidecar (`.xmp`, `.aae`) and its
Live Photo video (`.mov`) travel with it and come back with `--undo`.

Applying also records the pairs you reviewed in `Records/labels.csv`, and the
limit that folder was judged at in `Records/<job> - settings.txt`, so a cull can
always be traced back to the standard it was held to.

Tip: instead of typing a path, type `./crull ` and then drag the folder from
Finder into the Terminal window. It pastes the path, quoted correctly.

## How it decides two photos are the same

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

## Changed your mind?

**Drag the job's folder out of `Culled Photos` and drop it on
PhotoCruller.app.** The tool recognises its own output, tells you what the job was
and how many files it holds, and asks before putting anything back:

    ● 2024.03 - Holiday
      a finished job — 1,204 files (18.3 GB) can go back where they came from.
      put 1,204 files back?  [y/n]

Dropping a folder from *inside* one of those jobs works too — it finds the job
it belongs to. One keypress answers it, and only `y` or `n` count — anything
else is ignored rather than taken as an answer.

By name, if you prefer typing:

    ./crull --undo "<job name>"

Either way it puts back everything that job moved, exactly where it came from,
using the job's own log. Nothing is overwritten; anything that can't go back is
reported. Run it with a wrong name and it lists the jobs that can be undone.

## Checking where the line belongs

    ./crull "/path/to/photos" --hunt

Changes nothing, moves nothing. The same blind page as `--audit`, asking a
wider question: instead of only the culls, it draws pairs from across the whole
score range — confident culls, confident keeps, and everything between — so
your answers map out where your eye and the tool disagree.

It reports two rates, because there are two ways to be wrong: photographs it
would have lost, and duplicates it would have left behind. Every pair is
written to `Records/audit <timestamp>.csv` with what you said.

## Anything else

    ./crull --dashboard     refresh PhotoCruller.html
    ./crull --help


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
bars, the settings, and the review page before anything moves.

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

**Dropping a folder from the working folder means undo**, never cull — see
"Changed your mind?" above. The tool will not cull its own output.

**Rebuilds are rarely needed.** The app runs the live scripts, so code changes
reach it immediately; only a change to the drop-handling inside
`mac_install.command` needs `./mac_install.command` re-run.

## What a run looks like

    ./crull "/some/folder"

    ● 2020.01 - NYC
      reading photos    [############--------------------]  38%  1,900/5,000   1m20s left
      comparing photos  [################################] 100%  145/145      2m04s
      working out options   4s
      1   cull 18 of 145   12.4% of the folder   0.7 GB
      2   cull 23 of 145   15.9% of the folder   0.9 GB
      3   cull 31 of 145   21.4% of the folder   1.4 GB
      4   cull 44 of 145   30.3% of the folder   1.9 GB
      5   cull 51 of 145   35.2% of the folder   2.2 GB
      [1-5] review  ·  [q]uit
      > 2
      review open in your browser — http://127.0.0.1:52118/index.html
      you refused 2 · turned 1 round
      done · 21 moved · 0.8 GB · Photo Bin holds 12.4 GB

The options come first; the review page opens once you pick one. The choice of
setting is a single keypress — no Enter — and everything after that happens in
the page. Quit it and nothing moves; you are back at the settings, free to look
at another one.

**Nothing closes on its own.** A folder with no duplicates in it still waits
for `q`, so a run can never flash past before you have read what it found.
Dropped onto the app, the window closes once you have quit every folder in the
queue.
`--verbose` restores the full diagnostics when something needs debugging.

## If something looks wrong

Any pair where the wrong photograph is being culled can be answered on the
spot — *Wrong way round* to keep the other frame, or *Do not cull this* to keep
both. If a whole setting is culling too freely, quit back to the settings and
take a lower one: the list covers every distinct outcome the dial can produce,
and a lower setting excludes that pair and everything like it.

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

## Finding out how often it is wrong

    ./crull "/some/folder" --audit

Draws thirty culls at random from what the run would move and shows them in the
same page, with the answers covered: no labels, no filenames, and the side each
frame lands on decided by a coin. For each pair you say **the same photograph**
or **different photographs**; different means the cull was wrong.

Press *Done* and it reports how many were wrong and the range the true rate
lies in.

**Why a separate exercise.** Reviewing a whole plan tells you what that folder
needs, but not how often the tool is wrong — by the end you have seen which
frame it chose every time, and cannot unsee it.

**Why at random.** The review shows the biggest differences first, so working
through more of it tells you about the pairs the tool already thinks are
marginal, not about the rest. Only an even draw from the whole plan answers "of
the photographs this would move, how many should not be". Thirty gives a range
about ten points wide, a hundred about six.

## What it will not do

- Delete anything. Ever. Emptying `Culled Photos` is your decision
  alone, made in the Finder.
- Touch the folder it scans, other than removing files you approved moving.
- Judge that five distinct sunsets are redundant because you only need one.
  That's taste, and it isn't trying.
