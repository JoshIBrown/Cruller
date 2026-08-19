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
for a specific reason: a *tonal edit* is precisely a change in luminance and
contrast with structure held constant, and the code currently detects it with
hand-set thresholds on brightness offset and contrast ratio. SSIM already
separates those terms by construction.

SSIM has its own documented limits — it assumes local structures matter
equally, and it does not handle spatial distortion — but the frames here are
aligned before comparison, which is the condition it wants.

## Choosing which frame survives: sharpness

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
the camera's own private block is still in it. Measured on 31 auto-culls across
three folders, those two speak for a quarter of them and are silent for the
rest; before they existed the direction was backwards on 6%.

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
alone, most carry their own: an exact copy and an identical picture need no
direction at all, a crop and a smaller copy are proved by containment, and a
raw is not made from a JPEG. Two do not. A **resave** and a **tonal edit**
leave the geometry untouched, so nothing about the pictures says which came
first, and the direction rests on the compression rungs alone unless the camera
marks happen to speak. On the three folders measured that was 10 of 31
auto-culls. This is the gap double-compression detection closes, and it is why
that item ranks above the other two.

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
a clean comb is acted on.

**What it does not catch.** Saving again more *coarsely* collapses values
together rather than leaving gaps, and looks like a photograph with less detail
in it. That is the right half to miss: a coarser re-save already loses to its
source on the compression rungs, while a finer one beats them. On 30 real
auto-culls the comb spoke on 3, agreed with the camera marks every time it and
they both spoke, and proved one direction the marks could not.

## Choosing the best frame of a burst

**Here:** not attempted. Every distinct frame is kept.

**In the literature:** no-reference image quality assessment. BRISQUE scores
naturalness from local luminance statistics against a model trained on known
distortions; NIQE uses the same family of statistics but is trained only on
undistorted images, so it is not tied to particular distortion types. Published
burst-selection systems combine a global quality filter with a content
comparison, which is close to the shape this would need.

**Why it stays unattempted:** picking the frame where somebody is smiling is a
judgement about content, and no quality metric answers it.

## What follows from all this

Three of these have a documented method that answers a question currently
answered by inference:

1. An asymmetric dissimilarity, so derivation has a direction that was measured
   rather than assumed from which file holds more pixels. **Still open.**
2. Resampling detection, so an upscale cannot pass for an original. **Open, and
   the least urgent** — measured against real culls, keepers read 0.98 of the
   culled file's detail reach where an enlargement would read 0.41.
3. The quantization table, so a re-save is read from the file rather than
   guessed from an inferred compression tier. **Done.**

None is exotic and all are cheap. Each should be measured here before being
believed, in the same way everything else was.
