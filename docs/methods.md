# What this does, and what the literature does

Every decision here has a published equivalent. This maps one to the other,
says where they agree, and — more usefully — says where they diverge and
whether the divergence is a choice or an oversight.

It exists because several weaknesses found by measurement turn out to be
documented properties of the methods being used. Knowing that is faster than
rediscovering it.

## Finding candidates: the frequency signature

**Here:** each sketch is sampled to a square, transformed with a discrete
cosine transform, its lowest frequencies kept, and each thresholded at their
median. The first coefficient — brightness — is dropped. Two frames are
candidates when their signatures agree.

**In the literature:** this is *perceptual hashing*, the DCT variety usually
called pHash. The family also includes average hashing (block brightnesses),
difference hashing (adjacent block differences) and wavelet hashing.

**Why this one.** Comparative evaluations place the DCT variety well ahead of
average hashing for near-duplicate retrieval, and the reason matters here:
average hashing compares brightness directly, so a copy whose tone was changed
moves a long way even though the picture is unchanged. That is the common case
— a program that resizes a photograph usually re-encodes it too — and it was
observed before the change, three copies sitting further from their originals
than the threshold allowed.

**What is not used.** Wavelet hashing is reported more robust to blur and
filtering at modest extra cost, and is untested here. Its documented weakness
is large geometric change, which is the case the keypoint screen already
covers.

## Deciding two frames are one photograph

**Here:** 2,000 ORB keypoints at a 1600-pixel long edge, a homography fitted by
RANSAC, one frame warped onto the other, and the difference read in blocks —
the largest block difference and that difference relative to local texture.

**In the literature:** a standard registration pipeline. Comparative studies
put SIFT ahead of ORB on accuracy and ORB far ahead on speed, which is the
trade made here. On the fitting step, MAGSAC++ outperforms plain RANSAC on
published homography benchmarks and removes the inlier-threshold guess.

**Where they diverge.** The block residual is close to a per-block mean
absolute error. The standard comparison is SSIM, which decomposes similarity
into luminance, contrast and structure. That decomposition is interesting here
for a specific reason: an *edited* pair is precisely a change in luminance and
contrast with structure held constant, and the code currently detects it with
hand-set thresholds on brightness offset and contrast ratio. SSIM already
separates those terms by construction.

SSIM has its own documented limits — it assumes local structures matter
equally, and it does not handle spatial distortion — but the frames here are
aligned before comparison, which is the condition it wants.

## Choosing which of two copies survives: sharpness

**Round one only.** This decides which of two *files* is the copy, and it is the
last rung of the ladder to be reached — most pairs are settled above it, by a
raw beside an export or a mark the camera left. Round two never asks: a person
picks the frame they like, and no focus measure substitutes for that.

**Here:** the variance of a Laplacian per tile, weighted towards the centre,
averaging the sharpest few tiles.

**In the literature:** the variance of the Laplacian is a standard focus
measure and appears in every comparative study. The largest of those evaluated
around 36 operators across imaging conditions.

**What it found:** Laplacian-based operators perform best under normal
conditions — and are **the most sensitive to noise of any family tested**.
Statistics-based operators are the robust ones. Window size matters in both
directions: too large oversmooths, too small amplifies noise.

**That is the weakness observed here**, from the other end. Between two frames
where one is grainier, this measure can prefer the noisier one, because noise
is high-frequency detail and that is what a Laplacian responds to. Denoising
first was tried and made things worse, which is consistent — the filters that
suppress noise also soften the edges being measured. The literature's answer is
not to clean the image but to use an operator that is less noise-sensitive to
begin with.

## Telling an original from a copy of it

**Here:** one rule — the file is not the original and the original is here —
with labels recording how the copy was made. A label may claim derivation only
if it proves it: a containment warp, a quarter turn, an untouched geometry with
the tone moved. Labels resting on file properties must also show the two
pictures agree. The keeper comes from a ladder that puts raw first and
resolution second, and below those two rungs that are evidence rather than
inference: whether anything wrote the file after the camera did, and whether
the camera's own private block is still in it. Both were built after a measured
failure — the tool keeping a Windows Photo Viewer re-save over its iPhone
original, and keeping a file whose clock had moved forty days over one still
carrying the camera's block.

**In the literature:** this is *image phylogeny*, and it is a developed field.
The standard shape is two steps: build a dissimilarity matrix with a
dissimilarity function, then construct a tree from it. The tree's root is the
original; every other node is a derivative of its parent.

**Where they diverge, and it matters.** Phylogeny dissimilarity functions are
deliberately **asymmetric**. The question asked is "can A be transformed into
B?", which has a different answer each way round: a crop can be produced from
the full frame, but the full frame cannot be produced from the crop. Every
comparison here is symmetric — the residual is measured both ways and the worse
taken — so the direction of derivation is inferred from file properties
afterwards rather than measured.

That inference is where the trouble is. Ranking by resolution assumes a copy is
never larger than its source, which is false for an upscaled export.

**What has proof today, and what does not.** Of the labels the tool acts on
alone, most carry their own: a *duplicate* and an *identical* need no direction at
all, a *crop* and a *smaller* are proved by containment, and a raw is not made
from a JPEG. Two do not. A **resave** and an **edited**
leave the geometry untouched, so nothing about the pictures says which came
first, and the direction rests on the compression rungs alone unless the camera
marks happen to speak. This is the gap double-compression detection closes, and
it is why that item ranks above the other two.

## A camera that saves two frames of one capture

**Here:** read from EXIF `CustomRendered`, which the camera writes itself.
Shooting HDR stores 3 on the merged exposure and 4 on the frame it was merged
from; shooting Portrait stores 8 on the depth blur and 9 on the frame it was
computed from. Measured over 25,728 photographs, no other combination occurs.
Which one survives is not something a measurement can answer — both are the
same photograph and neither is degraded — so it was asked: across 30 pairs, the
untouched frame every time for Portrait, the merged exposure every time for
HDR, though 9 of 10 HDR answers were that the two could not be told apart.

**Why it is not inference.** Every other reason the tool acts on alone is an
argument that one file was made from another. This one is a record the camera
kept at the moment of capture, which is why these are settled without review
even though the two frames differ visibly.

**And why the record outranks the comparison.** They differ visibly enough that
the full look calls them different scenes — an HDR merge lifts shadows and
pulls back highlights, which is exactly what the residual measures. So the pair
was being nominated, rejected, and never reaching its own rule: 27 of 57 such
pairs settled. The mark is about provenance and the residual only about
appearance, so where the camera says one capture, that is the membership
decision. Narrowly: only the two combinations a camera writes, only with a
shared capture time, and everything else still has to look alike. 56 of 57 now,
the last being a pair whose group formed around a third frame.

## A turn the alignment cannot see

Orientation is applied before anything is measured, so a frame stored sideways
and its upright twin line up with **no rotation at all** — one such pair here
reads `rot=0.0` and a residual of 0.8%. The rule that looks for a quarter turn
in the alignment can therefore never fire on the commonest shape of rotated
copy: a camera frame carrying an orientation flag beside a copy with the pixels
baked and the flag cleared. Nineteen captures in this library are that shape,
and the tool was keeping the right frame in every case but calling it a plain
near-duplicate, so all of them reached the review.

What gives it away is the stored dimensions being transposes of each other,
which is read alongside the same agreement test every other lineage claim uses.
Eighteen of the nineteen now settle. The evidence is the shared capture instant
rather than the residual, because for this shape the residual is misleading: a
baked turn can sit 180 degrees from its original, which is the same photograph
with the same histogram and an anti-correlated pixel at every position, and it
reads 16%. Turning a camera through a right angle and shooting again inside one
recorded second is not something that happens, so transposed shapes at one
instant are a stored-orientation difference. One case in the library has the
turn baked the wrong way round, and the tool keeps the camera's frame — the one
that is the right way up.

## Detecting an upscale

**Here:** nothing. Resolution decides, so given an original and an enlarged
copy of it, the enlargement wins on the resolution rung and the original is
culled.

**In the literature:** resampling detection is well established. Rescaling an
image interpolates new pixels from old ones, which introduces periodic
correlations between neighbouring pixels; those correlations are detectable,
and the period reveals the scaling factor. The foundational method is from
2005 and works on uncompressed and lightly compressed images; it degrades under
heavy JPEG compression, which later work addresses.

**Why it matters here:** this answers "which of these two was made from the
other" directly from the pixels, without capture times, filenames, or an
assumption about which way resolution runs.

## Detecting a re-save

**Here:** two readings of the same table, for two different jobs. The keeper
order reads the quantization matrix straight, as a mean, because two generations
of one picture often land in the same bucket; that names the earlier generation
in 91% of pairs where the EXIF says which is the edit, and 96% once resolution
has spoken first. The *label* still works off the bucketed tier, and calls a
difference of more than one tier a resave.

**In the literature:** a re-saved JPEG has been compressed twice, and double
compression is detectable from the file itself. The quantization table is
stored in the file and can be read without decoding; DCT coefficient histograms
carry characteristic artefacts of a second compression, and the first
quantization matrix can often be estimated. Published estimation accuracy is
around 80%, rising with quality factor.

**Built, 2026-08-19.** The quantization table was already read. The rest — the
DCT histogram — needed the coefficients as stored, which meant a baseline JPEG
reader that decodes the entropy-coded data rather than the pixels; reading them
through decoded pixels cannot work, and why is in dead-ends.md. A second, finer
save leaves a comb of empty bins that one quantization cannot produce, and only
a clean comb is acted on. It is read as little as possible: frames from
one camera tie on every rung above it, so the tie is the normal case, but the
rung can only ever demote — so the candidates are ordered on the cheap rungs
below and read down until one comes up clean. On a folder of 140 photographs
that is nine reads rather than 140.

**What it does not catch.** Saving again more *coarsely* collapses values
together rather than leaving gaps, and looks like a photograph with less detail
in it. That is the right half to miss: a coarser re-save already loses to its
source on the compression rungs, while a finer one beats them. On 30 real
auto-culls the comb spoke rarely, agreed with the camera marks every time it
and they both spoke, and proved one direction the marks could not.

## Choosing the best frame of a burst

**Here:** not attempted, and now deliberately out of scope. Round two gathers a
burst into a scene and puts every frame of it in front of a person, largest
scene first. Picking the frame where somebody is smiling is the thing being
asked of them, not of the tool.

**In the literature:** no-reference image quality assessment. BRISQUE scores
naturalness from local luminance statistics against a model trained on known
distortions; NIQE uses the same family of statistics but is trained only on
undistorted images, so it is not tied to particular distortion types. Published
burst-selection systems combine a global quality filter with a content
comparison, which is close to the shape this would need.

**Why it stays unattempted:** picking the frame where somebody is smiling is a
judgement about content, and no quality metric answers it. What changed is that
this is no longer a gap — it is the division of labour. The tool finds the
fifty-five frames; the person picks the one.

## Gathering a scene, and why not with the same instrument

**Here:** capture time proposes a shoot and the sketch splits it into scenes,
each frame joining on agreement with the scene's own average. Nothing that
decides round one is used.

**Why not.** The obvious thing is to reuse the residual — it already answers
"are these two the same picture" very well. It answers the wrong question.
Measured on 8,000 nature photographs, the longest burst in the folder came out
as **no group at all**: fifty-five frames of a bird in flight, and no two of
them the same photograph. The instrument built to refuse near-misses refuses an
entire scene.

**In the literature:** this is event or session clustering, usually time-first
with content used to refine, which is the shape arrived at here independently.
The refinement is normally agglomerative, and the choice of linkage is exactly
where it goes wrong — single linkage lets a cluster walk. That was reproduced
here before it was read about: chaining neighbour to neighbour ran a scene from
2013 to 2019, holding pairs that were anti-correlated.

## What follows from all this

Three of these have a documented method that answers a question currently
answered by inference:

1. An asymmetric dissimilarity, so derivation has a direction that was measured
   rather than assumed from which file holds more pixels. **Still open.**
2. Resampling detection, so an upscale cannot pass for an original. **Open, and
   the least urgent** — spot-checked against real culls, the keepers read as
   full-resolution frames rather than enlargements.
3. The quantization table, so a re-save is read from the file rather than
   guessed from an inferred compression tier. **Done.**

None is exotic and all are cheap. Each should be measured here before being
believed, in the same way everything else was.
