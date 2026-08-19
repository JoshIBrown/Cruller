#!/usr/bin/env python3
"""
sift.py - go through one mixed folder and work out what can go.

Built for a folder holding a jumble of things: camera raws, exported JPEGs,
re-saved copies, resized copies, and near-identical frames from the same burst.
It sorts every image into groups that show the same picture and, inside each
group, decides which single file is worth keeping.

    python3 sift.py "/path/to/folder"                 # report + manifest, no changes
    python3 sift.py "/path/to/folder" --recursive

Every duplicate is labelled with WHY it is a duplicate:

    exact copy        byte-identical, under another name
    identical picture same pixels, different file bytes — proven by full decode
    resave            same picture, more heavily compressed
    smaller copy      same picture at lower resolution
    export of raw     a JPEG whose raw original is also in this folder
    near-duplicate    a different frame of the same moment

Keeping order, best first: raw or lossless beats JPEG; larger beats smaller;
less compressed beats more compressed; sharper beats softer.

Nothing is deleted or moved: this writes a manifest and stops. cull.py is the
tool that acts on it.
"""
import argparse, csv, hashlib, io, json, os, sys
from collections import defaultdict
import numpy as np
from PIL import Image
from multiprocessing import Pool

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from loaders import (open_image, exif_time, time_fallback, quantization_tier,
                     quantization_mean,
                     pixel_dims, is_raw, shot_info, IMG_EXT, HAVE_HEIF)
try:
    import verify as _verify          # imports cv2; absence lands in except
    HAVE_VERIFY = True
except Exception:
    HAVE_VERIFY = False

def _clock(secs):
    """A duration a person can read at a glance."""
    secs = int(secs)
    if secs >= 3600:
        return f"{secs // 3600}h{secs % 3600 // 60:02d}m"
    if secs >= 60:
        return f"{secs // 60}m{secs % 60:02d}s"
    return f"{secs}s"


def _cursor(visible):
    """Hide the block cursor while a line is being redrawn under it."""
    if sys.stderr.isatty():
        sys.stderr.write("\033[?25h" if visible else "\033[?25l")
        sys.stderr.flush()


def progress(done, total, label, width=32, counts=True, note=None):
    """One self-erasing line on stderr. Silent when output is piped to a file.

    Throttled by time, not by count: an update lands every fifth of a second
    however fast or slow the stage is, and the final count always lands.

    A stage still running shows how long is left; a finished stage keeps its
    line and shows what it took. Both read the same clock, started the first
    time that stage reports. A new stage always draws at once, whatever the
    throttle says, so a slow first step never looks like a hang.

    `counts` off leaves the item column blank but still occupies it, for a
    stage whose numbers would mean nothing to anyone watching; `note` puts
    something readable there instead. The column is as wide as the largest
    count this run has shown, so the clock stays in one place down the screen.

    A caller that has claimed the line can register `_relay` to hear about the
    reports it is suppressing. Without that, a stage whose work happens inside
    something else has no way to show it is alive — which is how the settings
    scan came to sit at 0% for a minute looking hung. The estimate is deliberately plain — work done
    over time spent — because stages here are uniform enough that anything
    cleverer would only be wrong more precisely.

    With PHOTOCRULLER_PLAIN_PROGRESS set, emits parseable `@progress label|d|t`
    lines instead — that is how the window shows a live percentage without
    pretending to be a terminal.
    """
    only = getattr(progress, "_only", None)
    if not total:
        return
    if only is not None and only != label:
        relay = getattr(progress, "_relay", None)
        if relay:
            relay(done, total)    # the owner decides what, if anything, to draw
        return
    import time
    now = time.time()
    fresh = getattr(progress, "_label", None) != label
    if not fresh and done < total and now - getattr(progress, "_t", 0.0) < 0.2:
        return
    progress._t = now
    if os.environ.get("PHOTOCRULLER_PLAIN_PROGRESS"):
        # Whole numbers only: a stage may measure itself in fractions, but
        # anything parsing this expects counts. Scaled to tenths of a
        # percent so a fractional bar survives the trip.
        sys.stderr.write(f"@progress {label}|{round(done / total * 1000)}|1000\n")
        sys.stderr.flush()
        return
    if not sys.stderr.isatty():
        return

    # One stage runs at a time, so the previous stage's clock is finished with.
    if fresh:
        progress._label, progress._start = label, now
        if not getattr(progress, "_hidden", False):
            _cursor(False)
            progress._hidden = True
            import atexit
            atexit.register(_cursor, True)
    spent = now - progress._start

    pct = done / total
    bar = "#" * int(pct * width) + "-" * (width - int(pct * width))
    if done >= total:
        tail = f"  {_clock(spent)}"
    elif done and spent > 1:
        tail = f"  {_clock(spent * (total - done) / done)} left"
    else:
        # Nothing to predict from yet. Count up rather than saying
        # "estimating" forever: a stage whose first step is slow has to look
        # alive, and a number that moves is the only thing that says so.
        tail = f"  {_clock(spent)}"
    field = note if note is not None else (f"{done:,}/{total:,}" if counts else "")
    progress._cw = max(getattr(progress, "_cw", 0), len(field))
    sys.stderr.write(f"\033[2K\r  {label:<22s} [{bar}] {pct * 100:3.0f}%  "
                     f"{field:>{progress._cw}}{tail}")
    sys.stderr.flush()
    if done >= total:
        sys.stderr.write("\n")
        _cursor(True)
        progress._hidden = False


THUMB = (256, 144)

SCREEN_W = 700          # keypoints for the geometric screen are found at this width
BS, GRID, TOPK, SIGMA, MAXSHIFT = 8, 8, 5, 0.42, 12


def quick_hash(path, chunk=1 << 20):
    """Fingerprint from file size plus the head and tail of the file.

    Hashing whole files would mean reading hundreds of gigabytes on a folder of
    raws. Two distinct photos essentially never share a size and both ends.
    """
    h = hashlib.md5()
    size = os.path.getsize(path)
    h.update(str(size).encode())
    with open(path, 'rb') as fh:
        h.update(fh.read(chunk))
        if size > chunk * 2:
            fh.seek(-chunk, os.SEEK_END)
            h.update(fh.read(chunk))
    return h.hexdigest()


# Application-owned photo libraries look like folders but are private databases.
# Culling inside one corrupts it. Refused as a target, skipped in a scan.
LIBRARY_PKG_EXT = {'.photoslibrary', '.photolibrary', '.aplibrary',
                   '.migratedphotolibrary', '.lrlibrary', '.lrcat'}


def is_library_package(path):
    return os.path.splitext(path.rstrip(os.sep))[1].lower() in LIBRARY_PKG_EXT


def scan(folder, recursive, exclude=()):
    """All images under `folder`. Anything in `exclude` (the working folder,
    typically) is skipped if it turns up inside the tree — its contents are
    tool output, not library. Photo-library packages are skipped too: those
    are Photos/Lightroom databases, not folders of files."""
    exclude = {os.path.abspath(e) for e in exclude if e}
    out = []
    if recursive:
        for dp, dn, fn in os.walk(folder):
            dn[:] = [d for d in dn if not d.startswith('.')
                     and not is_library_package(d)
                     and os.path.abspath(os.path.join(dp, d)) not in exclude]
            for f in fn:
                if not f.startswith('.') and os.path.splitext(f)[1].lower() in IMG_EXT:
                    out.append(os.path.join(dp, f))
    else:
        for f in sorted(os.listdir(folder)):
            p = os.path.join(folder, f)
            if not f.startswith('.') and os.path.isfile(p) and os.path.splitext(f)[1].lower() in IMG_EXT:
                out.append(p)
    return sorted(out)


# Everything _probe extracts is a pure function of the file's bytes, so probe
# results are cached in the working folder keyed by content fingerprint — a
# re-run pays for fingerprints (two megabytes per file) instead of decodes,
# and entries survive renames, culls and undos. Bump the version whenever
# _probe or loaders change what gets extracted; old rows are then ignored.
# Programs that stamp their name into the Software tag when they write a file.
# A camera writes its own model there, and a file nothing has touched carries
# no such name — so between two frames of one group, the one without is the
# earlier generation. Names only, never versions, so a new release still reads.
EDITORS = ("photoshop", "lightroom", "gimp", "photo gallery", "picasa",
           "snapseed", "pixelmator", "affinity", "luminar", "capture one",
           "acdsee", "corel", "on1", "photos ", "photoscape", "paint.net")

PROBE_VERSION = 6      # the camera's own marks are read


# Verdicts are pure functions of two files' bytes as well, so the full-look
# result for a pair is cached beside the probe rows. On a repeat run the
# expensive stage — decode, align, warp both ways at 1600px — collapses to a
# lookup. Bump when verify.py or REVIEW_SIZE change what a verdict means.
VERDICT_VERSION = 1
# The keypoint screen's answer is a property of two photographs, so it keeps
# like a verdict. Held only in memory it made repeat rounds fast but left a
# fresh run paying for it again; on disk the first grouping is fast too.
SCREEN_VERSION = 1


def _cache_open():
    try:
        import config, sqlite3
        wd = config.working_dir()
        if not wd:
            return None
        os.makedirs(os.path.join(wd, "Cache"), exist_ok=True)
        # Two runs at once must not kill either: wait for the other to finish
        # its write rather than raising "database is locked" mid-folder.
        db = sqlite3.connect(os.path.join(wd, "Cache", "probe.db"),
                             check_same_thread=False, timeout=30)
        db.execute("CREATE TABLE IF NOT EXISTS probe (md5 TEXT PRIMARY KEY, v INT, blob BLOB)")
        db.execute("CREATE TABLE IF NOT EXISTS verdict "
                   "(a TEXT, b TEXT, v INT, js TEXT, PRIMARY KEY (a, b))")
        db.execute("CREATE TABLE IF NOT EXISTS screen "
                   "(a TEXT, b TEXT, v INT, js TEXT, PRIMARY KEY (a, b))")
        return db
    except Exception:
        return None


# Only content-derived fields live in the cache. `path`, `bytes`, `md5` and
# the capture-time fallback are per-file facts filled in at run time.
_CACHED_SCALARS = ('sharp', 'w', 'h', 'tier', 'qmean', 'raw', 'meta', 'edited',
                   'maker', 'moved',
                   'focal', 'exposure', 'exif_t')


def _pack(r):
    scal = {k: r[k] for k in _CACHED_SCALARS}
    scal['sshape'] = list(r['sshape'])
    bio = io.BytesIO()
    np.savez_compressed(
        bio, thumb=r['thumb'],
        spts=r['spts'] if r['spts'] is not None else np.empty(0, np.float32),
        sdes=r['sdes'] if r['sdes'] is not None else np.empty(0, np.uint8),
        scal=np.frombuffer(json.dumps(scal).encode(), dtype=np.uint8))
    return bio.getvalue()


def _unpack(blob):
    try:
        z = np.load(io.BytesIO(blob), allow_pickle=False)
        scal = json.loads(bytes(z['scal']).decode())
        spts, sdes = z['spts'], z['sdes']
        r = dict(thumb=z['thumb'],
                 spts=spts if len(spts) else None,
                 sdes=sdes if len(sdes) else None,
                 sshape=tuple(scal.pop('sshape')))
        r.update(scal)
        return r
    except Exception:
        return None


def _fp(path):
    try:
        return quick_hash(path)
    except OSError:
        return None


def _probe_pair(pm):
    return _probe(pm[0], pm[1])


# The long edge every photograph is reduced to before anything measures it,
# worked out from the file's own dimensions rather than asked for and hoped.
# The decoder can only halve, and a fixed 1920x1080 request meant a portrait
# never halved at all — its width fell below 1920 after one step, so the full
# image came back. Portraits cost 4x their landscape twins and were scored for
# sharpness at 4x the detail, which made the number incomparable between
# orientations. Deriving the factor gives exactly one answer per file.
#
# Halving only, never a resize. The decoder reduces by powers of two, which is
# exact — each pixel is the mean of a 2x2 block — and free inside a JPEG decode.
# Landing on an exact 2000 instead needs an interpolating filter that smooths
# the image, which is the very thing sharpness measures, and it costs 8%.
#
# It was tried, on the reasoning that a size that merely lands between 2000 and
# 3999 cannot be compared between photographs. Measured: of 1,145 groups, 823
# reach sharpness with everything above it tied, and **none** hold contenders
# that halve differently — same pixel count means same dimensions in practice.
# The bound is the guarantee; the exactness was solving nothing.
#
# 2000 and not less. Halving again moves the keeper in 7% of Art groups and 4%
# of Food groups, and shifts which photographs are culled, for 3-6% of a run
# real decisions traded for noise. Among the groups sharpness actually
# decides it is nearer a third, measured on 30 landscape groups.
READ_LONG = 2000


def _read_size(w, h, target=READ_LONG):
    """The halvings to apply, and the size that leaves.

    Used by both passes that decode a photograph. Asking for a fixed box
    instead stops the decoder halving whenever either side
    of the halved image falls under the box, so it hands back the full frame.
    """
    f = 1
    while max(w, h) // (f * 2) >= target:
        f *= 2
    return f, (max(1, w // f), max(1, h // f))


def _probe(path, md5=None):
    """One pass per file: thumbnail, sharpness, dimensions, compression, hash."""
    try:
        im = open_image(path)
        ex_t = exif_time(im)
        im.draft('L', _read_size(*im.size)[1])
        # Greyscale is wanted for exactly two things — the thumbnail and the
        # sharpness score — so it is prepared for those and nothing else. The
        # thumbnail is resized by the imaging library straight from the 8-bit
        # image; building a float32 copy and casting it back to 8-bit to
        # do the same job, which cost 3% of reading for nothing. The sharpness
        # maths stays in float32: 16-bit integers halve the memory but numpy
        # promotes their variance to 64-bit, which measured 8% slower.
        gi = im.convert('L')
        thumb = np.asarray(gi.resize(THUMB), dtype=np.uint8)
        g = np.asarray(gi, dtype=np.float32)
        lap = (g[:-2, 1:-1] + g[2:, 1:-1] + g[1:-1, :-2] + g[1:-1, 2:] - 4 * g[1:-1, 1:-1])
        h, w = lap.shape
        th, tw = max(h // GRID, 1), max(w // GRID, 1)
        tiles = lap[:th * GRID, :tw * GRID].reshape(GRID, th, GRID, tw).swapaxes(1, 2)
        tv = tiles.reshape(GRID, GRID, -1).var(axis=2)
        ys, xs = np.mgrid[0:GRID, 0:GRID]
        c = (GRID - 1) / 2
        wgt = np.exp(-(((xs - c) / c) ** 2 + ((ys - c) / c) ** 2) / (2 * SIGMA ** 2))
        sharp = float(np.sort((tv * wgt).ravel())[::-1][:TOPK].mean())
        md5 = md5 or quick_hash(path)
        # A re-encode usually loses the capture metadata. When two files hold the
        # same picture at the same size, the one that still knows when it was
        # taken is the earlier generation.
        meta, edited, maker, moved = 0, False, False, False
        try:
            if is_raw(path):
                meta = 2
            else:
                with Image.open(path) as im2:
                    ex = im2.getexif()
                with open(path, 'rb') as fh:
                    head = fh.read(300000)
                meta = (1 if len(ex) >= 5 else 0) + (1 if b'ns.adobe.com/xap' in head else 0)
                # An editor signs its work in the Software tag; a file straight
                # from a camera carries the camera's name or nothing. Noted
                # here, compared later: whole folders arrive processed — two in
                # three files carrying one editor's name is ordinary for work
                # delivered by a professional — so this means something only
                # between two frames of one group.
                edited = any(e in str(ex.get(t) or "").lower()
                             for t in (305, 11) for e in EDITORS)
                # Two marks the camera leaves and an editor does not, both free
                # here. The Software tag above only catches an editor that
                # names itself, which is 4% of these files — the rest say the
                # phone's OS version, which an edit made on the phone does not
                # change. These two do not depend on recognising a name.
                sub = ex.get_ifd(0x8769)
                # The camera's private block. Editors do not regenerate it:
                # absent on 100% of files an editor signed, present on 90% of
                # the rest.
                maker = bool(sub.get(37500))
                # A camera leaves the file's clock at the moment of capture.
                # Moved on 100% of files an editor signed, on 3% of the rest.
                shot_at, written_at = sub.get(36867), ex.get(306)
                moved = bool(shot_at and written_at and shot_at != written_at)
        except Exception:
            pass
        # Keypoints for the geometric screen, taken here because the frame is
        # already decoded. Doing it per pair instead meant decoding two raws
        # just to find out they show different scenes — which is the answer for
        # most candidate pairs in a folder of bursts.
        spts = sdes = None
        try:
            import verify as _v
            small = np.asarray(Image.fromarray(g.astype(np.uint8))
                               .resize((SCREEN_W, max(1, int(SCREEN_W * g.shape[0] / g.shape[1])))))
            spts, sdes = _v.screen_features(small)
        except Exception:
            pass
        w0, h0 = pixel_dims(path)
        shot = shot_info(path)
        return dict(path=path, thumb=thumb, sharp=sharp, w=w0, h=h0,
                    spts=spts, sdes=sdes, sshape=(int(SCREEN_W * g.shape[0] / g.shape[1]), SCREEN_W),
                    tier=quantization_tier(path), raw=is_raw(path), meta=meta,
                    qmean=quantization_mean(path), edited=edited,
                    maker=maker, moved=moved,
                    exif_t=ex_t, md5=md5, bytes=os.path.getsize(path),
                    focal=shot['focal35'], exposure=shot['exposure'])
    except Exception as e:
        return dict(path=path, error=str(e)[:70])


class Comparer:
    """Thumbnails are held as uint8 and cast per comparison — as float32 a
    folder of 28,000 would need 4.2 GB of thumbnails alone."""

    def __init__(self, T):
        self.T = T
        self.win = np.outer(np.hanning(T.shape[1]), np.hanning(T.shape[2]))
        self.fft = {}

    def _t(self, i):
        return self.T[i].astype(np.float32)

    def _F(self, i):
        if i not in self.fft:
            self.fft[i] = np.fft.rfft2(self._t(i) * self.win)
            if len(self.fft) > 3000:
                self.fft.pop(next(iter(self.fft)))
        return self.fft[i]

    def _blk(self, a):
        h, w = a.shape
        return a[:h // BS * BS, :w // BS * BS].reshape(h // BS, BS, w // BS, BS)

    def compare(self, i, j):
        """Camera shake removed by phase correlation, then the block residual.

        Measured both ways round, but only one correlation is computed: naming
        the pair the other way conjugates it, so the shift is simply negated
        and the overlapping crops come out the same two regions swapped. The
        pixel differences are therefore identical either way and only the
        texture term changes — so the second inverse FFT, which was 45% of
        this method and 90% of a warm run, buys nothing.
        """
        R = self._F(i) * np.conj(self._F(j)); R /= (np.abs(R) + 1e-9)
        r = np.fft.irfft2(R, s=self.T[i].shape)
        p = np.unravel_index(np.argmax(r), r.shape)
        dy = p[0] if p[0] < self.T.shape[1] // 2 else p[0] - self.T.shape[1]
        dx = p[1] if p[1] < self.T.shape[2] // 2 else p[1] - self.T.shape[2]
        if abs(dy) > MAXSHIFT or abs(dx) > MAXSHIFT:
            dy = dx = 0
        A, B = self._t(i), self._t(j)
        a = A[max(0, dy):A.shape[0] + min(0, dy), max(0, dx):A.shape[1] + min(0, dx)]
        b = B[max(0, -dy):B.shape[0] + min(0, -dy), max(0, -dx):B.shape[1] + min(0, -dx)]
        if a.size == 0:
            return 1.0, 99.0
        bd = self._blk(np.abs(a - b)).mean(axis=(1, 3))
        ta = self._blk(a).std(axis=(1, 3))
        tb = self._blk(b).std(axis=(1, 3))
        return (float(bd.max() / 255),
                float(max((bd / (ta + 2.0)).max(), (bd / (tb + 2.0)).max())))


# How alike two frames must be, measured on the residual left after one is
# warped onto the other and compared at REVIEW_SIZE. One rule for every lens:
# the focal-length bands that once stood in for this were compensation for
# deciding on a thumbnail, and died with the move to warped 1600px measurement.
#
# One limit, for every photograph. Two limits split by whether anything alive
# was in frame once sat here. They are gone because
# the person choosing what to drag in decides the standard better than a
# detector can — a folder of one kind needs one number, and the dial moves it.
DUP_BLOCK, DUP_RATIO = 30.0, 20.5

# The thumbnail may only ever say "definitely not". Pairs further apart than
# this on the cheap 256x144 comparison are rejected without the expensive test;
# it is deliberately generous, because its only job is to save work.
REJECT_BLOCK, REJECT_RATIO = 45.0, 40.0

# The resolution every real decision is made at. Tested downward on
# 89 labelled pairs: 1400 changes 4 verdicts, 1200 changes 7, 1000 changes 4 —
# for 16-31% off a stage that is 18% of a cold run, so about 3-6% overall. A
# verdict change is a possible false cull, which is not for sale at that price.
REVIEW_SIZE = 1600



# How strongly two frequency signatures must agree before a pair is worth
# comparing properly. Agreement runs from -1 to 1.
#
# Fitted, not chosen. A generous setting nominated 23 candidates per photograph
# on a dense folder and comparing them took 88% of the run; tightening returns
# 40% of the time and costs three culls in 327 on that folder, none at all on a
# sparse one. Tightening further keeps paying but at twice the cost in culls,
# so this sits at the knee.
#
# SIG_CAP is a backstop against a folder copied into itself, where every frame
# would otherwise nominate every other.
SIG_NEAR, SIG_CAP = 0.30, 60


def _dct_basis(n, _cache={}):
    """The DCT-II matrix, built once per size."""
    if n not in _cache:
        k = np.arange(n)[:, None]
        x = np.arange(n)[None, :]
        m = np.cos(np.pi * (2 * x + 1) * k / (2 * n)) * np.sqrt(2.0 / n)
        m[0] /= np.sqrt(2.0)
        _cache[n] = m.astype(np.float32)
    return _cache[n]


def signatures(T, side=32, keep=8):
    """A frequency signature per frame, for deciding what is worth comparing.

    Each sketch is sampled to a square, transformed, and its lowest
    frequencies kept and thresholded at their own median. The result is a
    string of +1 and -1 — how the picture is built rather than how bright it
    is — scaled so that a dot product between two of them is their agreement,
    from -1 to 1.

    Averaging brightness over a grid, which this replaces, compares tone
    directly. Tone is the first thing an export changes: three copies were
    found sitting further from their own originals than the threshold allowed,
    on nothing but a shift in brightness. Dropping the first coefficient drops
    the brightness with it, and the rest describe structure.

    Measured against the brightness grid it replaces, each pass in its own
    process so no cache carries over: the same culls on every folder tried,
    20% less time on a dense one, 2-4% on sparser ones. Never slower.
    Normalising the grid instead fixes the tone problem too and returns almost
    none of the time.
    """
    n = T.shape[0]
    C = _dct_basis(side)
    ys = np.linspace(0, T.shape[1] - 1, side).astype(int)
    xs = np.linspace(0, T.shape[2] - 1, side).astype(int)
    small = T[:, ys][:, :, xs].astype(np.float32)
    d = np.einsum("ij,njk,lk->nil", C, small, C, optimize=True)
    low = d[:, :keep, :keep].reshape(n, -1)[:, 1:]      # without the first: brightness
    bits = np.where(low > np.median(low, axis=1, keepdims=True), 1.0, -1.0)
    return (bits / np.sqrt(bits.shape[1])).astype(np.float32)


def neighbours(T, cap, chunk=512):
    """Every other frame whose picture is built like this one, up to `cap`.

    Two frames of the same thing are candidates whether taken a second or a
    decade apart, so a copy that turns up years later is found on its content
    and not on its clock.

    Comparing every frame with every other is too much on a big folder — 28,000
    files is 398 million pairs — so candidates are judged on the frequency
    signature above, which is one matrix multiply.

    Agreement decides, not rank. Keeping a fixed number per frame was wrong in
    both directions: a folder of unrelated photographs still nominated its
    quota apiece and paid for every one downstream, while a session of 200
    near-identical frames was truncated. A frame like nothing else now
    nominates nothing.
    """
    n = T.shape[0]
    sig = signatures(T)
    cap = min(cap, n - 1)
    out = []
    for s in range(0, n, chunk):
        e = min(s + chunk, n)
        agree = sig[s:e] @ sig.T
        for row, i in enumerate(range(s, e)):
            j = np.flatnonzero(agree[row] >= SIG_NEAR)
            j = j[j != i]
            if j.size > cap:                    # the closest, when there are many
                j = j[np.argsort(-agree[row][j])[:cap]]
            out.append(j.astype(np.int32))
    return out


def same_picture(pa, pb):
    """Proof, not judgement: decode both files fully and compare every pixel.

    Expensive, so callers gate it behind cheap evidence (equal thumbnails,
    equal dimensions). Equality here is certainty — a pair that passes cannot
    be a false positive, whatever the subject.
    """
    try:
        a = np.asarray(open_image(pa).convert("RGB"))
        b = np.asarray(open_image(pb).convert("RGB"))
        return a.shape == b.shape and bool(np.array_equal(a, b))
    except Exception:
        return False


# How much of a pair may still differ while one is called a copy of the other.
# Two ways to satisfy it, because there are two kinds of copy.
#
# A crop or a turn re-samples the same pixels, so what survives alignment is
# encoding noise: measured across 139 culls whose lineage rests on file
# properties — resized copies, re-saves, exports of a raw — every one sits at
# or under 9.8, median 2.2.
#
# An edit that moves the tone shifts every pixel, so its plain residual is
# large however faithful the copy. What stays small is the residual relative to
# local texture: a labelled rotated-and-brightened copy scores 31.1 on the
# first measure and 2.59 on this one, while a pair of faces a second apart
# scores 31.1 and 22.73. The tone moves the whole frame evenly; a person moves
# against their surroundings.
#
# Against a real library the pair of tests admits 1 of the 50 pairs that
# geometry alone had claimed, and every one of the 139 real derivatives.
DERIVED_MAX, DERIVED_RATIO = 10.0, 5.0


def has_motion(path, _seen={}):
    """Does a Live Photo's video sit beside this frame?

    Asked once per file and remembered: a group asks about the same frames
    repeatedly, and this is the only rung of the ranking that touches the disk.
    """
    if path not in _seen:
        stem = os.path.splitext(path)[0]
        _seen[path] = any(os.path.exists(stem + e)
                          for e in (".mov", ".MOV", ".mp4", ".MP4"))
    return _seen[path]


# Where a cull is checked once more before it is believed. Fine detail is the
# whole content of some photographs — a page of print, a page of music — and at
# the resolution every other decision is made at, the characters are a few
# pixels tall and average away. Two different pages then align beautifully,
# because their margins and blocks do.
#
# Measured on the one pair a person refused twice out of 384 judged: it groups
# at 1600 and at 2400, and reads as a different scene at 3200 and above, where
# the keypoints land on the glyphs. Against 60 culls that same person accepted,
# every one survives. Only a positive "different" overturns anything — where
# the closer look cannot tell, it says nothing and the first answer stands,
# because less evidence is not contrary evidence.
CONFIRM_SIZE = 3200


def derivative_kind(v, dt):
    """Crop, rotation or tonal edit of the same capture — provable lineage.

    Where lineage is provable it is MEMBERSHIP, not just a label: the edit
    itself can push the residual past any limit, and an edit of the original is
    exactly what the keep-originals rule says must go.

    That bypass is only honest if the lineage is real, so each kind must show
    the two pictures agree as well as that their geometry lines up. Framing
    alone proves nothing: a burst shot while zooming nests one frame inside the
    other exactly as a crop does, and a subject who moved between the frames
    then leaves by a rule no dial can reach.

    Same-instant only, too: seconds apart, a crop signature is as often an
    optical zoom (measured 50/50).
    """
    if v is None or dt is None or dt >= 2.0 or v.get("scene") != "same":
        return None
    block, rel = v.get("block"), v.get("ratio")
    agrees = ((block is not None and block * 100 <= DERIVED_MAX)
              or (rel is not None and rel <= DERIVED_RATIO))
    z = v.get("zoom") or 1.0
    if agrees and ((v.get("b_in_a") == 1.0 and z <= 0.91) or
                   (v.get("a_in_b") == 1.0 and z >= 1.10)):
        return "cropped copy"
    if agrees and v.get("rot") is not None and abs(abs(v["rot"]) - 90) < 3:
        return "rotated copy"
    # A true edit inherits its source's capture instant exactly, so this asks
    # for the identical timestamp as well as unmoved geometry. That is not
    # sufficient on its own: many cameras record only whole seconds, so frames
    # of a burst share an instant to the millisecond too, and "same geometry,
    # different light" then describes a changing face as readily as a
    # brightness edit. The pictures still have to agree.
    if (agrees and dt <= 0.01
            and v.get("shift", 1.0) < 0.02 and abs(z - 1.0) < 0.03
            and abs(v.get("rot") or 0.0) < 1.0
            and (abs(v.get("lum_off") or 0.0) > 6
                 or abs((v.get("contrast") or 1.0) - 1.0) > 0.08)):
        return "tonal edit"
    return None


def structure_agrees(a, b, floor=0.97):
    """Do these two hold the same picture, tone set aside?

    Brightness is the first thing an export changes and the last thing that
    matters: resizing, re-encoding and tone-mapping all move it, while the
    picture stays put. Removing each sketch's mean and scale before comparing
    answers "the same picture?" without also asking "the same tone?", which is
    the wrong question to ask of a copy.

    Free at this point — both sketches are already in hand — and it is what
    separates a real derivative from two photographs that merely differ in
    resolution or compression. Audited across four folders, every cull that
    skipped review on a bare file property and should not have was a pair this
    test rejects.
    """
    ta = np.asarray(a['thumb'], dtype=np.float32)
    tb = np.asarray(b['thumb'], dtype=np.float32)
    if ta.shape != tb.shape:
        return False
    va, vb = ta.ravel() - ta.mean(), tb.ravel() - tb.mean()
    na, nb = float(np.sqrt(va @ va)), float(np.sqrt(vb @ vb))
    if na < 1e-3 or nb < 1e-3:                 # a blank frame agrees with anything
        return False
    return float(va @ vb) / (na * nb) >= floor


def classify(keeper, other, v=None, dt=None):
    """Why is `other` redundant given `keeper`?

    There is really one reason, and these are its labels: the file is not the
    original and the original is here. What differs is how the copy was made —
    cropped, turned, re-toned, resized, re-encoded — and that is a note for the
    record rather than a separate decision.

    A reason may claim that relationship only if it proves it. `v` is the
    alignment verdict the membership decision was made on and `dt` the
    capture-time gap; between them they establish a crop, a quarter turn, or a
    frame whose geometry is untouched and whose tone moved. Where a reason
    rests on a file property instead, it must show the two pictures agree.

    Evidence is geometric and photometric, never filenames. The time gap is
    used only to insist a crop or a turn belongs to one capture: a crop
    signature seconds apart is as often an optical zoom, measured at 50/50 on
    the labels.
    """
    if other['md5'] == keeper['md5']:
        return "exact copy"
    if (not keeper['raw'] and not other['raw']
            and keeper['w'] == other['w'] and keeper['h'] == other['h']
            and np.array_equal(keeper['thumb'], other['thumb'])
            and same_picture(keeper['path'], other['path'])):
        return "identical picture"           # same pixels, different file bytes
    kp = keeper['w'] * keeper['h']; op = other['w'] * other['h']
    # Everything below asserts one thing: `other` was made from `keeper`, and
    # `keeper` is still here. The names say how, which is for the record; the
    # decision is the same in every case; the names differ only in what
    # evidence backs them.
    #
    # Three prove derivation on their own — a containment warp, a quarter turn,
    # an identical frame with the tone moved. Three do not: being a raw beside
    # a JPEG, holding fewer pixels, or carrying a coarser quantization table
    # are facts about two files, not about a relationship between them. Those
    # must show the pictures agree before they may claim lineage; without that
    # they fall through to a plain near-duplicate.
    if keeper['raw'] and not other['raw'] and structure_agrees(keeper, other):
        return "export of raw"
    kind = derivative_kind(v, dt)
    if kind:
        return kind
    if op and kp and op < kp * 0.9 and structure_agrees(keeper, other):
        return "smaller copy"
    if (other['tier'] > keeper['tier'] + 1
            and structure_agrees(keeper, other)):
        return "resave"
    return "near-duplicate"


# The keeper order, one rung per line: what is read, and what is wrong with the
# file that loses on it. Both come from here so they cannot disagree. They did
# disagree — rungs were added over time and the phrases were not, so every
# reason the tool printed named the rung above the one that actually decided,
# and a compression difference was reported as "less sharp". A rung added
# without its phrase is now a syntax error rather than a silent mislabel.
LADDER = (
    ("motion",   "no Live Photo video"),
    ("raw",      "not the raw"),
    ("pixels",   "fewer pixels"),
    ("unedited", "something wrote it after the camera did"),
    ("camera",   "the camera's own marks are gone"),
    ("finer",    "more compressed"),
    ("metadata", "less metadata"),
    ("tier",     "much more compressed"),
    ("sharp",    "less sharp"),
    ("bytes",    "smaller file"),
    ("path",     None),          # the coin toss; never a reason
)


def why_inferior(keeper_rank, loser_rank):
    """What is wrong with the file being culled, in one phrase.

    A percentage of an allowance nobody set says nothing. This names the first
    rung the two files differ on, from the loser's side, reading the same tuple
    the keeper rule ranked on.
    """
    assert len(keeper_rank) == len(LADDER), "a rung was added without its phrase"
    for (name, phrase), k, l in zip(LADDER, keeper_rank, loser_rank):
        if k != l:
            return phrase or "the same by every measure"
    return "the same by every measure"


def main(argv=None):
    ap = argparse.ArgumentParser(description="Sift one mixed folder for redundant images.")
    ap.add_argument("folder")
    ap.add_argument("--exclude", action="append", default=[],
                    help="skip this folder if it appears inside the scan (repeatable)")
    ap.add_argument("--fixed", action="store_true", help="use one setting for the whole folder")
    ap.add_argument("--block", type=float, default=15.0)
    ap.add_argument("--ratio", type=float, default=5.0)
    ap.add_argument("--window", type=int, default=SIG_CAP,
                    help="most look-alike candidates any one frame may have")
    ap.add_argument("--files", default=None, metavar="LIST",
                    help="judge only the files named in LIST (one path per "
                         "line); the folder argument is their common parent")
    ap.add_argument("--audit", default=None, metavar="PAIRS",
                    help="record the fate of these labelled pairs (CSV with "
                         "file_a/file_b) tier by tier, to PAIRS + ' fates.csv'. "
                         "the honest price of each gate is what it does to "
                         "pairs the run actually nominates")
    ap.add_argument("--recursive", action="store_true")
    ap.add_argument("--workers", type=int, default=0,
                    help="threads for the comparison stage (default: cores, max 8)")
    ap.add_argument("--no-threads", action="store_true",
                    help="compare on one thread; slower, useful when debugging")
    ap.add_argument("--csv", default=None,
                    help="manifest path (default: SiftResults.csv in the current "
                         "directory — never inside the folder being scanned)")
    ap.add_argument("--no-summary", action="store_true",
                    help="skip the closing tally: the caller is about to print "
                         "something better")
    ap.add_argument("--quiet", action="store_true",
                    help="one summary line instead of the full diagnostics")
    a = ap.parse_args(argv)

    def info(*args_, **kw):
        if not a.quiet:
            print(*args_, **kw)

    folder = a.folder.rstrip('/')
    # Say something before the long quiet stretches — walking a big tree,
    # booting the workers, decoding the first raws — or a person cannot tell
    # working from hung. Learned on a large run that sat silent.
    if sys.stderr.isatty():
        sys.stderr.write("  finding photos ...\r")
        sys.stderr.flush()
    if a.files:
        # A dropped selection rather than a folder: judge exactly these files.
        with open(a.files) as fh:
            listed = [ln.rstrip("\n") for ln in fh if ln.strip()]
        paths = sorted(p for p in listed
                       if os.path.splitext(p)[1].lower() in IMG_EXT
                       and os.path.isfile(p))
        if len(paths) < len(listed):
            n_skip = len(listed) - len(paths)
            print(f"  ({n_skip} dropped item{'' if n_skip == 1 else 's'} "
                  f"{'was' if n_skip == 1 else 'were'} not a photo; skipped)")
    else:
        paths = scan(folder, a.recursive, a.exclude)
    if not paths:
        sys.exit("no images found in " + folder)
    if sys.stderr.isatty():
        sys.stderr.write(f"  {len(paths):,} photos                    \n")
        sys.stderr.flush()
    progress(0, len(paths), "reading photos")

    db = _cache_open()
    fps = []
    with Pool(os.cpu_count() or 4) as p:
        for nn, h in enumerate(p.imap(_fp, paths, chunksize=16), 1):
            fps.append(h)
            progress(nn, len(paths), "checking files")
    cached = {}
    if db is not None:
        want = [h for h in fps if h]
        try:
            for s in range(0, len(want), 500):
                qs = want[s:s + 500]
                for h, blob in db.execute(
                        "SELECT md5, blob FROM probe WHERE v = ? AND md5 IN (%s)"
                        % ",".join("?" * len(qs)), [PROBE_VERSION] + qs):
                    cached[h] = blob
        except Exception:
            cached.clear()               # unreadable cache means re-read, not stop
    recs, todo = [None] * len(paths), []
    for i, (path, h) in enumerate(zip(paths, fps)):
        r = _unpack(cached[h]) if h in cached else None
        if r is None:
            todo.append((i, path, h))
        else:
            recs[i] = r
    if todo:
        with Pool(os.cpu_count() or 4) as p:
            for nn, r in enumerate(p.imap(_probe_pair,
                                          [(pt, h) for _, pt, h in todo],
                                          chunksize=4), 1):
                recs[todo[nn - 1][0]] = r
                progress(nn, len(todo), "reading photos")
        if db is not None:
            rows = [(recs[i]['md5'], PROBE_VERSION, _pack(recs[i]))
                    for i, _, _ in todo if 'error' not in recs[i]]
            try:
                db.executemany("INSERT OR REPLACE INTO probe VALUES (?,?,?)", rows)
                db.commit()
            except Exception as e:
                # The cache is an optimisation. Losing it costs a re-read next
                # time; letting it end the run costs the whole folder.
                info(f"  note: could not save to the cache ({str(e)[:40]})")
    if len(paths) > len(todo):
        info(f"  {len(paths) - len(todo):,} already known")
    # the per-file facts the cache must never carry
    for path, h, r in zip(paths, fps, recs):
        if r is None or 'error' in r:
            continue
        r['path'] = path
        r['md5'] = h or r['md5']
        r['bytes'] = os.path.getsize(path)
        r['t'] = r['exif_t'] if r.get('exif_t') else time_fallback(path)
    bad = [r for r in recs if r is not None and 'error' in r]
    recs = [r for r in recs if r is not None and 'error' not in r]
    # Every scanned file must end as a record or a reported error — the
    # accounting principle: you should not need to record failures, only to
    # notice that the books do not balance.
    if len(recs) + len(bad) != len(paths):
        print(f"  \u26a0 {len(paths) - len(recs) - len(bad)} files vanished "
              f"between scanning and reading \u2014 please report this")
    for b in bad[:5]:
        print("  unreadable:", os.path.basename(b['path']), b['error'])
    if bad:
        print(f"  ({len(bad)} unreadable, skipped)")

    fmt = defaultdict(int)
    for r in recs:
        fmt[os.path.splitext(r['path'])[1].lower()] += 1
    n_heic = sum(v for k, v in fmt.items() if k in ('.heic', '.heif'))
    if n_heic and not HAVE_HEIF:
        print(f"  note: {n_heic} HEIC files will read as errors — pip3 install pillow-heif")

    # uint8, not float32. `Comparer` casts one frame at a time and `neighbours`
    # averages with an explicit float32 dtype, so nothing needs the whole stack
    # widened — and widening it costs 4x. At 91,000 files that is 13.5 GB before
    # anything else loads, which is the difference between a library-wide run
    # finishing and dying.
    T = np.stack([r['thumb'] for r in recs])
    cmp = Comparer(T)
    use_verify = HAVE_VERIFY
    if not HAVE_VERIFY:
        print("  alignment unavailable — pip3 install opencv-python-headless")
    stats_v = defaultdict(int)
    # The live thresholds. Held in a dict so `regroup` can change them without
    # rebuilding anything above.
    cur = dict(block=(a.block if a.fixed else DUP_BLOCK),
               ratio=(a.ratio if a.fixed else DUP_RATIO))

    # Both in-memory caches are shared across the comparison thread pool, so
    # every read, insert and eviction happens under a lock. Unlocked, two
    # threads evicting at once corrupt the dict mid-iteration; the resulting
    # exceptions were caught downstream as "cannot align, keep both" and cost
    # a full Nature run half its culls before the verdict cache made the
    # damage visible. Decodes stay outside the lock — only bookkeeping is in.
    import threading as _ct
    _gcache, _glock = {}, _ct.Lock()

    def _gray(path, size):
        # Keyed by size as well as path: a cache that ignored the size would
        # hand back an 800px array to a caller that asked for 1600.
        key = (path, size)
        with _glock:
            if key in _gcache:
                return _gcache[key]
        im = open_image(path)
        try:
            # A square request, deliberately. It stops the decoder halving a
            # landscape frame — the short side falls under the box — so the
            # full image comes back and is shrunk here instead, 2.2x more
            # pixels than the reading pass uses. That looks like waste and is
            # not: shrinking to 1600 from the full frame antialiases better
            # than shrinking from a half-size decode, and the sharper result
            # finds 2 more culls in 80 labelled pairs for 6% more time
            # (measured). Decoding small here is the false economy.
            im.draft('L', (size, size))
        except Exception:
            pass
        im = im.convert('L')
        im.thumbnail((size, size))
        arr = np.asarray(im)
        with _glock:
            _gcache[key] = arr
            while len(_gcache) > 120:
                _gcache.pop(next(iter(_gcache)))
        return arr

    _fcache, _flock = {}, _ct.Lock()

    def _feats(path, size):
        """ORB keypoints per frame, not per pair.

        Each frame appears in up to `--window` candidate pairs, and the
        detector was being run again for every one of them — verify.compare has
        always accepted precomputed features and nothing ever passed them.
        """
        key = (path, size)
        with _flock:
            if key in _fcache:
                return _fcache[key]
        try:
            val = _verify.features(_gray(path, size))
        except Exception:
            val = (None, None)
        with _flock:
            _fcache[key] = val
            while len(_fcache) > 400:
                _fcache.pop(next(iter(_fcache)))
        return val

    # Every pair that earns a full look, with the number it was judged on.
    # Recording costs nothing — the measurement is already made — and it is the
    # only way to find out where the tool's decisions actually sit relative to
    # the limit, rather than reasoning from a handful of remembered cases.
    scored = []
    _vcache = {}

    # Audit: which tier decides the fate of each watched (labelled) pair.
    # A set lookup per comparison when active, nothing at all when not.
    _audit_pairs, _audit_log = None, []
    if a.audit:
        _audit_pairs = set()
        with open(a.audit) as fh:
            for row in csv.DictReader(fh):
                pa_, pb_ = row.get("file_a"), row.get("file_b")
                if pa_ and pb_ and pa_ != pb_:
                    _audit_pairs.add(frozenset((os.path.abspath(pa_),
                                                os.path.abspath(pb_))))
        print(f"  auditing the fate of {len(_audit_pairs)} labelled pairs")

    def _audit_note(keeper, other, stage, detail):
        if _audit_pairs is None:
            return
        k = frozenset((recs[keeper]['path'], recs[other]['path']))
        if k in _audit_pairs:
            _audit_log.append((recs[keeper]['path'], recs[other]['path'],
                               stage, detail))

    import threading as _threading
    _md5_of = {r['path']: r['md5'] for r in recs}
    _vlock = _threading.Lock()
    _vwrites = [0]
    _scache = {}
    _pending = {"verdict": [], "screen": []}

    def _preload(table, version, into, decode):
        """Pull this folder's cached answers into memory in one query.

        Asking the database per pair meant every worker thread queueing on one
        lock: on a 2,600-photo folder that was 558 of 563 seconds spent waiting
        rather than measuring, even with every answer already cached.
        """
        if db is None:
            return
        hs = sorted({h for h in _md5_of.values() if h})
        got = 0
        try:
            for k in range(0, len(hs), 400):
                chunk = hs[k:k + 400]
                for a_, b_, js in db.execute(
                        "SELECT a, b, js FROM %s WHERE v = ? AND a IN (%s)"
                        % (table, ",".join("?" * len(chunk))),
                        [version] + chunk):
                    into[decode(a_, b_)] = json.loads(js)
                    got += 1
        except Exception:
            pass
        return got

    def _flush(force=False):
        """Write remembered answers in batches, not one lock at a time."""
        if db is None:
            return
        for table, rows in _pending.items():
            if not rows or (not force and len(rows) < 2000):
                continue
            try:
                with _vlock:
                    db.executemany(
                        "INSERT OR REPLACE INTO %s VALUES (?,?,?,?)" % table, rows)
                    db.commit()
            except Exception:
                pass
            rows.clear()

    def _screen(i, j):
        """The keypoint screen, remembered for the session.

        Its answer is a property of the two photographs, not of the limit, so
        a second round at a new setting must not pay for it again — that cost
        was the whole wait between rounds (35s on a 200-file folder, of which
        0.05s was real work).
        """
        a_, b_ = recs[i], recs[j]
        if a_.get('sdes') is None or b_.get('sdes') is None:
            return None
        key = (_md5_of.get(a_['path']), _md5_of.get(b_['path']))
        hit = _scache.get(key)
        if hit is not None:
            return hit
        hit = _verify.screen(a_['spts'], a_['sdes'], b_['spts'], b_['sdes'],
                             a_.get('sshape') or (700, 700))
        _scache[key] = hit
        if key[0] and key[1]:
            _pending["screen"].append((key[0], key[1], SCREEN_VERSION,
                                       json.dumps(hit, default=float)))
        return hit

    def _confirm(pa, pb, size):
        """Align two frames and measure what is left. The decision itself.

        Cached twice over: in memory, because grouping and the proof-image
        stage ask about the same pairs; and on disk keyed by the two files'
        content fingerprints, because a verdict is a pure function of their
        bytes — a repeat run answers from the cache instead of decoding,
        aligning and warping both ways again.
        """
        ka, kb = _md5_of.get(pa), _md5_of.get(pb)
        key = (ka, kb, size) if ka and kb else (pa, pb, size)
        if key in _vcache:
            return _vcache[key]
        try:
            v = _verify.compare(_gray(pa, size), _gray(pb, size),
                                *_feats(pa, size), *_feats(pb, size))
        except Exception:
            # A crash is not a verdict. It is returned as keep-both for this
            # one ask, never memorised anywhere — and counted, so a run that
            # crashed its way to a low cull count says so out loud instead of
            # letting the number pass for truth.
            stats_v["comparison crashed"] += 1
            return dict(scene="unknown", inliers=0, keypoints=0,
                        block=None, ratio=None)
        with _vlock:
            _vcache[key] = v
            while len(_vcache) > 40000:
                _vcache.pop(next(iter(_vcache)))
        if ka and kb:
            _pending["verdict"].append((ka, kb, VERDICT_VERSION,
                                        json.dumps(v, default=float)))
        return v

    # One query each, before any pair is asked about.
    _preload("verdict", VERDICT_VERSION, _vcache,
             lambda a_, b_: (a_, b_, REVIEW_SIZE))
    _preload("screen", SCREEN_VERSION, _scache, lambda a_, b_: (a_, b_))
    for _v in _vcache.values():
        if _v.get("where") is not None:
            _v["where"] = tuple(_v["where"])

    n = len(recs)

    def rank(i):
        r = recs[i]
        # A frame carrying a Live Photo's video outranks everything else a
        # ladder can measure. Its video travels with it when it is culled, so
        # losing that frame loses motion the survivor does not hold and no
        # amount of resolution or sharpness replaces. It sits above the raw
        # rung because a raw is still a single instant.
        motion = 1 if has_motion(r['path']) else 0
        fmt_score = 1 if r['raw'] else 0        # the original always wins
        px = r['w'] * r['h']
        if r['raw'] and px == 0:
            px = 10 ** 9                      # unknown sensor size still beats any export
        # The two rungs that are evidence rather than inference. Every other
        # rung is a property of one file — how big, how sharp, how finely
        # quantized — and says nothing about which of two files came first.
        # These say something happened to a file after the shutter: an editor
        # named itself, or the clock moved off the moment of capture, or the
        # camera's private block is missing. All three are read from EXIF that
        # is already open.
        #
        # Below resolution, so a small edit can never beat a full-size
        # original. Above the compression rungs, because a re-save at higher
        # quality beats its own source there — it spends more bytes on pixels
        # it has already degraded. That is not hypothetical: on real culls the
        # tool kept a Windows Photo Viewer re-save over its iPhone original,
        # and kept a file whose clock had moved forty days over the one still
        # carrying the camera's block.
        untouched = 0 if (r.get('edited') or r.get('moved')) else 1
        camera = 1 if r.get('maker') else 0
        # How coarsely this was quantized, unbucketed. The tier rounds onto a
        # log scale, which is right for "much more compressed" and wrong here:
        # two generations of one picture often land in the same bucket. Read
        # straight it names the earlier generation in 91% of pairs where the
        # EXIF says which is the edit, and 96% once resolution has spoken first.
        finer = -r.get('qmean', 0.0)
        # The path is the last resort, and it is there so the order is
        # *total*. Two files can tie on every real criterion — copies do, by
        # definition — and without a final tiebreak the leader of their group
        # was decided by whichever the scan happened to list first, which made
        # the plan depend on directory order rather than on the photographs.
        return (motion, fmt_score, px, untouched, camera, finer,
                r.get('meta', 0), -r['tier'], r['sharp'], r['bytes'], r['path'])

    def matches(keeper, other):
        """Is `other` redundant against `keeper`? The only membership test.

        Two stages, and only the second one may say yes. The thumbnail is a
        cheap filter that can reject and nothing more; the decision is the
        residual left after warping one frame onto the other and comparing at
        REVIEW_SIZE, which is where a changed expression or a turned head is
        still visible.
        """
        stats_v["comparisons attempted"] += 1
        b, r = cmp.compare(keeper, other)
        if b > REJECT_BLOCK / 100 or r > REJECT_RATIO:
            # Simultaneous captures get a second opinion: a copy that was
            # rotated or heavily cropped fails the rigid thumbnail overlay,
            # but the keypoint screen sees through both. The window matches
            # the derivative rule's own gate, so anything that could classify
            # as a copy can also be found; bursts still pay almost nothing.
            sc = (_screen(keeper, other)
                  if abs(recs[keeper]['t'] - recs[other]['t']) <= 2.0 else None)
            if not (sc and sc["scene"] == "same"):
                stats_v["rejected on the sketch"] += 1
                _audit_note(keeper, other, "sketch", f"{b*100:.0f}/{r:.0f}")
                return False              # nowhere near; no need to look closer

        # The geometric screen: keypoints only, no pixels, no decode. Most
        # candidate pairs in a burst are different frames of a moving scene,
        # and this says so for the cost of a descriptor match.
        sc = _screen(keeper, other)
        if sc is not None:
            if sc["scene"] == "different":
                stats_v["screened out on keypoints"] += 1
                _audit_note(keeper, other, "screen",
                            f"inliers={sc['inliers']}/{sc['keypoints']}")
                return False

        # A 600px glance between the screen and the full
        # look was measured on a folder of bursts: it dismissed 2 pairs out
        # of 469 while costing a decode on every pair that reached it — the
        # keypoint screen had taken over its job. Removed rather than tuned.

        v = _confirm(recs[keeper]['path'], recs[other]['path'], REVIEW_SIZE)
        stats_v[v["scene"]] += 1
        if v["scene"] == "different":
            _audit_note(keeper, other, "inlier floor",
                        f"inliers={v['inliers']} kp={v['keypoints']}")
            return False              # same layout, different subject
        # A recomposed shot — large shift or rezoom — is not rejected here
        # too. It now falls through: the residual is measured inside the
        # overlap, so frame movement does not stand in for the picture
        # changing. Shift and zoom are still recorded in the plan.
        if v["scene"] == "unknown":
            # Too dark or too smooth for geometry — a bird against blank sky,
            # a museum wall. No warp, so no honest high-resolution residual,
            # and the sketch is all there is. It does not get to say yes on its
            # own: darkness compresses exactly the differences that matter.
            stats_v["unverifiable, kept apart"] += 1
            _audit_note(keeper, other, "keypoint floor", f"kp={v['keypoints']}")
            return False
        if v["block"] is None:
            return False
        ok = (v["block"] <= cur['block'] / 100 and v["ratio"] <= cur['ratio'])
        if not ok and derivative_kind(
                v, abs(recs[keeper]['t'] - recs[other]['t'])):
            ok = True    # provable lineage is membership: the edit goes
        if ok and use_verify:
            # One more look, at a resolution that keeps the fine detail. Only
            # a positive "different" overturns: where the closer look cannot
            # tell, it says nothing, because less evidence is not contrary
            # evidence. Paid only by pairs already judged duplicates.
            closer = _confirm(recs[keeper]['path'], recs[other]['path'],
                              CONFIRM_SIZE)
            if closer["scene"] == "different":
                ok = False
                stats_v["refused by the closer look"] += 1
                _audit_note(keeper, other, "closer look",
                            f"different at {CONFIRM_SIZE}")
        if len(_pending["verdict"]) + len(_pending["screen"]) >= 2000:
            _flush()                       # bound what a killed run would lose
        _audit_note(keeper, other, "residual",
                    f"{v['block']*100:.1f}/{v['ratio']:.1f} -> "
                    + ("cull" if ok else "keep"))
        scored.append((recs[keeper]['path'], recs[other]['path'],
                       round(v["block"] * 100, 2), round(v["ratio"], 2), ok,
                       v.get("where"), v.get("dx") or 0.0, v.get("dy") or 0.0))
        return ok

    _pool = None
    if use_verify and not a.no_threads:
        try:
            from concurrent.futures import ThreadPoolExecutor
            _pool = ThreadPoolExecutor(max_workers=a.workers or min(8, (os.cpu_count() or 4)))
        except Exception:
            _pool = None

    # Identical bytes first: those need no picture test at all.
    same_bytes = defaultdict(list)
    for i, r in enumerate(recs):
        same_bytes[r['md5']].append(i)

    cand = neighbours(T, a.window)

    # Discovery is complete for bursts, however large the run — the
    # guarantee, and a measured win: the clean A/B on the burst-heaviest
    # folder culls 1,070 with this against 1,045 without, in fewer groups —
    # giant bursts stop fragmenting into several keepers once every mate is
    # a candidate. It also means a looser dial or a smarter sketch can never
    # be starved of pairs, and a burst is treated identically in a 900-file
    # run and a very large one.
    #
    # Two nets. A *burst* chains frames arriving faster than one every
    # BURST_GAP seconds; every pair inside a burst is a candidate, all of
    # them. The minute window catches slower sequences around it. The caps
    # guard one degenerate case only: files with no real capture time fall
    # back to file dates, and a folder copied in one moment would otherwise
    # pair quadratically with itself.
    # A minute, and measured: widening it to ten looked attractive because 18
    # of the culls only the look-alike stage could find were 1-8 minutes apart
    # — but those pairs were already being found, so the wider net only made
    # the same culls reachable twice. It cost 72,694 extra candidate pairs and
    # 2.8x the run for one extra cull on that folder. Widen this only if
    # the look-alike stage is ever removed.
    BURST_GAP, BURST_MAX = 3.0, 500
    TIME_NEAR, TIME_CAP = 60.0, 100
    order = sorted(range(n), key=lambda i: recs[i]['t'])
    extra = defaultdict(set)
    burst = [order[0]] if order else []
    def flush(b):
        if 1 < len(b) <= BURST_MAX:
            for x in range(len(b)):
                for y in range(x + 1, len(b)):
                    extra[b[x]].add(b[y])
                    extra[b[y]].add(b[x])
    for prev, i in zip(order, order[1:]):
        if recs[i]['t'] - recs[prev]['t'] <= BURST_GAP:
            burst.append(i)
        else:
            flush(burst)
            burst = [i]
    flush(burst)
    for pos, i in enumerate(order):
        for j in order[pos + 1:pos + 1 + TIME_CAP]:
            if recs[j]['t'] - recs[i]['t'] > TIME_NEAR:
                break
            # both directions: either frame may end up the keeper, and a
            # keeper only ever compares against its own candidate list
            extra[i].add(j)
            extra[j].add(i)
    # Two ways in, counted as pairs a person would recognise: A-with-B once,
    # not once from each side. "Look alike" is the frequency signature;
    # "close in time" is bursts plus the minute window. The overlap says how
    # much either could be trusted on its own.
    def key(i, j):
        return (i * n + j) if i < j else (j * n + i)

    looks = {key(i, int(j)) for i, c in enumerate(cand) for j in c}
    times = {key(i, int(j)) for i, js in extra.items() for j in js}
    for i, js in extra.items():
        cand[i] = np.union1d(cand[i], np.fromiter(js, dtype=cand[i].dtype))
    both = looks & times
    if looks or times:
        info(f"  {len(looks | times):,} pairs to compare \u00b7 "
             f"{len(looks - both):,} look alike, {len(times - both):,} close in "
             f"time, {len(both):,} both")

    # A group is a keeper and the frames that lose to *it*. Taking the best
    # frame first and letting it claim its own losers means every culled file
    # was compared with the file that replaces it — never with some third frame
    # that happened to sit between them. A long burst that drifts therefore
    # breaks into several groups instead of one chain spanning more change than
    # the threshold ever allowed.
    # Everything above this point is the expensive part: decoding, keypoints,
    # the candidate shortlist, and the verdict for every pair that needed one.
    # None of it depends on the thresholds — those only decide how to compare
    # against numbers already worked out. So grouping is a function that can be
    # run again with different limits for nothing, which is what lets the review
    # ask "too picky or not picky enough?" and answer in under a second.
    def regroup(block=None, ratio=None):
        if block is not None:
            cur["block"], cur["ratio"] = block, ratio
        stats_v.clear()
        del scored[:]
        assigned = [False] * n
        groups = []
        for done, i in enumerate(sorted(range(n), key=rank, reverse=True), 1):
            progress(done, n, "comparing photos")
            if assigned[i]:
                continue
            assigned[i] = True
            members = [i]
            for j in same_bytes[recs[i]['md5']]:          # exact copies, always
                if not assigned[j]:
                    assigned[j] = True
                    members.append(j)
            # One keeper's candidates are independent of each other — each asks
            # "does this frame lose to *this* keeper", and nothing in the answer
            # depends on the other candidates. So they are judged in parallel and
            # applied in order afterwards, which keeps grouping exactly sequential
            # while the expensive part uses the whole machine. Threads rather than
            # processes: the work is inside numpy, OpenCV and JPEG decoding, all of
            # which release the GIL, and the frame and verdict caches stay shared
            # instead of being copied into every worker.
            todo = [int(j) for j in cand[i] if not assigned[j]]
            if todo:
                if _pool is None or len(todo) < 4:
                    verdicts = [matches(i, j) for j in todo]
                else:
                    verdicts = list(_pool.map(lambda j: matches(i, j), todo))
                for j, ok in zip(todo, verdicts):
                    if ok and not assigned[j]:
                        assigned[j] = True
                        members.append(j)
            if len(members) > 1:
                groups.append(members)
        dup = sum(len(g) - 1 for g in groups)
        accounted = (stats_v.get("rejected on the sketch", 0)
                     + stats_v.get("screened out on keypoints", 0)
                     + stats_v.get("same", 0) + stats_v.get("different", 0)
                     + stats_v.get("unknown", 0))
        if stats_v.get("comparisons attempted", 0) != accounted:
            print(f"  \u26a0 {stats_v['comparisons attempted']:,} comparisons attempted, "
                  f"{accounted:,} accounted for \u2014 please report this")
        if stats_v.get("comparison crashed"):
            print(f"  \u26a0 {stats_v['comparison crashed']:,} comparisons failed \u2014 "
                  f"count is low; please report this")
        group_line = f"{len(groups):,} groups \u00b7 {dup:,} redundant ({dup / n * 100:.0f}%)"

        def geometry_of(keeper, other):
            """Shift and zoom for the record — how far the camera moved on every
            pair that grouped, kept because the open half of the movement rule (camera movement
            gradually tightening the test) will need the distribution."""
            if not use_verify:
                return "", ""
            v = _confirm(recs[keeper]['path'], recs[other]['path'], REVIEW_SIZE)
            sh, zm = v.get("shift"), v.get("zoom")
            return (("" if sh is None else round(sh, 4)),
                    ("" if zm is None else round(zm, 4)))

        def margin_against(keeper, other):
            """How much of the allowed slack this decision used, 0 to 1.

            1.0 means it only just qualified. Mistakes cluster here, so the review
            should spend its attention on the high numbers rather than sampling
            evenly across pairs that were never in doubt. Measured on the same
            warped residual the decision was made on — ranking the review by a
            number the decision did not use would point it at the wrong pairs.
            """
            th_b, th_r = cur['block'], cur['ratio']   # the live limit
            try:
                b = r = None
                if use_verify:
                    v = _confirm(recs[keeper]['path'], recs[other]['path'], REVIEW_SIZE)
                    if v.get("block") is not None:
                        b, r = v["block"], v["ratio"]
                if b is None:
                    b, r = cmp.compare(keeper, other)
            except Exception:
                return 0.0, None, None

            def used(value, allowed):
                # A limit of zero allows nothing, so any difference at all has
                # overrun it — and dividing by it would crash the outcomes
                # scan, which always probes the bottom of the dial first.
                if allowed:
                    return value / allowed
                return 0.0 if not value else float("inf")

            return max(used(b, th_b / 100), used(r, th_r)), b, r

        rows = []
        cat_count = defaultdict(int)
        freed = 0
        ordered = sorted(groups, key=lambda g: recs[g[0]]['t'])
        # Every cull here is confirmed at full size, which on a loose setting
        # is hundreds of full comparisons. Counted in comparisons rather than
        # groups: one group can hold forty frames, and a bar that moves once
        # per group sits still through all of them — which reads as a hang and
        # gives an estimate that means nothing.
        todo = sum(len(g) - 1 for g in ordered) or 1
        seen = 0
        progress(0, todo, "confirming culls")
        for gi, g in enumerate(ordered):
            best = max(g, key=rank)
            kr = recs[best]
            for i in g:
                r = recs[i]
                dims = f"{r['w']}x{r['h']}" if r['w'] else ("raw sensor" if r['raw'] else "?")
                if i == best:
                    rows.append([os.path.relpath(r['path'], folder), "KEEP", gi, len(g), "",
                                 dims, r['tier'], round(r['sharp'], 1),
                                 f"{r['bytes']/1e6:.1f}", round(r['t'], 3),
                                 "", "", "", "", "", ""])
                else:
                    v = (_confirm(kr['path'], r['path'], REVIEW_SIZE)
                         if use_verify else None)
                    # After the work, never before: reporting a step on the way
                    # in shows the last one finished while it is still running,
                    # and hands the cursor back mid-comparison.
                    seen += 1
                    progress(seen, todo, "confirming culls")
                    why = classify(kr, r, v, abs(kr['t'] - r['t']))
                    cat_count[why] += 1
                    freed += r['bytes']
                    m, b, rr = margin_against(best, i)
                    sh, zm = geometry_of(best, i)
                    kept_because = why_inferior(rank(best), rank(i))
                    rows.append([os.path.relpath(r['path'], folder), "REDUNDANT", gi, len(g), why,
                                 dims, r['tier'], round(r['sharp'], 1),
                                 f"{r['bytes']/1e6:.1f}", round(r['t'], 3),
                                 round(m, 3),
                                 "" if b is None else round(b * 100, 1),
                                 "" if rr is None else round(rr, 2), sh, zm,
                                 kept_because])
        if cat_count:
            info(f"{group_line} \u00b7 {freed/1e9:.2f} GB")
            import shutil, textwrap
            parts = [f"{v:,} {k}" for k, v in
                     sorted(cat_count.items(), key=lambda x: -x[1])]
            room = max(40, shutil.get_terminal_size((100, 24)).columns - 4)
            for line in textwrap.wrap(", ".join(parts), room,
                                      initial_indent="  ",
                                      subsequent_indent="  "):
                info(line)

        out = a.csv or os.path.join(os.getcwd(), "SiftResults.csv")
        with open(out, "w", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["file", "verdict", "group", "group_size", "why", "dimensions",
                        "compression_tier", "sharpness", "MB", "taken",
                        "margin", "block_pct", "ratio", "shift", "zoom",
                        "why_inferior"])
            w.writerows(rows)
        info("manifest:", out)
        if a.quiet and not a.no_summary:
            gb = (f"{freed/1e9:.1f} GB" if freed >= 1e9
                  else f"{freed/1e6:.0f} MB")
            if not dup:
                print(f"  {n:,} photos \u00b7 nothing redundant")
            else:
                # Two short lines beat one that the window folds mid-phrase.
                # The first says what the run would do; the second, in what
                # proportions — and only when there is more than one kind,
                # since on most runs everything is a near-duplicate.
                print(f"  cull {dup:,} of {n:,} \u00b7 "
                      f"{len(groups):,} groups \u00b7 {gb}")
                if len(cat_count) > 1:
                    import shutil
                    import textwrap
                    kinds = ", ".join(f"{v:,} {k}" for k, v in
                                      sorted(cat_count.items(), key=lambda x: -x[1]))
                    room = max(40, shutil.get_terminal_size((100, 24)).columns - 6)
                    for line in textwrap.wrap(kinds, room, initial_indent="    ",
                                              subsequent_indent="    ",
                                              break_long_words=False):
                        print(line)
        return dict(groups=len(groups), redundant=dup, freed=freed,
                    block=cur["block"], ratio=cur["ratio"], manifest=out)

    result = regroup()
    _flush(force=True)
    if _audit_pairs is not None:
        # Pairs the run never weighed directly: both files present but neither
        # in the other's shortlist, or files that were not in the tree at all.
        seen = {frozenset((x[0], x[1])) for x in _audit_log}
        byp = {r['path']: r for r in recs}
        for k in _audit_pairs - seen:
            pa_, pb_ = sorted(k)
            ra, rb = byp.get(pa_), byp.get(pb_)
            if ra is None or rb is None:
                why = "not in this run"
            elif ra['md5'] == rb['md5']:
                why = "grouped as exact copies"
            else:
                why = "never nominated - outside each other's shortlist"
            _audit_log.append((pa_, pb_, "unseen", why))
        # The verdict that matters is the OUTCOME: a watched pair is settled
        # when either of its files was culled, whichever group did it. Scoring
        # only the pair's own comparisons once undercounted real success 2.5x.
        verdict = {}
        for row in csv.DictReader(open(result["manifest"])):
            verdict[os.path.join(folder, row["file"])] = row["verdict"]
        for k in _audit_pairs:
            pa_, pb_ = sorted(k)
            if "REDUNDANT" in (verdict.get(pa_, "KEEP"), verdict.get(pb_, "KEEP")):
                _audit_log.append((pa_, pb_, "outcome", "settled - one side culled"))
            else:
                _audit_log.append((pa_, pb_, "outcome", "unresolved - both kept"))
        fates = (a.audit[:-4] if a.audit.lower().endswith(".csv") else a.audit) \
            + " - fates.csv"
        with open(fates, "w", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["file_a", "file_b", "stage", "detail"])
            w.writerows(sorted(_audit_log))
        info("audit:", fates)
    return dict(regroup=regroup, result=result, files=n, scored=scored)


if __name__ == "__main__":
    main()
