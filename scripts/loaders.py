"""Readers that work across formats: JPEG, PNG, HEIC, TIFF and camera raws.

Raw files are not decoded - every camera raw embeds a full-size JPEG preview,
which is enough to compare content and to measure sharpness. Extracting it is
far faster than demosaicing and needs no extra libraries.
"""
import io, os, re, struct
from datetime import datetime
import numpy as np
from PIL import Image, ImageOps

# iPhones shoot HEIC. Pillow needs a plugin for it; without one the tool would
# see an empty library on most people's photos.
try:
    from pillow_heif import register_heif_opener
    register_heif_opener()
    HAVE_HEIF = True
except ImportError:
    HAVE_HEIF = False

RAW_EXT = {'.arw', '.cr2', '.cr3', '.crw', '.nef', '.nrw', '.dng', '.raf', '.orf',
           '.rw2', '.pef', '.srw', '.raw', '.3fr', '.erf', '.mrw', '.x3f'}
IMG_EXT = {'.jpg', '.jpeg', '.png', '.tif', '.tiff', '.heic', '.heif', '.webp', '.bmp'} | RAW_EXT

TS_PAT = re.compile(
    r'(\d{4})[.\-_](\d{2})[.\-_](\d{2})\D+(\d{2})[.\-_](\d{2})[.\-_](\d{2})(?:[.\-_](\d{1,3}))?')


def is_raw(path):
    return os.path.splitext(path)[1].lower() in RAW_EXT


def embedded_jpeg(path, probe_bytes=12 << 20):
    """Pull the preview JPEG out of a raw container.

    Candidate spans are found by scanning for SOI/EOI markers, then verified
    largest-first by asking PIL to parse the header. The verification is not
    optional: raw sensor data contains marker bytes by chance, and on
    60-megapixel uncompressed files a fake span can dwarf the real preview —
    34 healthy Europe raws read as "unreadable" for the life of the tool
    because the largest span was sensor noise.

    Previews live near the start of the file, so a slice is read first and the
    whole file only if nothing usable turns up — raws run to 100 MB or more.
    """
    with open(path, 'rb') as fh:
        data = fh.read(probe_bytes)
    if data.find(b'\xff\xd8\xff') < 0 or data.rfind(b'\xff\xd9') < 0:
        data = open(path, 'rb').read()
    spans = []
    i = 0
    while True:
        i = data.find(b'\xff\xd8\xff', i)
        if i < 0:
            break
        j = data.find(b'\xff\xd9', i)
        if j > 0:
            spans.append((j - i, i, j + 2))
        i += 3
    for _, s, e in sorted(spans, reverse=True)[:8]:
        blob = data[s:e]
        try:
            Image.open(io.BytesIO(blob)).size    # header parse; noise fails here
            return blob
        except Exception:
            continue
    raise ValueError("no embedded preview in " + os.path.basename(path))


def open_image(path):
    """The photograph as it should be seen: EXIF rotation applied.

    Cameras record "this frame was shot on its side" as a tag rather than
    rotating the pixels, and every reader is expected to honour it. Nothing here
    did, so a portrait frame was compared, ranked and — worse — *shown* to a reviewer
    lying on its side or upside down, which is how it turned up in a sampling
    round he was asked to judge.

    It matters for more than looks. Two files of the same picture with different
    orientation tags read as a rotation the homography then has to absorb.

    Only applied when the file actually carries a rotation. `exif_transpose`
    returns a fully-decoded copy even when there is no tag, and that copy
    silently disabled `draft()` lazy decoding for every caller — slower on
    every raw, and it shifted every residual measurement enough to flip a
    verdict on a known pair (its ratio moved 27.5 -> 21.8, under the limit).
    Untagged frames — the common case — were never displayed wrong, so they
    keep the lazy path untouched.
    """
    im = Image.open(io.BytesIO(embedded_jpeg(path))) if is_raw(path) else Image.open(path)
    try:
        if im.getexif().get(274) not in (None, 1):     # 274 = Orientation
            return ImageOps.exif_transpose(im)
    except Exception:
        pass
    return im


def exif_time(im):
    """Capture time from an already-open image's EXIF, or None.

    Only true capture tags. Tag 306 is the file's modify time and on an
    exported file it records the export, not the shot.
    """
    try:
        exif = im.getexif()
        # DateTimeOriginal lives in the EXIF sub-IFD, not the top-level one.
        # Reading only the top level finds it in no file at all — checked
        # against a real library, 0 of 6 there and 6 of 6 in the sub-IFD — so
        # every capture time silently came from the fallback below, which reads
        # the filename. Look in the sub-IFD first, then the top level, which is
        # where a few older writers put it.
        for table in (exif.get_ifd(0x8769), exif):
            for tag in (36867, 36868):         # DateTimeOriginal, DateTimeDigitized
                v = table.get(tag) if table else None
                if v:
                    try:
                        return datetime.strptime(str(v)[:19],
                                                 "%Y:%m:%d %H:%M:%S").timestamp()
                    except ValueError:
                        pass
    except Exception:
        pass
    return None


def time_fallback(path):
    """Capture time without opening the file: filename timestamp, else mtime."""
    m = TS_PAT.search(os.path.basename(path))   # filenames often carry the real capture time
    if m:
        y, mo, d, h, mi, s, ms = m.groups()
        try:
            return datetime(int(y), int(mo), int(d), int(h), int(mi), int(s)).timestamp() \
                   + (int(ms) / 1000 if ms else 0)
        except ValueError:
            pass
    return os.path.getmtime(path)


def capture_time(path):
    """EXIF capture time if present, else a timestamp in the filename, else mtime."""
    try:
        t = exif_time(open_image(path))
    except Exception:
        t = None
    return t if t is not None else time_fallback(path)


def quantization_tier(path):
    """Coarse bucket describing how heavily a JPEG was compressed.

    Lower is better (finer table). Raws and lossless formats get -1, meaning
    'no lossy compression at all', so they outrank every JPEG.
    """
    ext = os.path.splitext(path)[1].lower()
    if ext in RAW_EXT or ext in {'.png', '.tif', '.tiff', '.bmp'}:
        return -1
    try:
        im = Image.open(path)
        qt = getattr(im, "quantization", None)
        if not qt:
            return 0
        import math
        qmean = float(np.mean(list(qt.values())[0]))
        return int(round(math.log(max(qmean, 1.0)) / math.log(1.4)))
    except Exception:
        return 99


def sensor_dims(path):
    """Real sensor dimensions of a raw, read from the TIFF IFD0 tags.

    A raw's embedded preview is usually a fraction of full size, so measuring the
    preview would understate the file badly.
    """
    try:
        with open(path, 'rb') as fh:
            head = fh.read(4)
            if head[:2] not in (b'II', b'MM'):
                return None
            endian = '<' if head[:2] == b'II' else '>'
            fh.seek(4)
            off = struct.unpack(endian + 'I', fh.read(4))[0]
            fh.seek(off)
            count = struct.unpack(endian + 'H', fh.read(2))[0]
            dims = {}
            for _ in range(min(count, 200)):
                entry = fh.read(12)
                if len(entry) < 12:
                    break
                tag, typ, cnt = struct.unpack(endian + 'HHI', entry[:8])
                if tag in (256, 257):
                    if typ == 3:
                        dims[tag] = struct.unpack(endian + 'H', entry[8:10])[0]
                    elif typ == 4:
                        dims[tag] = struct.unpack(endian + 'I', entry[8:12])[0]
            if 256 in dims and 257 in dims:
                return dims[256], dims[257]
    except Exception:
        pass
    return None


def _tiff_tags(path, want, limit=400):
    """Read selected tags from a TIFF-structured file (raws included).

    Walks IFD0, follows the Exif IFD pointer, and returns the tags asked for.
    Written by hand because a raw's embedded preview carries only thin EXIF and
    the real shooting data lives in the container.
    """
    out = {}
    try:
        with open(path, 'rb') as fh:
            data = fh.read(256 * 1024)
        if data[:2] not in (b'II', b'MM'):
            return out
        e = '<' if data[:2] == b'II' else '>'
        def u16(o): return struct.unpack(e + 'H', data[o:o+2])[0]
        def u32(o): return struct.unpack(e + 'I', data[o:o+4])[0]
        def read_ifd(off, depth=0):
            if off <= 0 or off + 2 > len(data) or depth > 2:
                return
            n = u16(off)
            for i in range(min(n, limit)):
                ent = off + 2 + i * 12
                if ent + 12 > len(data):
                    return
                tag, typ, cnt = struct.unpack(e + 'HHI', data[ent:ent+8])
                val_off = ent + 8
                if tag == 0x8769:                      # Exif IFD pointer
                    read_ifd(u32(val_off), depth + 1)
                    continue
                if tag not in want:
                    continue
                if typ == 3:
                    out[tag] = u16(val_off)
                elif typ == 4:
                    out[tag] = u32(val_off)
                elif typ == 5 and cnt == 1:            # rational
                    p = u32(val_off)
                    if p + 8 <= len(data):
                        num, den = struct.unpack(e + 'II', data[p:p+8])
                        out[tag] = num / den if den else None
        read_ifd(u32(4))
    except Exception:
        pass
    return out


FOCAL, FOCAL35, EXPOSURE = 0x920A, 0xA405, 0x829A


def shot_info(path):
    """Focal length (35mm equivalent where known) and shutter speed."""
    focal = focal35 = exposure = None
    try:
        if is_raw(path):
            t = _tiff_tags(path, {FOCAL, FOCAL35, EXPOSURE})
            focal, focal35, exposure = t.get(FOCAL), t.get(FOCAL35), t.get(EXPOSURE)
        else:
            ex = Image.open(path).getexif()
            ifd = ex.get_ifd(0x8769) if hasattr(ex, 'get_ifd') else {}
            focal = ifd.get(FOCAL, ex.get(FOCAL))
            focal35 = ifd.get(FOCAL35, ex.get(FOCAL35))
            exposure = ifd.get(EXPOSURE, ex.get(EXPOSURE))
    except Exception:
        pass
    f = None
    for cand in (focal35, focal):
        if cand:
            try:
                f = float(cand); break
            except Exception:
                pass
    try:
        exposure = float(exposure) if exposure else None
    except Exception:
        exposure = None
    return dict(focal35=f, exposure=exposure)


def pixel_dims(path):
    try:
        if is_raw(path):
            d = sensor_dims(path)
            if d and d[0] > 0:
                return d
            # Sony and others keep only the preview in IFD0, so a number here
            # would understate the file. Report unknown rather than mislead.
            return (0, 0)
        with Image.open(path) as im:
            return im.size
    except Exception:
        return (0, 0)
