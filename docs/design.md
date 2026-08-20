# How PhotoCruller decides

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

This threshold is not the limit. The limit decides how different two frames may
be and still count as the same photograph; this decides which pairs are ever
compared at all. A pair the pool never nominates is never measured, so no limit
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
| Closer look | 190 ms | Only for pairs the full look called duplicates. Repeats the decision at 3200px, where fine detail survives, and drops the pair if it now reads as a different scene. |

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

## Which of two copies survives

**Round one only.** This ladder answers "which of these two files is the copy",
which is a question about files. Round two asks which photograph you like, and
nothing on this list is a substitute for an answer to that — the tool proposes
nothing there.

The keeper is chosen by the first rung that separates two files:

1. **Motion** — a frame carrying a Live Photo's video, since the video travels
   with it when it is culled and no other rung can replace what that loses.
2. **Format** — a raw beats a derived file.
3. **Not a computed depth blur** — a Portrait render loses to the frame it was
   computed from. Above resolution, because the blur is the larger file.
4. **Resolution** — more pixels.
5. **Nothing wrote it after the camera did** — an editor named in the Software
   tag, or a file clock moved away from the moment of capture.
6. **The camera's own marks** — the private block a camera writes and an editor
   does not regenerate.
7. **Not the spare frame of an HDR pair** — the merged exposure outlives the
   frame it was merged from. Below resolution: an HDR pair is always the same
   size, so this can never cull a larger frame for a smaller one.
8. **It proves it was saved again** — a comb of empty bins in the histogram of
   its stored coefficients, which one quantization cannot produce.
9. **The orientation flag is still set** — a camera records which way up it was
   held; software that turns a picture transposes the pixels and resets it.
10. **Finer quantization** — the matrix read straight from the header.
11. **Metadata richness** — the file that still knows when and how it was taken.
12. **Compression tier** — less lossy.
13. **Sharpness**.
14. **File size**.
15. **Path** — a coin toss, present only so the order is total and the plan
    does not depend on the order the folder was scanned in.

Rungs 3 and 5 to 8 are the only ones that are evidence rather than inference:
everything else is a property of one file, while those two say something
happened to it after the shutter. They sit above the compression rungs because
a re-save at higher quality beats its own source on those — measured on real
culls, where the tool kept a Windows Photo Viewer re-save over its iPhone
original.

The rung that decides is also the phrase the tool prints, taken from the same
list, so the two cannot disagree.

Sharpness settles about 69% of the pairs that reach it, so it is worth stating
exactly what it measures. The image is divided into a grid; in each tile the variance of a
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

## The limit

A pair is one photograph when its difference sits under one limit. One limit for
a whole folder — no second limit, and no subject detector.

An earlier design split the limit in two: one for photographs containing a
person or animal, a looser one for scenery, with a detector deciding which
applied. It was removed. The detector missed small subjects entirely, so a bird
in a landscape was silently judged by the loose limit, and the whole mechanism
was invisible — nothing in the interface showed which limit a pair had been
given. Curating the folder does the same job and can be seen.

There was also a dial: a run offered several limits as a list and you chose one
before the review. That went when round two stopped proposing culls. The dial
existed to let a person tune how much the tool would take, and round two takes
nothing — it gathers scenes and a person keeps what they want, so the question
the dial answered is now asked of every scene directly, by looking at it.

## Gathering a scene

Round two does not use the limit above, or the funnel, or the ladder. It asks a
different question — *have I taken too many of this?* — and the machinery for
"are these the same photograph" answers it badly. Measured on a folder of 8,000
nature photographs, the longest burst in it came out as **no group at all**:
fifty-five frames of a bird in flight, no two of them the same photograph.

So a scene is built from two things, cheap one first.

**One shoot.** Photographs within ninety minutes of each other. That number is
read off the library rather than chosen: the gaps between consecutive shots run
smoothly from fractions of a second upward with no natural cliff, until about
ninety minutes, where the largest single jump in the sorted gaps sits and 96% of
all gaps fall below.

**One scene.** Within a shoot, a photograph joins when its sketch agrees with
the scene's *own average* at 0.85 or better — not with whichever frame happens
to sit next to it. That distinction is the whole thing. Agreeing with a
neighbour lets a scene walk: a chain of neighbours ran from 2013 to 2019, one
photograph at a time, and held pairs that were anti-correlated. Measured against
the middle, the worst pair inside the largest scene went from −0.06 to 0.53.

Growing from the middle is also what holds a scene together while it changes —
the sun goes down and the colour moves through it, the eagle turns its head and
opens its wings, and every frame still agrees with what the scene is about.

**Where 0.85 came from.** Frames of one burst agree at 0.918 and frames of
different bursts at 0.343, so anything between is defensible. What settles it is
the difference between two real scenes: an evening of one sunset holds together
at 0.89, while eighteen views along a five-hour hike — all peaks and trees under
sky, every one a different place — sit at 0.76. At 0.85 the sunset stays whole
and the hike disperses, which is the right way round.

## The review

One page, one section per group, used by both rounds — because it is the same
act either way: looking at a set of photographs and saying which to keep.

What differs is the starting point. **Round one arrives with a plan**, so its
groups start read and leaving one alone means the plan stands. **Round two
arrives with nothing chosen**, so its groups start unreviewed, and leaving one
alone means exactly nothing.

That gives a group four states, and only three can be read from the checkboxes:
keeping some, keeping all, keeping none. The fourth is **unreviewed**, which
looks identical to keeping none and means the opposite. So it is held and shown
rather than inferred — dimmed, with a grey edge down the section, against a
green edge for a group that has been decided.

The consequence matters more than the display: an unreviewed scene cannot lose
a photograph, and not because a rule protects it. Nothing exists that says it
should go.

Nothing is left out of round one's page either — a relationship the tool can
prove is still a photograph leaving, and a proof nobody looked at is only a
claim.

**Every photograph of a group on screen together.** Choosing between twelve
frames means looking back and forth between them, comparing this one against
that one and back again. A view showing one at a time makes that impossible
however easy it is to step through — the comparison happens in memory rather
than on the page, which is where it is least reliable.

They are ordered by capture time inside the group, because that is the order
they happened in and the order a change makes sense in.

**Biggest groups first.** The review is where a person spends attention, and
the group of twelve is where it buys the most: eleven photographs that might
not be needed, against one in a pair. Ordering by least confident would put the
riskiest first, which is the right instinct for a review that decides safety —
and this one does not. The rules cull only what they can prove; what arrives
here is a choice about which frames are wanted.

**A verdict per photograph, not per pair.** Clicking the picture changes the
frame on screen; clicking a mark below changes another. A group can therefore
end with one kept, several, all of them — which refuses the group — or none,
which moves the lot. That last is a preference the tool could not previously
express, observed more than once: some sets are all worth losing.

**The marked frame is a starting position, not a decision.** A ladder picks it
— motion, then raw, resolution, untouched by an editor, metadata,
compression, sharpness — and
sharpness settles about 69%, the rung with the least evidence behind it.

Two measurements, and they disagree because they ask different things. Against
pairs where a person had *named the side they wanted*, the ladder agreed 2
times in 6: where somebody holds a preference, it is often a preference no
ranking over pixels can reach. Against groups drawn at random from a plan, it
agreed 24 times in 24 — on ordinary duplicates there is usually little to
choose between the frames, and the ladder picks a reasonable one.

So it is a good default, worth having so a plan can be accepted wholesale, and
worth one click to override.

**Groups are ordered least confident first**, by the largest difference inside
them, and a group holding a difference that could not be measured leads them
all: not knowing is the least confident state there is.

**Both buttons record everything.** Applying acts on the answers; quitting
moves nothing and returns to the settings, which is what several settings are
for. Either way every photograph's verdict is written down, and passes
accumulate rather than overwrite — looking at one setting and then another is
two opinions about the same folder, and the second does not cancel the first.

**A photograph the page cannot render is kept.** A file too corrupt to decode
is left out of the page, and anything left out was never seen, so it cannot
have been agreed to. Culling it would be culling unseen.

## Round one's rules

Ten of them, one file each in `scripts/derived/`, asked in order — the first
that holds gives the answer, and a pair no rule can account for goes to round
two. Each file opens with the name it produces, so landing in `rotated.py` tells
you what you are reading.

    duplicate   the same bytes under another name
    non-hdr     the frame the camera merged its HDR exposure from
    fake-blur   the depth blur it computed, beside the frame it came from
    identical   the same pixels in a different file, proven by a full decode
    export      a JPEG whose raw original is here too
    crop        a crop of the frame being kept
    rotated     a quarter turn of it
    edited      the same geometry with the tone moved
    smaller     the same picture at a lower resolution
    resave      the same picture, saved again more heavily

The order is the priority and it is not arbitrary: cheap and certain first, then
what must be argued from geometry, then the two that rest on file properties
alone.

Every name says what is wrong with the file being *removed*, not how the two are
related, so it reads as an instruction — *this one is a crop, delete it*. They
are one idea wearing ten labels: this file came from that one, and that one is
still here.

The provable relationship *is* the answer: a crop or a tone change is grouped
regardless of how large its measured difference is, because the edit is exactly
what makes the difference large, and the edit is what should go.

**A rule may claim derivation only if it proves it.** Three do so on their own —
a containment warp, a quarter turn, an untouched geometry with the tone moved.
Those three also prove *membership*: each is a change that moves the residual by
its own nature, so refusing them for reading far apart would be refusing them
for being what they are. The rest do not: being a raw beside a JPEG, holding
fewer pixels, or carrying a coarser quantization table are facts about two
files, not about a relationship between them. Those must also show the two pictures agree, by
comparing their sketches with brightness and contrast removed, so the question
asked is "the same picture?" and not "the same tone?". A pair that cannot show
it is a near-duplicate, and is labelled one.

Audited across four folders, the requirement changes no cull. It relabels about
3% of them — exactly the population whose evidence never supported the stronger
claim. Every cull is shown either way, so what this protects is the record: a
label is a statement about a relationship, and one that cannot be backed is
worth less than the plain answer.

The time window matters and is not the same for both. A crop or rotation is
accepted within 2 seconds. A tonal signature demands the same capture instant,
because "same geometry, the light moved" describes a breaking wave or a
changing expression just as well as it describes a brightness edit — measured
on labelled pairs, crop signatures on frames merely seconds apart are a
coin flip between a real crop and an optical zoom.

## Knowing how often it is wrong

The two rounds can be wrong in different ways, and only one of them can be
counted.

**Round one** makes a claim that is either true or false — this file came from
that one — so it can be checked exactly, and has been. Across ten folders,
every one of its 279 culls was either verified without the tool's help
(`identical` 114 of 114 pixel-for-pixel; `smaller` 32 of 32 by shrinking the
keeper and comparing; `duplicate` by hash) or looked at by eye. None was wrong.
Three rules were found under-firing during that check — camera pairs at 27 of
57, `rotated` at 0 of 19 — and none of them was over-firing.

The suite holds a case per rule, each built so that removing the rule it guards
makes it fail. That is the property worth having: a test that passes whether or
not the code is there tests nothing.

**Round two** decides nothing, so it has no error rate. Its mistake is a scene
gathered badly — too loose and unrelated photographs arrive together, too tight
and one burst becomes four — and there is no measurement for that, only looking.
The two cases that set its threshold were found that way: a sunset that must
stay whole, and a hike that must come apart.

There was once a blind audit mode, which drew culls at random and hid the tool's
verdict so a reviewer's answers meant something. It served the design where the
tool proposed everything. Round one is now checked cull by cull rather than
sampled, and round two proposes nothing to audit, so it was removed; it is kept
in `project/archive/` for reference.

## Safety

- **Nothing is ever deleted.** Redundant files are moved to a holding folder
  with a log, and one command puts every file back.
- **Sidecars and Live Photo videos travel with their photograph**, and return
  on undo.
- **Photo library packages are never entered.** A managed library is a
  database, not a folder of files.
- **The tool never writes into the folder it is scanning.** Everything it
  produces — plans, logs, reviews, moved files — goes to a working folder
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
