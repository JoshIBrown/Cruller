# How Cruller decides

This explains every judgement the tool makes and why each number in it is the
number it is. Nothing here assumes you have seen the code, and every figure was
measured rather than chosen.

## The problem

A photo library accumulates near-duplicates: burst frames, an original beside
its export, a crop beside what it was cropped from, the same scene shot six
times while someone blinked. They are not identical files, so file hashing
finds none of them. They are also not *the same photograph* in any simple
sense — one frame of a burst may be the good one.

So the tool has to answer two questions, and they are different questions:

1. **Are these the same photograph?** — comparing, and collecting the ones
   that match into a set.
2. **If so, which frame survives?** — the keeper choice.

Getting the first one wrong loses a photograph you wanted. Getting the second
wrong keeps the worse of two copies. The first failure is much more expensive,
so everything below is biased towards keeping both when unsure.

## Finding candidates

Comparing every photograph against every other is quadratic: a folder of 28,000
files is 398 million pairs. Two cheap pools nominate candidates instead, and
their union goes forward.

**Close in time.** Photographs taken within 3 seconds of each other chain into
a burst, and every pair inside a burst becomes a candidate. A wider one-minute
window catches slower sequences. This is nearly free — it reads capture times,
not pixels — and it means a burst is discovered identically in a small folder
and a huge one.

**Look alike.** Every photograph is reduced to a frequency signature: its
sketch is transformed, the lowest frequencies kept, and each thresholded at
their median to give a string of ones and minus-ones. Frames whose signatures
agree become candidates. This finds copies that share no timestamp at all: an
export made years later, a file recovered from a backup, the same picture
filed twice.

The first coefficient is dropped, and with it the brightness. That matters
because tone is the first thing an export changes, and a descriptor built on
average brightness leaves a re-toned copy sitting further from its own original
than the threshold allows — measured, three of them. Compared against such a
descriptor with a cold cache each time, this finds the same culls and returns
20% of the time on a dense folder.

Agreement decides which frames are nominated, not rank. A fixed number each
is wrong in both directions: a folder of unrelated photographs would still
nominate its quota apiece and pay for every one downstream, while a session of
200 near-identical frames would be truncated. A photograph that resembles
nothing nominates nothing.

**How much agreement is enough** is a trade, and it was measured rather than
guessed. A generous threshold nominated 23 candidates per photograph on a
dense folder, and comparing them took 88% of the run. Tightening it costs a
small number of real culls — 3 in 327 on that folder, none at all on a sparse
one — and returns 41% of the time. Tightening further keeps paying, but more
slowly and at twice the cost in culls, so the current setting sits at that
knee.

This threshold is not the dial. The dial decides how different two frames may
be and still count as the same photograph; this decides which pairs are ever
compared at all. A pair the pool never nominates is never measured, so no dial
setting can recover it.

**Does this miss duplicates?** It was checked directly, by comparing every
possible pair in two folders and looking for culls the two pools never
nominated. There were none — the exhaustive run found exactly the same culls.

## The funnel

Candidates pass through four tests, cheapest first. Only the last one may say
*yes*; the earlier ones exist to say *no* quickly.

| Test | Cost per pair | What it does |
|---|---|---|
| Identical bytes | negligible | Same content, different name. Culled by rule. |
| Rough overlay | 0.3 ms | Aligns two 256×144 sketches by phase correlation and compares them. Rejects about 99% of candidates. |
| Keypoint screen | 20 ms | 400 ORB features. Catches copies that were rotated or heavily cropped, which look nothing alike at sketch size. |
| Full look | 60 ms | The real decision, below. |

The rough overlay may only reject. Anything it lets through is confirmed
properly, so a cheap test can never cause a cull on its own.

## The full look

Two thousand ORB keypoints are found in each frame at a 1600-pixel long edge,
matched, and a homography fitted by RANSAC. One frame is then warped onto the
other and the difference between them is measured in blocks.

Warping is what makes this work. It absorbs translation, rotation, zoom and
perspective, so what remains is *the scene changing* rather than the
photographer moving. A recomposed shot of the same subject aligns; two
different subjects do not.

The difference is read two ways — the largest block difference, and that
difference relative to local texture — and both must sit under the limit. The
relative reading stops a busy, high-contrast area from passing simply because
everything there is busy.

**Why 1600 pixels.** Measured against a set of hand-labelled pairs, this is a
genuine peak rather than a floor:

| Comparison size | Share of wanted culls found | False culls |
|---|---|---|
| 600 | 30% | 0 |
| 800 | 39% | 0 |
| 1200 | 39% | 0 |
| **1600** | **40%** | **0** |
| 2400 | 37% | 0 |
| 3200 | 33% | 0 |

Bigger is worse, monotonically, and costs 80% more time at 3200. Extra
keypoints past 2,000 behave the same way: 500, 1,000 and 4,000 features all
find fewer of the wanted culls than 2,000 does. In both cases the extra detail
is weaker evidence that muddies the alignment.

**Why blocks are 1/200th of the long edge.** A block was once a fixed 8 pixels,
which is 1/200th of a 1600-pixel frame but 1/75th of a 600-pixel one. That made
every comparison-size measurement misleading: at small sizes each block covered
more of the picture and averaged real differences away, which made low
resolution look like it culled *more*. Stating the rule proportionally leaves
every large photograph bit-identical and makes the whole measurement stable.

## Reading each photograph

Every photograph is decoded once, up front, to feed two things: the 256×144
sketch and a sharpness score. It is reduced by halving only — never to an exact
target size — because halving is exact and free inside a JPEG decode, while
landing on an arbitrary size needs an interpolating filter that smooths the
image. Smoothing is precisely what sharpness measures, so interpolating there
would corrupt the number being read.

The long edge lands between 2,000 and 3,999 pixels. Halving once more was
measured and rejected: it moves the keeper in about 7% of groups and shifts
which photographs get culled, to save 3–6% of a run.

## Sharpness, and which frame survives

The keeper is chosen by a ladder, and the first rung that separates two files
decides:

1. **Format** — a raw beats a derived file.
2. **Resolution** — more pixels.
3. **Metadata richness** — the file that still knows when and how it was taken.
4. **Compression tier** — less lossy.
5. **Sharpness**.
6. **File size**.

Sharpness settles about 69% of them, so it is worth stating exactly what it
measures. The image is divided into a grid; in each tile the variance of a
Laplacian is taken, which is large where edges are crisp and small where they
are soft. Tiles are weighted towards the centre of the frame, and the sharpest
few are averaged.

That combination asks "is the subject crisp", not "does this file contain a lot
of fine detail". The distinction matters: read at full resolution, the same
measure picks up sensor noise and texture that have nothing to do with focus,
and noise scores as sharpness. Judged against hand-picked keepers, the
half-size reading agreed and the full-resolution reading did not.

The measure has a known blind spot. Between two frames where one is grainier,
it can prefer the noisier one, because noise is high-frequency detail and that
is what the Laplacian responds to.

## The limit, and the dial

A pair is a duplicate when its difference sits under one limit. There is one
limit for a whole folder, moved on a dial from 0 to 100, and the person
choosing what goes in the folder sets the standard for it.

An earlier design split the limit in two — one for photographs containing a
person or animal, a looser one for scenery — with a detector deciding which
applied. It was removed. The detector missed small subjects entirely, which
meant a bird in a landscape was silently judged by the loose limit, and the
whole mechanism was invisible: nothing in the interface showed which limit a
pair had been given. Curating the folder does the same job and can be seen.

Rather than asking you to guess a number, a run works out every distinct
outcome the dial can produce and offers about five of them as a list: how many
photographs each setting culls, what share of the folder that is, how much
space it frees, and how many pairs it would give you to review.

**The list comes first and nothing is rendered until you choose.** Proof
images are built only for the outcome you choose to review, and only then can that
outcome be applied — so nothing is ever applied that has not been looked at.

**How the options are chosen.** The dial runs from 0 to 100, but most settings
answer the same as their neighbour, and the interesting ones bunch at the low
end — the difference between 2 and 3 matters, the difference between 70 and 80
rarely does. So the tool lays a ladder across the range, close together at the
bottom and spreading towards the top.

It weighs five of those rungs, and no more. Two are given rather than found:
the most conservative setting and the most thorough are always worth offering.
Each of the remaining three is placed in the widest gap between the cull counts
already known, which is where another option is worth the most.

That matters because weighing a setting is not cheap. Each one walks the whole
candidate set again — about ten seconds on a folder of a thousand photographs —
so the count is the cost. Searching for exact boundaries instead took
seventeen settings to offer the same five.

## Culls decided by rule

Some relationships are provable rather than judged, and those are culled
without being shown for review:

- **Identical picture** — the decoded images match exactly.
- **Smaller copy** — the same picture at lower resolution.
- **Cropped copy** — one frame's warp lands entirely inside the other.
- **Tonal edit** — identical geometry, shifted brightness or contrast.
- **Rotated copy** — a quarter-turn of the same capture.
- **Export of a raw**, **resave** — derived files beside their original.

These are one rule wearing several labels. Each says the same thing — this
file is not the original, and the original is here — and the label records how
the copy was made, which is a note rather than a separate decision.

The provable relationship *is* the answer: a crop or a tonal edit is grouped
regardless of how large its measured difference is, because the edit is exactly
what makes the difference large, and the edit is what should go.

**A reason may skip review only if it proves derivation.** Three do so on their
own — a containment warp, a quarter turn, an untouched geometry with the tone
moved. Three do not: being a raw beside a JPEG, holding fewer pixels, or
carrying a coarser quantization table are facts about two files, not about a
relationship between them. Those must also show the two pictures agree, by
comparing their sketches with brightness and contrast removed, so the question
asked is "the same picture?" and not "the same tone?". A pair that cannot show
it falls through to a judged near-duplicate and is put in front of somebody.

Audited across four folders, that requirement changes no cull at all. It moves
about 3% of them from settled to reviewed — which is exactly the population
whose evidence never supported settling them.

The time window matters and is not the same for both. A crop or rotation is
accepted within 2 seconds. A tonal signature demands the same capture instant,
because "same geometry, the light moved" describes a breaking wave or a
changing expression just as well as it describes a brightness edit — measured
on labelled pairs, crop signatures on frames merely seconds apart are a
coin flip between a real crop and an optical zoom.

## Safety

- **Nothing is ever deleted.** Redundant files are moved to a holding folder
  with a log, and one command puts every file back.
- **Sidecars and Live Photo videos travel with their photograph**, and return
  on undo.
- **Photo library packages are never entered.** A managed library is a
  database, not a folder of files.
- **The tool never writes into the folder it is scanning.** Everything it
  produces — plans, logs, proof images, moved files — goes to a working folder
  chosen once, on first run.
- **No alignment, no cull.** A pair too dark or too flat to align reliably is
  kept, both frames.

## Repeat runs

Pairwise verdicts are also held in memory for the life of a run, which is
worth knowing before measuring anything: two settings compared inside one
process are not a fair test, because the first pays for the comparisons and the
second finds them already done. Any A/B here needs a process each.

Reading is the expensive part, so results are cached against file content
rather than path or timestamp: a folder that has been read once mostly skips
straight to comparing, and a file that moved is not re-read. Re-deciding at a
different limit takes about a second however long the first read took, because
the pairwise verdicts are cached too and the limit is applied to stored
numbers.
