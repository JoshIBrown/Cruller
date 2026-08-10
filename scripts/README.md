# The code

What each file owns, how a run flows through them, and the invariants a change
must not break. For why the tool decides the way it does — the thresholds, the
measurements behind them, and what was tried and rejected — see
[docs/design.md](../docs/design.md) and [docs/dead-ends.md](../docs/dead-ends.md).

## The files

| | |
|---|---|
| `cull.py` | The command: arguments, the review loop, applying, undoing, reset. Owns everything a person sees |
| `sift.py` | The engine: reads a folder, finds candidates, groups them, ranks each group, writes the plan |
| `verify.py` | One question answered well — are these two frames the same photograph? Alignment and the residual |
| `loaders.py` | Reading pictures and metadata across formats, including raws without demosaicing |
| `config.py` | The one setting: where the tool's output goes. Asked once, remembered |
| `dashboard.py` | A single page summarising what has been culled, job by job |

`settings.conf` is the only file here meant to be edited, and the first run
writes it for you.

## A run, end to end

1. `cull.py` parses the arguments and hands a folder to `sift.main`.
2. `sift.py` walks it, fingerprints every file, and reads each photograph once —
   producing a sketch, a sharpness score, dimensions and metadata.
3. Candidates come from two pools: frames whose frequency signatures agree, and
   frames taken close together. Their union goes forward.
4. Each pair is screened cheaply, then — if it survives — settled by
   `verify.compare`, which aligns the two frames and measures what is left.
5. Survivors are grouped around a keeper chosen by the ranking ladder, and the
   result is written as a plan: one row per file, with its verdict and why.
6. `cull.py` offers the outcomes the dial can produce, renders proof images for
   the one chosen, and — only if asked — moves files and writes a log.

## Invariants

**Nothing is ever deleted.** Files are moved and logged, and the log is the
authority for putting them back. A change that deletes a photograph is wrong
however good its reason.

**The tool never writes into the folder being scanned.** Everything it produces
goes to the working folder, which is refused if it sits inside that tree.

**Caches are keyed by content, never by path or time.** A file that moved is not
re-read; a file that changed is. Every cache entry carries a version, and any
change to what is stored must raise it: a cache that answers with a stale shape
is worse than no cache at all.

**A cheap test may only reject.** The sketch and the keypoint screen exist to
say no quickly. Only the full comparison may say yes, so a cull never rests on
a shortcut.

**No alignment, no cull.** A pair too dark or too flat to align reliably is
kept, both frames. A crash during comparison is not a verdict: it is counted
and reported, never cached.

**A cull that skips review must prove derivation.** Reasons resting on file
properties — a raw beside a JPEG, fewer pixels, a coarser quantization table —
must also show the two pictures agree. Otherwise the pair is judged and shown.

**The residual is measured both ways.** Warping softens the frame being moved,
so the answer depends on which frame is named first. The larger difference
wins: if either view says these are two photographs, both are kept.

## Concurrency

Reading runs in a process pool, so anything those workers need must survive
being imported afresh — a value patched in the parent does not reach them.

Comparison runs in a thread pool sharing the in-memory caches, so every read,
insert and eviction happens under a lock. Decodes stay outside it; only
bookkeeping is inside.

Verdicts are held in memory for the life of a run as well as on disk. Two
settings compared inside one process are therefore not a fair test: the second
finds the first's work already done.

RANSAC is seeded inside a lock, so a fit cannot depend on what else is running.

## What a run writes

    Culled Photos/<job>/      what was moved, original structure kept
    Spot Checks/<job>/        proof images: keeper beside what it replaces
    Records/<job> - plan.csv  every file, its verdict, its group, and why
    Records/<job> - log.csv   what moved where; the authority for undo
    Records/labels.csv        cumulative judgements: approved, or retracted
    Cache/probe.db            what was read, every verdict, every screen

A job is named for its date and source folder, so two runs over one folder on
one day are numbered rather than overwriting each other. The plan is authority
for applying; the log is authority for undoing.

## Changing a threshold

Every number that decides something carries its measurement in a comment beside
it. Move one and you must measure it the same way and replace the comment — a
threshold with a stale justification is how the next reader is misled.
