"""PhotoCruller's one setting: the working folder, in scripts/settings.conf.

    working folder = /Volumes/SomeDrive/Some Folder

It holds everything the tool produces, and is never the library being scanned.
The environment variable PHOTOCRULLER_DIR overrides, mainly for tests.
cull.py asks on first run when nothing is set, and writes the answer here.
"""
import os

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL_ROOT = os.path.dirname(HERE)
SETTINGS = os.path.join(HERE, "settings.conf")


def _read():
    out = {}
    try:
        for line in open(SETTINGS):
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                out[k.strip().lower()] = v.strip()
    except OSError:
        pass
    return out


def working_dir():
    """The folder that holds everything the tool produces, or None if unset."""
    return (os.environ.get("PHOTOCRULLER_DIR")
            or _read().get("working folder") or None)


def save_working(path):
    """Set the working folder, preserving whatever else the file says."""
    kv = _read()
    kv["working folder"] = os.path.abspath(path).rstrip(os.sep)
    with open(SETTINGS, "w") as fh:
        for k, v in kv.items():
            fh.write(f"{k} = {v}\n")
