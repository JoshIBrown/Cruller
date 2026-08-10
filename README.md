# Cruller

Point it at a folder of photographs. It finds the near-duplicates, decides which
frame to keep, and moves the rest to a holding folder with a log.

**Nothing is ever deleted.** Every run is reversible with one command.

```bash
./crull "/path/to/some/photos"          # look — changes nothing
./crull "/path/to/some/photos" --apply  # move the redundant files out
./crull --undo "<job name>"             # put them all back
./crull --reset                        # undo everything, clear every cache
./crull "/folder" --audit              # judge 30 culls at random, blind
./crull --audit-result                 # what the tool's error rate actually is
```

macOS users can drag a folder onto `Cruller.app` instead.

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

A pair is a duplicate when that residual sits under one limit, which you move on
a dial from 0 to 100. There is no second limit and no subject detector — the
person choosing what goes in a folder sets its standard.

Candidates come from two pools, unioned: photographs that **look alike**
(a 144-number brightness sketch) and photographs **close in time** (bursts
chained at under 3 seconds). Measured against exhaustive all-pairs comparison,
this misses nothing.

Which frame survives is decided by a ladder: format (raw wins) → resolution →
metadata richness → compression tier → sharpness → file size. Sharpness settles
about 69% of them.

## Reviewing before you commit

An analysis run writes a proof image for **every photograph it would move** —
the frame that replaces it, side by side, at the same size — including the
culls it can prove. A relationship the tool is certain about is still a
photograph leaving.

They are ordered by how different the two frames are, most different first, so
the least confident call is the first thing seen. A pair whose difference could
not be measured leads the whole review, because not knowing is the least
confident state there is.

You are offered five settings, each with something to look at, and pick a cull
count rather than guessing at a threshold.

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
