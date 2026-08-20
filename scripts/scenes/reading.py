"""Reading photographs into the little that round two needs.

A scene is decided from two things only: when a photograph was taken, and what
it looks like reduced to a sketch. Both are already computed for every file the
tool has ever seen, and both are already kept in the cache on disk, so this
borrows that machinery rather than repeating it — the reading is the expensive
part of any run and doing it twice would be the expensive part twice.
"""
import os
from multiprocessing.pool import Pool

import sift


def records(paths, note=None):
    """A record for each readable photograph, carrying its time and its sketch.

    Unreadable files are dropped rather than reported: round two is a choice
    about photographs, and a file nothing can open is not one.
    """
    prints = [sift._fp(p) for p in paths]
    known = {}
    db = sift._cache_open()
    if db is not None:
        want = [h for h in prints if h]
        try:
            for start in range(0, len(want), 500):
                chunk = want[start:start + 500]
                for h, blob in db.execute(
                        "SELECT md5, blob FROM probe WHERE v = ? AND md5 IN (%s)"
                        % ",".join("?" * len(chunk)),
                        [sift.PROBE_VERSION] + chunk):
                    known[h] = blob
        except Exception:
            known.clear()

    out, missing = [None] * len(paths), []
    for i, (path, h) in enumerate(zip(paths, prints)):
        got = sift._unpack(known[h]) if h in known else None
        if got is None:
            missing.append((i, path, h))
        else:
            out[i] = got

    if missing:
        with Pool(os.cpu_count() or 4) as pool:
            for n, got in enumerate(pool.imap(
                    sift._probe_pair, [(p, h) for _, p, h in missing],
                    chunksize=4), 1):
                out[missing[n - 1][0]] = got
                if note:
                    note(n, len(missing), "reading photographs")
        if db is not None:
            rows = [(out[i]["md5"], sift.PROBE_VERSION, sift._pack(out[i]))
                    for i, _, _ in missing if "error" not in out[i]]
            try:
                db.executemany("INSERT OR REPLACE INTO probe VALUES (?,?,?)", rows)
                db.commit()
            except Exception:
                pass

    # The facts the cache deliberately does not hold, because they belong to
    # the file on disk rather than to the picture inside it.
    ready = []
    for path, print_, got in zip(paths, prints, out):
        if got is None or "error" in got:
            continue
        got["path"] = path
        got["md5"] = print_ or got.get("md5")
        got["bytes"] = os.path.getsize(path)
        got["t"] = got.get("exif_t") or sift.time_fallback(path)
        ready.append(got)
    return ready
