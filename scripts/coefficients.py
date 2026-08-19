"""The numbers a baseline JPEG actually stores.

Everything else here reads a JPEG by decoding it to pixels. That is the wrong
end for one question: whether a file has been compressed twice. A JPEG stores
each 8x8 block as coefficients divided by a quantization table and rounded to
whole numbers, and a second save re-divides and re-rounds those, which maps
several old values onto one new one and leaves others unreachable. The trace is
in the integers. Decoding to pixels and taking the block DCT back does not
recover them — measured, the result lands a median of 0.2 off the nearest whole
number, which is near enough to uniform that no trace survives.

So this reads the entropy-coded data directly: markers, Huffman tables, and the
scan. Baseline sequential only. A progressive file interleaves coefficients
across scans and is declined rather than guessed at.
"""
import numpy as np

ZIGZAG = np.array([
     0,  1,  8, 16,  9,  2,  3, 10, 17, 24, 32, 25, 18, 11,  4,  5,
    12, 19, 26, 33, 40, 48, 41, 34, 27, 20, 13,  6,  7, 14, 21, 28,
    35, 42, 49, 56, 57, 50, 43, 36, 29, 22, 15, 23, 30, 37, 44, 51,
    58, 59, 52, 45, 38, 31, 39, 46, 53, 60, 61, 54, 47, 55, 62, 63])


class Unsupported(Exception):
    """This file is not a baseline JPEG, so the question does not apply."""


class _Huffman:
    """A JPEG Huffman table, as a dict from (length, code) to symbol."""

    __slots__ = ("lookup", "maxlen")

    def __init__(self, counts, symbols):
        self.lookup = {}
        code = i = 0
        for length in range(1, 17):
            for _ in range(counts[length - 1]):
                self.lookup[(length, code)] = symbols[i]
                code += 1
                i += 1
            code <<= 1
        self.maxlen = 16


class _Bits:
    """The scan's bits, with JPEG's 0xFF00 stuffing removed as it reads."""

    __slots__ = ("data", "pos", "bit", "end")

    def __init__(self, data, pos, end):
        self.data, self.pos, self.bit, self.end = data, pos, 0, end

    def read(self):
        if self.pos >= self.end:
            return 0                       # past the scan: pad, as decoders do
        b = self.data[self.pos]
        if b == 0xFF:
            nxt = self.data[self.pos + 1] if self.pos + 1 < self.end else 0
            if nxt != 0x00:
                return 0                   # a marker: the scan is over
        v = (b >> (7 - self.bit)) & 1
        self.bit += 1
        if self.bit == 8:
            self.bit = 0
            self.pos += 2 if b == 0xFF else 1
        return v

    def align(self):
        if self.bit:
            self.bit = 0
            self.pos += 1

    def receive(self, n):
        v = 0
        for _ in range(n):
            v = (v << 1) | self.read()
        return v

    def decode(self, table):
        code = 0
        for length in range(1, 17):
            code = (code << 1) | self.read()
            sym = table.lookup.get((length, code))
            if sym is not None:
                return sym
        raise Unsupported("a Huffman code did not resolve")


def _extend(v, n):
    return v - (1 << n) + 1 if n and v < (1 << (n - 1)) else v


def luma_coefficients(path, max_blocks=3000):
    """The quantized luma values as stored, shaped (blocks, 8, 8) in scan order.

    Raises Unsupported for anything that is not a baseline JPEG. Stops once
    `max_blocks` luma blocks are in hand — the scan must be read in order, but
    it need not be read to the end to have a histogram. 3,000 blocks costs
    about 100ms and gives the same answer as 20,000, which costs 670ms.
    """
    with open(path, "rb") as fh:
        d = fh.read()
    if d[:2] != b"\xff\xd8":
        raise Unsupported("not a JPEG")

    huff = {}
    frame = None
    restart = 0
    i = 2
    while i < len(d) - 1:
        if d[i] != 0xFF:
            i += 1
            continue
        m = d[i + 1]
        if m in (0xD8, 0x01) or 0xD0 <= m <= 0xD7:
            i += 2
            continue
        if m == 0xD9:
            break
        seg = int.from_bytes(d[i + 2:i + 4], "big")
        body = d[i + 4:i + 2 + seg]
        if m in (0xC2, 0xC1, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB,
                 0xCD, 0xCE, 0xCF):
            raise Unsupported("not baseline sequential")
        if m == 0xC0:
            h = int.from_bytes(body[1:3], "big")
            w = int.from_bytes(body[3:5], "big")
            n = body[5]
            comps = []
            for c in range(n):
                cid, hv, tq = body[6 + c * 3:9 + c * 3]
                comps.append({"id": cid, "h": hv >> 4, "v": hv & 15, "tq": tq})
            frame = {"w": w, "h": h, "comps": comps}
        elif m == 0xC4:
            p = 0
            while p < len(body):
                tc_th = body[p]
                counts = list(body[p + 1:p + 17])
                total = sum(counts)
                syms = list(body[p + 17:p + 17 + total])
                huff[(tc_th >> 4, tc_th & 15)] = _Huffman(counts, syms)
                p += 17 + total
        elif m == 0xDD:
            restart = int.from_bytes(body[0:2], "big")
        elif m == 0xDA:
            if frame is None:
                raise Unsupported("a scan arrived before the frame header")
            ns = body[0]
            scan = {}
            for c in range(ns):
                cs, td_ta = body[1 + c * 2:3 + c * 2]
                scan[cs] = (td_ta >> 4, td_ta & 15)
            start = i + 2 + seg
            return _scan(d, start, frame, scan, huff, restart, max_blocks)
        i += 2 + seg
    raise Unsupported("no scan found")


def _scan(d, start, frame, scan, huff, restart, max_blocks):
    comps = frame["comps"]
    hmax = max(c["h"] for c in comps)
    vmax = max(c["v"] for c in comps)
    mcux = -(-frame["w"] // (8 * hmax))
    mcuy = -(-frame["h"] // (8 * vmax))
    luma = comps[0]
    bits = _Bits(d, start, len(d))
    pred = {c["id"]: 0 for c in comps}
    out = []
    seen = 0
    for n in range(mcux * mcuy):
        if restart and n and n % restart == 0:
            bits.align()
            if (bits.pos + 1 < len(d) and d[bits.pos] == 0xFF
                    and 0xD0 <= d[bits.pos + 1] <= 0xD7):
                bits.pos += 2
            pred = {c["id"]: 0 for c in comps}
        for c in comps:
            dc_t, ac_t = scan.get(c["id"], (0, 0))
            for _ in range(c["h"] * c["v"]):
                block = _block(bits, huff[(0, dc_t)], huff[(1, ac_t)], pred, c)
                if c is luma:
                    out.append(block)
                    seen += 1
        if seen >= max_blocks:
            break
    if not out:
        raise Unsupported("the scan held no blocks")
    return np.asarray(out, dtype=np.int32).reshape(-1, 8, 8)


def _block(bits, dc_table, ac_table, pred, comp):
    z = np.zeros(64, dtype=np.int32)
    s = bits.decode(dc_table)
    diff = _extend(bits.receive(s), s) if s else 0
    pred[comp["id"]] += diff
    z[0] = pred[comp["id"]]
    k = 1
    while k < 64:
        rs = bits.decode(ac_table)
        r, s = rs >> 4, rs & 15
        if s == 0:
            if r != 15:
                break
            k += 16
            continue
        k += r
        if k > 63:
            break
        z[ZIGZAG[k]] = _extend(bits.receive(s), s)
        k += 1
    return z.reshape(8, 8)
