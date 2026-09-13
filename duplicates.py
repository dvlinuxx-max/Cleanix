import os
import hashlib
import time

from cleaner import is_link


def _hash_file(path, partial=False, chunk=1024 * 1024):
    h = hashlib.blake2b(digest_size=16)
    try:
        with open(path, "rb", buffering=0) as f:
            if partial:
                data = f.read(64 * 1024)
                h.update(data)
            else:
                while True:
                    block = f.read(chunk)
                    if not block:
                        break
                    h.update(block)
        return h.hexdigest()
    except (PermissionError, OSError):
        return None


def _unique_files(paths):
    """Drop paths that point at the same file (hardlinks, same file seen twice)."""
    seen, out = set(), []
    for p in paths:
        try:
            st = os.stat(p)
            key = (st.st_dev, st.st_ino) if st.st_ino else os.path.normcase(os.path.realpath(p))
        except OSError:
            continue
        if key not in seen:
            seen.add(key)
            out.append(p)
    return out


class DuplicateEngine:

    def __init__(self, root_path, min_size, progress_q, stop_event):
        self.root = root_path
        self.min_size = min_size
        self.q = progress_q
        self.stop = stop_event

    def run(self):
        try:
            self._find()
        except Exception as e:
            self.q.put(("dup_error", str(e)))

    def _find(self):
        by_size = {}
        scanned = 0
        last = time.time()
        stack = [self.root]
        while stack:
            if self.stop.is_set():
                self.q.put(("dup_cancelled", None)); return
            cur = stack.pop()
            low = cur.lower()
            if "\\windows\\winsxs" in low or "\\$recycle.bin" in low:
                continue
            try:
                with os.scandir(cur) as it:
                    entries = list(it)
            except OSError:
                continue
            for e in entries:
                if is_link(e):
                    continue
                try:
                    if e.is_dir(follow_symlinks=False):
                        stack.append(e.path)
                        continue
                    sz = e.stat(follow_symlinks=False).st_size
                except OSError:
                    continue
                if sz < self.min_size:
                    continue
                by_size.setdefault(sz, []).append(e.path)
                scanned += 1
                if time.time() - last > 0.2:
                    last = time.time()
                    self.q.put(("dup_progress", f"المسح: {scanned:,} ملف مرشح"))

        candidates = {s: ps for s, ps in by_size.items() if len(ps) > 1}

        groups = {}
        total_groups = len(candidates)
        done = 0
        for sz, paths in candidates.items():
            if self.stop.is_set():
                self.q.put(("dup_cancelled", None)); return
            done += 1
            paths = _unique_files(paths)
            if len(paths) < 2:
                continue
            partial = {}
            for p in paths:
                ph = _hash_file(p, partial=True)
                if ph:
                    partial.setdefault((sz, ph), []).append(p)
            for key, plist in partial.items():
                if len(plist) < 2:
                    continue
                for p in plist:
                    fh = _hash_file(p, partial=False)
                    if fh:
                        groups.setdefault((sz, fh), []).append(p)
            if done % 5 == 0:
                self.q.put(("dup_progress",
                            f"تحليل البصمات: {done} من {total_groups} مجموعة حجم"))

        result = []
        wasted = 0
        for (sz, fh), plist in groups.items():
            if len(plist) > 1:
                result.append({"size": sz, "count": len(plist), "paths": sorted(plist)})
                wasted += sz * (len(plist) - 1)
        result.sort(key=lambda g: g["size"] * (g["count"] - 1), reverse=True)
        self.q.put(("dup_done", {"groups": result, "wasted": wasted}))
