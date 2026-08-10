# What was tried and does not work

Each of these was built or measured, and each is written down so it does not
get proposed again. Where something was removed, the entry says what it did, so
you can tell whether your idea is the same idea.

## Recognising what is in the photograph

**The idea.** Two frames of a bird turning its head produce the same numbers as
a plate of food nudged an inch. Only one of those pairs should be culled. If
the tool knew there was a *bird* there, it could tell them apart.

**What was built.** Face detection and a general object detector, cropping the
subject from the original at up to 2,000 pixels, aligning it, and judging the
subject region on its own terms.

**Why it went.** Every proxy for "is there a live subject here" landed the
protected cases squarely inside the distribution of the approved ones — detail
maps, spectral saliency, connected components in the residual, all
indistinguishable. Eye-state detection produced one usable reading out of
nineteen detected faces. And the detectors missed small subjects entirely: a
small bird, an insect, anything distant. The mechanism protected exactly the
cases that did not need protecting.

**What replaced it.** Nothing, deliberately. Every case it was meant to fix is
reachable only at a loose setting — of fourteen disputed culls collected from
one review, eleven appeared only above the default limit, and none survived
below it. The low end of the dial is the answer, and it needs no model.

**The lesson worth keeping.** Before deciding a judgement needs more
intelligence, check whether the evidence survived being shrunk. The case that
originally motivated all this — open eyes against closed eyes — scores 4.5% on
a 256×144 sketch, where a face is 20 pixels and an expression is a fraction of
one block. The measure was not too stupid; it was reading the wrong scale.

## Two limits instead of one

**The idea.** A landscape can change more than a portrait before it stops being
the same photograph, so scenery should be judged by a looser limit than
anything containing a person or an animal, with a detector deciding which
applies.

**Why it went.** Fitted, it did earn extra culls. But the detector missed small
subjects, so a bird in a landscape was quietly given the loose limit; nothing
in the interface ever showed which limit a pair had received, so a
misclassification was invisible; and at the loose end the two limits collapse
into one anyway. Choosing what goes into a folder does the same job visibly.

## Per-pair limits from focal length

**The idea.** A wide-angle shot and a telephoto shot of the same subject move
different amounts of the frame for the same physical movement, so the limit
should scale with the lens.

**Why it went.** It was compensation for a deeper problem — judging on a small
thumbnail — and once the comparison was done properly at 1600 pixels with a
fitted homography, the bands had nothing left to correct. No single set of
bands ever satisfied all the known cases; the fix came from measuring
correctly, not from more parameters.

## A fitted model instead of thresholds

**The idea.** Replace hand-set limits with a classifier trained on labelled
pairs.

**Why it went.** The labelled set is small, drawn from one person's library,
and heavily biased towards pairs the tool already flagged. A model fitted on it
learns that bias and hides it behind a score, where a threshold at least shows
you what it is doing. Thresholds also let a person move the decision at review
time, which a fitted model does not.

## Decoding once to a scratch file

**The idea.** The full look re-decodes frames that the reading pass already
decoded — on one folder, 5,316 decodes for 3,245 files. Write each decoded
frame to disk once, use it everywhere, delete it at the end.

**What happened.** It was built. Compression fails both ways: lossy compression
changed four verdicts in fifty-nine, and lossless spends more time compressing
than it saves decoding. Written raw it was bit-identical and, on paper, saved
20 ms per photograph.

**Why it went.** In a clean A/B it saved *nothing* — the same time, to the
second, and the same culls. Decoding runs on eight threads and is not the
critical path, so removing work from it only leaves threads waiting elsewhere.
It cost 6 GB of transient disk and a crash-cleanup obligation for no gain.

**The lesson worth keeping.** A saving per operation is not a saving in
wall-clock time unless that operation is the bottleneck.

## An exact decode size instead of a bounded one

**The idea.** Halving means the decoded long edge lands anywhere between 2,000
and 3,999 pixels. Two photographs can therefore be reduced by different
factors, and sharpness is compared *between* photographs. Ask for an exact size
instead.

**Why it went.** The worry was empty and the fix was harmful. Across 1,145
groups, 823 reached the sharpness rung with everything above it tied, and not
one held contenders that halved differently — equal pixel counts mean equal
dimensions in practice. Meanwhile an exact size requires an interpolating
filter, which smooths the image, which is what sharpness measures. It also cost
8%.

## Reading at a quarter instead of a half

**The idea.** Sharpness is a coarse measure; if half resolution serves it, a
quarter might too, and decoding is a large share of a cold run.

**Why it went.** Measured across two folders, it moves the keeper in about 7%
of groups and shifts which photographs are culled, in both directions, to save
3–6% of a run. Real decisions traded for noise. The saving is small because
reading is roughly 10% of a run on a dense folder — comparing photographs is
nearly all of the rest.

## Normalising the brightness grid instead of transforming it

**The idea.** The candidate descriptor compared average brightness, which a
re-toned copy defeats. Removing each grid's mean and scale before comparing
discards tone and leaves structure — a one-line change to the descriptor
already in use.

**Why it went.** It works, and it buys nothing. On matched nomination counts it
found the same culls as the frequency signature and returned almost none of the
time, because the grid still describes the picture coarsely however it is
scaled. If the descriptor is being changed at all, the transform is the change
worth making.

## Scoring a pair on a high block instead of the worst one

**The idea.** The score is the worst of about thirty thousand blocks, which is
an extreme value. One region changing completely — somebody walking through a
burst — makes the whole pair read as two different photographs, so a burst
frame can never be culled at a gentle setting however alike the rest of it is.
Measured on real burst pairs, the median block difference was 2% while the
score was 75%. Ignoring the top fraction of a percent should let those through
while still seeing anything larger.

**What it found.** Against labelled pairs it works, and by a wide margin. With
both limits refitted, scoring on the 99.9th block finds **97 of 200 wanted
culls with no false culls, against 71** for the worst block. It is also
steadier: dropping the single pair that constrains the limit moves it by 6%,
where the worst block moves by 29%.

**Why it went.** It culls a bird turning its head, and a small subject that
changed. Neither is in the labelled set; both are guarded cases, found by eye,
because they are the failures that matter. At the 99.9th block the small
subject scores 12.3% with a texture ratio of 1.27 — no limit that leaves the
tool useful protects it. Discarding the top blocks does not soften that
evidence, it removes it: a small subject *is* a handful of extreme blocks.

**The lesson worth keeping.** Labels and guarded cases are not
interchangeable. A fit that optimises a labelled set can walk straight through
a case the set does not contain, and the labelled set here is drawn from pairs
the tool already flagged — so it is thin exactly where the guards are. Fitting
anything against it must be checked against them.

The tension is real and stands: the worst block protects the small subject and
blocks the burst near-duplicate, and it cannot tell the two apart. Any fix has
to separate "a small region changed" from "a small subject changed", which is a
question about what is in the photograph.

## Sixteen-bit arithmetic for sharpness

**The idea.** The Laplacian spans about −1020 to 1020, so it fits in a 16-bit
integer and should be faster than floating point.

**Why it went.** It was 8% slower. Taking a variance of 16-bit integers
promotes them to 64-bit floats internally, so the narrower type buys nothing
and costs a conversion.

## Noise reduction before measuring

**The idea.** Sharpness responds to noise as well as focus, so denoise first.

**Why it went.** Every filter strong enough to suppress noise also softened the
edges the measure exists to find, moving keeper choices without improving them.
The blind spot is real; this is not the fix.

## Running the keypoint screen before the cheap sketch

**The idea.** The sketch is blind to strongly recomposed copies. Run the
keypoint screen first so nothing is rejected before it has been looked at
properly.

**Why it went.** The screen costs about twenty times what the sketch costs. On
one slice it inflated full looks from 575 to 1,403, and of forty pairs newly
reached, none actually culled.

## Brightness-matching the residual

**The idea.** A tonal edit differs from its original only in brightness, so
matching brightness before measuring would let the comparison see past the
edit.

**Why it went.** A global offset match gained tonal pairs and lost partial-light
pairs, ending slightly behind. A linear gain-and-offset match still missed most
tonal edits, because tone-curve edits are locally nonlinear, and it pushed a
must-keep pair — a breaking wave — towards being culled. Provable lineage
solved the problem instead, without touching the measurement.

## Vetoing a cull by zoom, or by subject box

**The idea.** A wide shot and a zoomed shot of the same scene are different
photographs; refuse to cull pairs whose alignment shows a large zoom.

**Why it went.** Zoom does not separate them. Above 1.15×, 21% of disputed
culls and 12% of approved ones — the same population. The subject-box variant
failed the same way: the subject's own region scored identically to the whole
frame.

## Writing star ratings into files

**The idea.** Mark keepers and losers with ratings so another application can
act on them.

**Why it went.** It writes into the library being scanned, which the tool
otherwise never does, and the review answers the same question better without
modifying anything.

## Letting a sample of the review vote

**The idea.** Show a subset of the culls, let the reviewer throw out the ones
they disagree with, and apply the rest untouched.

**Why it went.** A subset chosen worst-first says nothing about the majority
nobody looked at, so throwing one out offered the feeling of control over a
decision that had not actually been examined.

**What replaced it.** Not a smaller veto but a complete review: every cull in
the plan is shown, and each one can be refused or turned round on its own. A
veto is sound exactly when there is nothing behind it that was never seen. The
question the sample was standing in for — how often is the tool wrong — is
answered separately by a blind random audit, because a review where you are
told the answer each time cannot measure the answerer.
