# What is open

Known gaps and unfinished work, in rough order of how much they matter. Things
that were tried and rejected are in [dead-ends.md](dead-ends.md) instead.

## An honest error rate

Every accuracy figure the tool can currently quote comes from pairs it chose to
show for review — sorted worst-first, and a small fraction of any plan. That is
the one sample which cannot estimate its own error rate.

The fix is a uniform random draw from a run's plan, with no sorting, judged
blind. Thirty pairs gives about ±10 percentage points, a hundred gives ±6.
Until that exists, "the tool is right about X% of culls" is unsupported.

Reviewing more of the worst-first list does not substitute for it: across the
range one reviewer covered, their disagreement rate was flat — 13%, 10%, 13% by
third — so the ranking carries no information about where disagreements are.

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

The tool is five Python files that import each other. For something meant to be
downloaded and run by anyone, one file would be better.

## A run report

Proof images answer "was this cull right". Nothing yet answers "what did this
run do" in one page — space reclaimed, what was grouped and why, keeper beside
each replaced frame.
