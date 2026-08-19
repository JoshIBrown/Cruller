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

Which frame survives is decided by a ladder: carries a Live Photo's video →
raw → resolution → untouched by an editor → finer quantization → metadata
richness → compression tier → sharpness → file size.

Three of those rungs exist to keep originals, because a copy is only obvious
when it is smaller.

**Untouched** reads the Software tag: an editor signs its work and a camera
does not, so where two frames are the same size and one has been through an
editor, the other is the earlier generation. It sits below resolution so a
small edit can never beat a full frame, and it decides what nothing else can
see — a red-eye fix, a colour conversion, a tonal change alter no dimension at
all.

**Finer quantization** reads the JPEG's quantization matrix from its header,
without decoding. Saving a JPEG again throws more away, so the finer matrix is
the earlier generation. Measured against pairs whose EXIF names the editor,
resolution alone identifies the original 72% of the time and resolution then
the matrix 96%. The compression tier below it rounds the same number onto a log
scale, which is right for "much more compressed" and too coarse for this: two
generations of one picture often land in the same bucket.

What does *not* work, measured on the same pairs: high-frequency detail (50%,
because editors sharpen, so an edit often carries more apparent detail than its
source) and clipping (39%, because editors recover highlights rather than crush
them).

## Reviewing before you commit

A run does two things, and they are asked separately.

**First the copies.** Where the same picture sits in more than one file, there
is nothing to judge, so those are counted, their reasons named, and offered as
one decision: apply, look through them first, skip, or stop. Settling them also
keeps the grouping honest — a folder holding three copies of everything groups
strangely until they are gone.

**Then the grouping.** You are offered the settings the dial can produce, each
described by what it puts in front of you rather than what it would take:

    1    10 groups    20 photographs
    2    44 groups    94 photographs
    3    89 groups   209 photographs
    [1-3] review  ·  [q]uit

Nothing there is settled, so the list says only how much there is to look at.
How many would go, and how much that frees, depend on which frames you keep —
which is the question the review asks. Choosing a setting opens a page in your
browser, **one section per group**, and the answer is yours.

Each group shows **every photograph in it at once**, in the order they were
taken, with the frame the tool would keep outlined. Click any photograph to
keep or drop it; a group can end up keeping one, several, all of them — which
refuses the group — or none, which moves the lot.

**Groups come biggest first**, because that is where attention buys the most: a
group of twelve is eleven photographs you might not need. Safety is not the
review's job — the rules cull only what they can prove, and everything here is
a choice about which frames you want.

**Apply** moves everything still marked to go; **Quit** moves nothing and hands
you back the settings. Both close the page and write down every judgement, per
photograph, because an opinion about a photograph is the one thing here that
cannot be worked out again.

**The outlined frame is a starting position, not a decision.** See the ladder
above for how it is chosen, and how much of that is measured rather than
guessed.

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
