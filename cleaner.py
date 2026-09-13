import ctypes
import os
import stat
import sys
import tempfile
from ctypes import wintypes

REPARSE_POINT = 0x400
TEMP_NAMES = {"temp", "tmp"}


class _RBInfo(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("i64Size", ctypes.c_longlong),
                ("i64NumItems", ctypes.c_longlong)]


def recycle_bin_info():
    """Return (bytes, items) across all drives, or (0, 0) if the shell call fails."""
    info = _RBInfo()
    info.cbSize = ctypes.sizeof(_RBInfo)
    try:
        hr = ctypes.windll.shell32.SHQueryRecycleBinW(None, ctypes.byref(info))
    except (AttributeError, OSError):
        return 0, 0
    if hr != 0:
        return 0, 0
    return info.i64Size, info.i64NumItems


def empty_recycle_bin():
    no_confirm, no_progress, no_sound = 0x1, 0x2, 0x4
    hr = ctypes.windll.shell32.SHEmptyRecycleBinW(None, None, no_confirm | no_progress | no_sound)
    return hr == 0


def temp_dir():
    """Resolve %TEMP% and refuse anything that does not look like a temp folder."""
    raw = os.environ.get("TEMP") or os.environ.get("TMP") or tempfile.gettempdir()
    path = os.path.normpath(os.path.realpath(raw))
    parts = [p.lower() for p in path.split(os.sep) if p]
    if len(parts) < 3 or not os.path.isdir(path):
        return None
    if parts[-1] in TEMP_NAMES or (parts[-2] in TEMP_NAMES and parts[-1].isdigit()):
        return path
    return None


def default_skip():
    mei = getattr(sys, "_MEIPASS", None)
    return [mei] if mei else []


def is_link(entry):
    """True for symlinks and junctions; Python 3.11 is_symlink() misses junctions."""
    try:
        if entry.is_symlink():
            return True
        st = entry.stat(follow_symlinks=False)
        return bool(getattr(st, "st_file_attributes", 0) & REPARSE_POINT)
    except OSError:
        return True


def _walk(root, skip):
    skip = {os.path.normcase(os.path.normpath(p)) for p in skip}
    dirs = []
    stack = [root]
    while stack:
        cur = stack.pop()
        try:
            with os.scandir(cur) as it:
                items = list(it)
        except OSError:
            continue
        for e in items:
            if os.path.normcase(e.path) in skip:
                continue
            if is_link(e):
                yield "link", e.path, 0
                continue
            try:
                is_dir = e.is_dir(follow_symlinks=False)
            except OSError:
                continue
            if is_dir:
                stack.append(e.path)
                dirs.append(e.path)
            else:
                try:
                    size = e.stat(follow_symlinks=False).st_size
                except OSError:
                    size = 0
                yield "file", e.path, size
    for d in reversed(dirs):
        yield "dir", d, 0


def measure(root, skip=()):
    size = count = 0
    for kind, _, sz in _walk(root, skip):
        if kind == "file":
            size += sz
            count += 1
    return size, count


def _unlink(path):
    try:
        os.unlink(path)
    except PermissionError:
        os.chmod(path, stat.S_IWRITE)
        os.unlink(path)


def clear(root, skip=(), progress=None):
    """Delete everything inside root (not root itself). Files in use are skipped."""
    freed = deleted = skipped = 0
    for kind, path, sz in _walk(root, skip):
        try:
            if kind == "file":
                _unlink(path)
                freed += sz
                deleted += 1
                if progress and deleted % 250 == 0:
                    progress(deleted, freed)
            elif kind == "link":
                try:
                    os.rmdir(path)
                except OSError:
                    os.unlink(path)
            else:
                os.rmdir(path)
        except OSError:
            if kind == "file":
                skipped += 1
    return freed, deleted, skipped
