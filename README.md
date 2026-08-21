# PhotoCruller

Point it at a folder of photographs. It settles the copies, gathers what is left
into scenes, and lets you keep what you want from each.

**Nothing is ever deleted.** Everything it removes moves to a holding folder
with a log, and one command puts it all back.

```bash
./crull "/path/to/some/photos"          # the two rounds, with review
./crull "/path/to/some/photos" --apply  # take the plan as it stands
./crull "<a folder of culls>"           # look through that job's reviews again
./crull --undo "<job name>"             # put a job back
./crull --reset                         # undo everything, clear every cache
```

macOS users can drag a folder onto `PhotoCruller.app` instead.

## Two rounds, two questions

**Round one — copies.** Where one file came from another that is also here, a
rule names it and it goes. Ten rules, one file each in `scripts/derived/`, asked
in order:

    duplicate   byte-identical to the one being kept
    non-hdr     the frame the camera merged its HDR exposure from
    fake-blur   a depth blur the camera computed, not the frame it shot
    identical   the same pixels in a different file, proven by a full decode
    export      a JPEG whose raw original is also here
    crop        a crop of the frame being kept
    rotated     a quarter turn of it, with the orientation flag reset
    edited      the same geometry with the tone moved
    smaller     the same picture at a lower resolution
    resave      the same picture, more heavily compressed

Each says what is wrong with the file being removed, so it reads as an
instruction: *this one is a crop, delete it.* Every rule must prove its case —
the pictures agreeing, a containment warp, a mark the camera wrote — and one
that cannot say nothing, leaving the pair to round two.

**Round two — scenes.** What survived is gathered into scenes: one shoot's worth
of one subject. A shoot is photographs within ninety minutes of each other; a
scene is the ones inside it that look alike. Nothing here is provable, so the
tool chooses nothing. It shows each scene, largest first — the thing you took
most photographs of — and you keep what you want. The rest of that scene moves
out with the copies, and a scene you never review is left whole.

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

A pair is one photograph when that residual sits under the limit. One limit, no
second one, no subject detector.

A pair that can be **proved** derived — one frame's warp landing inside the
other, a quarter turn, identical geometry with the tone moved — belongs together
whatever it measures, because the edit is exactly what makes the difference
large. Refusing those for reading far apart would be refusing them for being
what they are.

All of that is round one. Round two never asks this question: a burst of a bird
in flight is one scene and no two frames of it are the same photograph, so it
reads a sketch instead. See below.

Candidates come from two pools, unioned: photographs that **look alike** (a
frequency signature of the sketch — its low frequencies, thresholded, with
brightness dropped, so a re-toned copy still matches) and photographs **close
in time** (bursts chained at under 3 seconds). Measured against exhaustive
all-pairs comparison, this misses nothing.

Which frame survives is decided by a ladder: carries a Live Photo's video →
raw → not a computed depth blur → resolution → nothing wrote it after the
camera did → the camera's own marks → not the spare frame of an HDR pair → it
proves it was saved again → the orientation flag is still set → finer
quantization → metadata richness → compression tier → sharpness → file size.

That ladder settles **round one only** — which of two files is the copy. It has
nothing to say about round two, where a person picks the frame they like and no
measurement is a substitute for that.

Eight of its rungs exist to keep originals, because a copy is only obvious when
it is smaller. Four are evidence rather than inference: they say something
happened to a file after the shutter, where every rung below them only says how
big or how sharp it is.

**Nothing wrote it after the camera did** reads two things. An editor signs the
Software tag, which is decisive but rare — 83% of an ordinary library carries a
Software tag and only 4% names an editor, the rest being the phone's OS
version, which an edit made on the phone leaves alone. So it also reads the
file's own clock: a camera leaves it at the moment of capture and an editor
moves it, which was true of every file an editor had signed and of 3% of the
rest. It sits below resolution so a small edit can never beat a full frame, and
it decides what nothing else can see — a red-eye fix, a colour conversion, a
tonal change alter no dimension at all.

**What the camera computed, and what it computed from.** A phone shooting HDR
or Portrait writes two files for one press of the shutter and marks them in
EXIF. The answer differs by kind, so these are two rungs. A **Portrait** pair is
a depth blur and the frame it was computed from; the blur is an effect rather
than a photograph, and it is written at the full sensor size while the untouched
frame is smaller — so that rung sits above resolution, or the effect wins on
pixels. An **HDR** pair is a merged exposure and the frame it was merged from,
always at the same size, so that rung only has to outrank file size. Judged
across 30 pairs: the untouched frame every time for Portrait, the merge every
time for HDR.

Because the camera recorded the relationship rather than the tool inferring it,
these are settled without anybody looking, under their own reasons — *spare of
*non-hdr* and *fake-blur* — rather than going to the review as
near-duplicates.

**Saved again** is the only rung the photograph proves about itself, without
reference to metadata anyone could have copied across. A JPEG stores each block
as whole numbers; saving it again with a finer table divides those by a smaller
step, which can only land on some of the new integers, so the histogram grows a
comb of empty bins that a single pass cannot produce. Reading it means decoding
the file's entropy-coded data rather than its pixels, because the round trip
through pixels leaves the numbers a median of 0.2 off the nearest integer and
the comb with them. That costs about 200ms a file, so it is read
as little as possible: the rung can only ever demote, so the candidates left
are put in order on the cheap rungs below it and read down until one does not
prove a second save. That is usually the first file asked. On a folder of 140
it is read nine times rather than 140.

It catches one half of the problem, and it is the half that matters: a re-save
at *coarser* quality already loses on the compression rungs, while a finer one
beats them, which is how a Windows Photo Viewer re-save came to be kept over
its iPhone original. Only a clean comb counts — anything in between is read as
saying nothing, since a rung that acts on a weak reading is a guess wearing
evidence's clothes.

**The orientation flag** records which way up the camera was held, leaving the
pixels alone; software that turns a photograph transposes the pixels and resets
the flag. It is still set on 45% of files that have the camera's block and on
3% of those that do not. It decides a quarter-turn pair, where everything above
it ties — a lossless rotate carries the metadata across, so even the marks tie
— and file size was choosing instead. The turned copy is about 0.1% larger,
because the turn moves the picture against the 8x8 grid, so the sideways frame
was winning every time.

**The camera's own marks** is the private block a camera writes and no editor
regenerates: absent from every file an editor had signed, present on 90% of the
rest. Where one of two frames still has it, that frame is the earlier
generation. Both rungs sit above the compression ones because a re-save at
higher quality beats its own source there — it spends more bytes on pixels it
has already degraded, and on real culls that was enough to keep the copy.

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

**Round one — the copies.** Where one file came from another that is also here,
there is nothing to judge, so they are counted, their reasons named, and offered
as one decision:

    ROUND ONE · copies
    25 files here came from another file that is also here · 65 MB
        13  non-hdr     the frame the camera merged its HDR exposure from
        11  crop        a crop of the frame being kept
         1  identical   the same pixels in a different file

    each one is provable, and named. nothing else is touched.
    [r]eview them  ·  [a]pply  ·  [s]kip  ·  [q]uit

Settling them first also keeps round two honest — a folder holding three copies
of everything gathers strangely until they are gone.

**Round two — the scenes.** What survived is gathered into scenes and each is
put in front of you, largest first, because the scene there are most of is where
attention buys the most.

    ROUND TWO · scenes
    33 scenes · 101 photographs · the biggest holds 13
    nothing is chosen for you here. keep what you want from each;
    a scene you do not review is left alone.

The page shows **one section per scene**, every photograph in it at once, in the
order they were taken. Click a photograph to keep it; **keep all** and **keep
none** decide a whole scene at once.

A scene is in one of four states, and the page says which: **unreviewed**,
**keeping some**, **keeping all**, **keeping none**. Unreviewed is the one that
matters — it looks exactly like keeping none and means the opposite, so it is
shown rather than guessed at, and an unreviewed scene cannot lose a photograph.
Not because a rule protects it, but because nothing exists that says it should
go.

**Move what I did not keep** moves the rest of every scene you reviewed. **Quit**
moves nothing. Both write down every judgement, per photograph, because an
opinion about a photograph is the one thing here that cannot be worked out
again.

### How often is it wrong?

Round one has been checked cull by cull. Across ten folders every one of its
279 culls was either verified exactly — `identical` 114 of 114 pixel-for-pixel,
`smaller` 32 of 32, `duplicate` by hash — or looked at by eye, and none was
wrong. The suite in `project/` holds a case for every rule, each built so that
removing the rule it guards makes it fail.

Round two cannot be wrong in the same way, because it decides nothing. Its
mistake is a scene gathered badly — too loose and unrelated photographs arrive
together, too tight and a burst is split — and the only test for that is
looking.

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
