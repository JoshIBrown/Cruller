# What is open

Known gaps and unfinished work, in rough order of how much they matter. Things
that were tried and rejected are in [dead-ends.md](dead-ends.md) instead.

## A burst frame where anything moved cannot be culled gently

A pair is scored on its worst block of about thirty thousand, so one region
changing completely sets the score for the whole pair. Measured on real burst
frames a second apart: the median block difference is 2% — over almost all of
the frame they are the same photograph — while the score is 75%, because
somebody moved.

That is the measure doing its job. Fine blocks and a maximum were chosen so a
changed expression could not be averaged away, and it works: a coarse grid
scored that at 4.5% and hid it. The cost is that a burst where anything at all
moved reads as two different photographs.

Scoring on a high block rather than the worst one was measured and refused —
see the dead ends. Separating the two cases needs to know whether the small
thing that changed is a subject, which is a question about content.

## Strongly recomposed copies

The cheap sketch cannot see that two frames are the same scene when one has
been heavily cropped or reframed. The keypoint screen catches copies made at
the same instant, but a recomposition seconds later still slips through: on one
audit, 8 of 20 newly nominated pairs died exactly there.

## Best-of-burst

Within a burst of genuinely different frames, the tool keeps them all by
design. A person often wants one — the frame where the subject faces the
camera, or where nobody blinked. This is preference among different
photographs, which is a different job from finding duplicates, and it needs the
subject recognition that was removed for good reasons. Wanted, but blocked.

## Sharpness and noise

The keeper measure responds to noise as well as to focus, so between two frames
where one is grainier it can prefer the noisier one. Denoising first was
measured and made things worse. No good answer yet.

## Orientation metadata

Rotation recorded in metadata rather than in pixels is not consistently applied
before comparison, so a photograph that is upright on screen may be compared
sideways.

## Consolidation

The tool is six Python files that import each other. For something meant to be
downloaded and run by anyone, one file would be better.

## A run report

The review answers "is this cull right" while there is still time to say no.
Nothing yet answers "what did this run do" afterwards, in one page: space
reclaimed, what was grouped and why, and what was refused.
