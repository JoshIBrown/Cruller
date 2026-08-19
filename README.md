# PhotoCruller

Point it at a folder of photographs. It finds the near-duplicates, decides which
frame to keep, and moves the rest to a holding folder with a log.

**Nothing is ever deleted.** Every run is reversible with one command.

```bash
./crull "/path/to/some/photos"          # analyse, then review every cull in a page
./crull "/path/to/some/photos" --apply  # skip the review, move the redundant files
./crull --undo "<job name>"             # put them all back
./crull --reset                         # undo everything, clear every cache
./crull "/folder" --audit               # judge 30 culls at random, blind, for a rate
```

macOS users can drag a folder onto `PhotoCruller.app` instead.

## How it decides

A pair of photographs goes through progressively more expensive tests, and the
cheap ones only ever say *no*:

1. **Identical bytes** — culled outright.
2. **A 256×144 sketch**, phase-correlated. 0.3 ms, and it rejects 99% of pairs.
3. **A keypoint screen** — 400 ORB features, for copies that were rotated or
   heavily cropped and so look nothing alike at thumbnail size.
4. **The full look** — 2,000 ORB features at 1600px, a RANSAC homography, one
   frame warped onto the other, and the residual read in blocks of 1/200th of
   the long edge. Warping absorbs camera movement, so what is left is the
   *scene* changing rather than the photographer.
5. **A closer look**, at 3200px, for pairs the full look called duplicates.
   Some photographs are all fine detail — a page of print, a page of music —
   and at 1600 the characters are a few pixels tall and average away, so two
   different pages align beautifully because their margins do. Only a positive
   *different* overturns the earlier answer; where the closer look cannot tell,
   it says nothing. Paid only by pairs already judged duplicates.

A pair is a duplicate when that residual sits under one limit, which you move
on a dial from 0 to 100. There is no second limit and no subject detector — the
person choosing what goes in a folder sets its standard.

The dial governs pairs that are *judged*. A pair that can be **proved** derived
— one frame's warp landing inside the other, a quarter turn, or identical
geometry with the tone moved — is grouped whatever it measures, because the
edit is exactly what makes the difference large. So even at 0 the tool culls
provable copies, and no setting spares them.

Candidates come from two pools, unioned: photographs that **look alike** (a
frequency signature of the sketch — its low frequencies, thresholded, with
brightness dropped, so a re-toned copy still matches) and photographs **close
in time** (bursts chained at under 3 seconds). Measured against exhaustive
all-pairs comparison, this misses nothing.

Which frame survives is decided by a ladder: format (raw wins) → resolution →
metadata richness → compression tier → sharpness → file size. Sharpness settles
about 69% of them.

## Reviewing before you commit

You are offered the settings the dial can actually produce — usually five — and
pick a cull count rather than guessing at a threshold. Choosing one opens a page
in your browser, **one section per group**: a group being the set the tool
believes are the same photograph, of which some are to be moved.

Each group shows **one photograph at a time**, filling the screen, with a slider
underneath. Slide left for the frames taken before it, right for those after,
and the picture changes in place. Run through a burst quickly and it plays like
a short film — which is the point. Change between frames in the same position is
far easier to see than difference between two frames side by side, so a moved
hand or a blink announces itself.

Under the slider, one mark per photograph: green stays, red goes, and an
outlined mark is the one the tool would have kept. Click the picture to change
its mind about the frame you are looking at, or click a mark to change another.

That means a group can end up keeping one, several, all of them — which refuses
the group entirely — or none at all, which moves the lot. Groups are ordered
least confident first, and a group whose difference could not be measured leads
all of them, because not knowing is the least confident state there is.

**Apply** moves everything still marked to go; **Quit** moves nothing and hands
you back the settings. Both close the page and write down every judgement, per
photograph, because an opinion about a photograph is the one thing here that
cannot be worked out again.

**The keeper is a starting position, not a decision.** The tool marks one frame
per group by a ladder — raw first, then resolution, metadata, compression,
sharpness — and sharpness settles about 69% of them, which is the rung with the
least evidence behind it. It is a good guess, not an answer, and one click
overrides it.

### How often is it wrong?

    ./crull "/some/folder" --audit

Reviewing the whole plan tells you what a folder needs, but not the tool's
error rate — by the end you have seen the answers. This asks the same question
with the answers covered: culls drawn at random, no labels, and the side each
frame lands on decided by a coin. It reports the share that were wrong and the
range the true rate lies in.

## Installing

Double-click `mac_install.command`, or see [START HERE.md](START%20HERE.md) for
the full walkthrough, Windows instructions, and what each library is for.

Needs Python 3, `numpy`, `pillow` and `opencv-python-headless`; `pillow-heif` if
you have iPhone HEIC files.

## Status

Working software, used daily against a 70,000-photograph library, and still
being sharpened.

- [docs/design.md](docs/design.md) — every judgement it makes, and why each
  number is the number it is
- [docs/dead-ends.md](docs/dead-ends.md) — what was built or measured and does
  not work, so it does not get proposed again
- [docs/roadmap.md](docs/roadmap.md) — known gaps and unfinished work
