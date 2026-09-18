import ctypes
import os
import re
import stat
import sys
import tempfile
from ctypes import wintypes

reparsePoint = 0x400
tempNames = {"temp", "tmp"}


class RBInfo(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("i64Size", ctypes.c_longlong),
                ("i64NumItems", ctypes.c_longlong)]


def recycleBinInfo():
    """Return (bytes, items) across all drives, or (0, 0) if the shell call fails."""
    info = RBInfo()
    info.cbSize = ctypes.sizeof(RBInfo)
    try:
        hr = ctypes.windll.shell32.SHQueryRecycleBinW(None, ctypes.byref(info))
    except (AttributeError, OSError):
        return 0, 0
    if hr != 0:
        return 0, 0
    return info.i64Size, info.i64NumItems


def emptyRecycleBin():
    noConfirm, noProgress, noSound = 0x1, 0x2, 0x4
    hr = ctypes.windll.shell32.SHEmptyRecycleBinW(None, None, noConfirm | noProgress | noSound)
    return hr == 0


def tempDir():
    """Resolve %TEMP% and refuse anything that does not look like a temp folder."""
    raw = os.environ.get("TEMP") or os.environ.get("TMP") or tempfile.gettempdir()
    path = os.path.normpath(os.path.realpath(raw))
    parts = [p.lower() for p in path.split(os.sep) if p]
    if len(parts) < 3 or not os.path.isdir(path):
        return None
    if parts[-1] in tempNames or (parts[-2] in tempNames and parts[-1].isdigit()):
        return path
    return None


def steamRoot():
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam") as key:
            path = winreg.QueryValueEx(key, "SteamPath")[0]
    except OSError:
        path = os.path.join(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"), "Steam")
    return os.path.normpath(path) if path and os.path.isdir(path) else None


def steamShaderDirs():
    """shadercache folder of every Steam library listed in libraryfolders.vdf."""
    root = steamRoot()
    if not root:
        return []
    libs = [root]
    try:
        with open(os.path.join(root, "steamapps", "libraryfolders.vdf"), encoding="utf-8") as f:
            libs += [p.replace("\\\\", "\\") for p in re.findall(r'"path"\s+"([^"]+)"', f.read())]
    except OSError:
        pass
    return [os.path.join(os.path.normpath(lib), "steamapps", "shadercache") for lib in libs]


webCacheNames = ("Cache", "Code Cache", "GPUCache")


def webCacheDirs(root):
    """Cache folders of a Chromium/Electron data dir and of each profile under it.

    Only disposable caches: cookies, Local Storage and IndexedDB hold logins and are never listed.
    """
    if not os.path.isdir(root):
        return []
    homes = [("", root)]
    try:
        with os.scandir(root) as it:
            homes += [(e.name, e.path) for e in it if e.is_dir(follow_symlinks=False)
                      and os.path.isfile(os.path.join(e.path, "Preferences"))]
    except OSError:
        pass
    found = []
    for profile, home in homes:
        for name in webCacheNames:
            path = os.path.join(home, name)
            if os.path.isdir(path):
                found.append((path, profile, name))
    return found


def firefoxCacheDirs():
    root = os.path.expandvars(r"%LOCALAPPDATA%\Mozilla\Firefox\Profiles")
    try:
        with os.scandir(root) as it:
            profiles = [e for e in it if e.is_dir(follow_symlinks=False)]
    except OSError:
        return []
    return [(os.path.join(e.path, "cache2"), e.name.split(".", 1)[-1])
            for e in profiles if os.path.isdir(os.path.join(e.path, "cache2"))]


def defaultSkip():
    mei = getattr(sys, "_MEIPASS", None)
    return [mei] if mei else []


def isLink(entry):
    """True for symlinks and junctions; Python 3.11 is_symlink() misses junctions."""
    try:
        if entry.is_symlink():
            return True
        st = entry.stat(follow_symlinks=False)
        return bool(getattr(st, "st_file_attributes", 0) & reparsePoint)
    except OSError:
        return True


def walk(root, skip):
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
            if isLink(e):
                yield "link", e.path, 0
                continue
            try:
                isDir = e.is_dir(follow_symlinks=False)
            except OSError:
                continue
            if isDir:
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
    for kind, _, sz in walk(root, skip):
        if kind == "file":
            size += sz
            count += 1
    return size, count


def unlinkFile(path):
    try:
        os.unlink(path)
    except PermissionError:
        os.chmod(path, stat.S_IWRITE)
        os.unlink(path)


def clear(root, skip=(), progress=None):
    """Delete everything inside root (not root itself). Files in use are skipped."""
    freed = deleted = skipped = 0
    for kind, path, sz in walk(root, skip):
        try:
            if kind == "file":
                unlinkFile(path)
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
