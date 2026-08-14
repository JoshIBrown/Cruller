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

You are offered the settings the dial can actually produce — usually five —
and pick a cull count rather than guessing at a threshold. Choosing one opens a page in your browser showing **every photograph
it would move** — the frame that replaces it on the left, the one leaving on
the right, at the same size. Nothing is certain enough to skip: a relationship
the tool has no doubt about is still a photograph leaving.

Pairs are ordered by how different the two frames are, most different first, so
the least confident call is the first thing seen. A pair whose difference could
not be measured leads the whole review, because not knowing is the least
confident state there is.

Every cull can be answered on its own:

- **Do not cull this**, with a reason — that frame stays, and the rest of the
  plan is unaffected.
- **Wrong way round** — the frame on the right becomes the keeper. One keeper
  can stand for several frames, so this is a statement about the whole group,
  and the page allows one per group.

**Apply** moves what survives the review; **Quit** moves nothing and returns
you to the settings. Both close the page, and both write down every judgement
you made, because an opinion about two photographs is the one thing here that
cannot be worked out again.

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
