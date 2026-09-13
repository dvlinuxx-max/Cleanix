import os
import sys
import threading
import queue
import time
import ctypes
import subprocess
import string
import shutil
import webbrowser

import tkinter as tk
from tkinter import ttk, filedialog, messagebox

import fileinfo
import cleaner
import updater
from duplicates import DuplicateEngine

try:
    from send2trash import send2trash
    HAS_SEND2TRASH = True
except ImportError:
    HAS_SEND2TRASH = False


APP_VERSION = "2.2.0"
SITE_URL = "https://mohmadev.com/"
APP_NAME = "Cleanix"
REPO_URL = "https://github.com/dvlinuxx-max/Cleanix"
CONTACT_EMAIL = "dvlinuxx@gmail.com"

FONT = "Segoe UI"
C = {
    "navy": "#0F2A4A", "navy_sub": "#B6C6DB",
    "bg": "#F2F5FA", "card": "#FFFFFF", "line": "#DCE3ED", "stripe": "#F7F9FC",
    "head": "#EAF0F7", "text": "#1B2430", "muted": "#5E6B7B",
    "blue": "#1A5FC8", "blue_h": "#154EA6", "blue_t": "#E4EEFB",
    "green": "#15803D", "green_h": "#116A32", "green_t": "#E1F3E8",
    "amber": "#B45309", "amber_t": "#FDF0D9",
    "red": "#C62828", "red_h": "#A32020", "red_t": "#FBE4E2",
    "gray": "#E4E9F0", "gray_h": "#D3DAE4", "disabled": "#9AA5B3",
}


def resource(name):
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, "assets", name)


def human_size(num):
    for unit in ("B", "KB", "MB", "GB", "TB", "PB"):
        if abs(num) < 1024.0:
            return f"{num:,.1f} {unit}"
        num /= 1024.0
    return f"{num:,.1f} EB"


AR_UNITS = ("بايت", "كيلوبايت", "ميغابايت", "غيغابايت", "تيرابايت")


def ar_size(num):
    """Size with Arabic units; Tk misorders Latin units inside Arabic sentences."""
    for unit in AR_UNITS:
        if abs(num) < 1024.0:
            return f"{num:,.1f} {unit}"
        num /= 1024.0
    return f"{num * 1024:,.1f} {AR_UNITS[-1]}"


def open_in_explorer(path):
    try:
        if os.path.isdir(path):
            os.startfile(path)
        else:
            subprocess.run(["explorer", "/select,", os.path.normpath(path)])
    except Exception as e:
        messagebox.showerror("خطأ", f"تعذر فتح المسار:\n{e}")


USER_FOLDERS = ("Desktop", "Documents", "Downloads", "Pictures", "Videos", "Music", "AppData",
                "OneDrive", "Favorites", "Contacts", "Links", "Saved Games", "Searches", "3D Objects")


def _protected_paths():
    env = os.environ
    items = [r"C:\Windows", r"C:\Program Files", r"C:\Program Files (x86)", r"C:\ProgramData",
             r"C:\Users"]
    items += [env.get(k, "") for k in ("SystemRoot", "ProgramFiles", "ProgramFiles(x86)", "ProgramData",
                                       "PUBLIC", "USERPROFILE", "LOCALAPPDATA", "APPDATA", "OneDrive",
                                       "TEMP", "TMP")]
    for base in (env.get("USERPROFILE", ""), env.get("OneDrive", "")):
        if base:
            items += [os.path.join(base, name) for name in USER_FOLDERS]
    if env.get("USERPROFILE"):
        items += [os.path.join(env["USERPROFILE"], "AppData", n) for n in ("Local", "LocalLow", "Roaming")]
    return {os.path.normcase(os.path.normpath(p)) for p in items if p}


PROTECTED = _protected_paths()


def is_protected(path):
    """System folders, the user's own base folders, drive roots, and anything that contains them."""
    np = os.path.normcase(os.path.normpath(path))
    if np in PROTECTED:
        return True
    if len(np) <= 3 and np[1:].startswith(":"):
        return True
    prefix = np.rstrip("\\") + "\\"
    return any(p.startswith(prefix) for p in PROTECTED)


class Btn(tk.Button):
    KINDS = {
        "primary": (C["blue"], C["blue_h"], "#FFFFFF"),
        "success": (C["green"], C["green_h"], "#FFFFFF"),
        "danger": (C["red"], C["red_h"], "#FFFFFF"),
        "neutral": (C["gray"], C["gray_h"], C["text"]),
        "navy": ("#2A5082", "#346096", "#FFFFFF"),
    }

    def __init__(self, master, text, command, kind="neutral", size=10, padx=14, pady=6, state="normal"):
        self._bg, self._hover, fg = self.KINDS[kind]
        super().__init__(master, text=text, command=command, bg=self._bg, fg=fg,
                         activebackground=self._hover, activeforeground=fg,
                         disabledforeground=C["disabled"], relief="flat", bd=0,
                         highlightthickness=0, cursor="hand2", padx=padx, pady=pady,
                         font=(FONT, size, "bold"))
        self.bind("<Enter>", self._enter)
        self.bind("<Leave>", self._leave)
        self.configure(state=state)

    def configure(self, cnf=None, **kw):
        if "state" in kw:
            on = kw["state"] == "normal"
            kw["bg"] = self._bg if on else C["gray"]
            kw["cursor"] = "hand2" if on else "arrow"
        return super().configure(cnf, **kw)

    config = configure

    def _enter(self, _):
        if str(self["state"]) == "normal":
            tk.Button.configure(self, bg=self._hover)

    def _leave(self, _):
        if str(self["state"]) == "normal":
            tk.Button.configure(self, bg=self._bg)


class TabView(tk.Frame):
    """Right-aligned tab bar; ttk.Notebook cannot place tabs on the right."""

    def __init__(self, master, on_change=None):
        super().__init__(master, bg=C["bg"])
        self.on_change = on_change
        self.bar = tk.Frame(self, bg=C["bg"])
        self.bar.pack(fill="x")
        self.body = tk.Frame(self, bg=C["card"], highlightbackground=C["line"], highlightthickness=1)
        self.body.pack(fill="both", expand=True)
        self.tabs = []
        self.frames = []
        self.current = -1

    def add(self, frame, title):
        idx = len(self.tabs)
        tab = tk.Label(self.bar, text=title, font=(FONT, 10, "bold"), padx=18, pady=8, cursor="hand2")
        tab.pack(side="right", padx=(0, 3))
        tab.bind("<Button-1>", lambda e, i=idx: self.select(i))
        tab.bind("<Enter>", lambda e, i=idx: self._hover(i, True))
        tab.bind("<Leave>", lambda e, i=idx: self._hover(i, False))
        self.tabs.append(tab)
        self.frames.append(frame)
        self._paint(idx)

    def select(self, idx):
        if idx == self.current:
            return
        if self.current >= 0:
            self.frames[self.current].pack_forget()
        self.current = idx
        self.frames[idx].pack(fill="both", expand=True)
        for i in range(len(self.tabs)):
            self._paint(i)
        if self.on_change:
            self.on_change()

    def _paint(self, i):
        if i == self.current:
            self.tabs[i].config(bg=C["card"], fg=C["blue"])
        else:
            self.tabs[i].config(bg=C["gray"], fg=C["muted"])

    def _hover(self, i, inside):
        if i != self.current:
            self.tabs[i].config(bg=C["gray_h"] if inside else C["gray"])


def card(parent, **kw):
    return tk.Frame(parent, bg=C["card"], highlightbackground=C["line"], highlightthickness=1, **kw)


class ScanEngine:
    def __init__(self, root_path, progress_q, stop_event):
        self.root_path = root_path
        self.q = progress_q
        self.stop = stop_event
        self.total_bytes = 0
        self.file_count = 0
        self.dir_sizes = {}
        self.big_files = []
        self.cat_bytes = {}

    def run(self):
        try:
            self._scan(self.root_path)
        except Exception as e:
            self.q.put(("error", str(e)))
            return
        if self.stop.is_set():
            self.q.put(("cancelled", None))
            return
        self.big_files.sort(key=lambda x: x[1], reverse=True)
        self.q.put(("done", {
            "dir_sizes": self.dir_sizes,
            "big_files": self.big_files[:1000],
            "total_bytes": self.total_bytes,
            "file_count": self.file_count,
            "cat_bytes": self.cat_bytes,
        }))

    def _quick_cat(self, name):
        ext = os.path.splitext(name)[1].lstrip(".").lower()
        d = fileinfo._EXT_MAP.get(ext)
        return d[1] if d else "other"

    def _scan(self, path):
        stack = [path]
        direct = {}
        children = {}
        last_report = time.time()
        all_dirs = []
        while stack:
            if self.stop.is_set():
                return
            cur = stack.pop()
            all_dirs.append(cur)
            direct.setdefault(cur, 0)
            children.setdefault(cur, [])
            try:
                with os.scandir(cur) as it:
                    for entry in it:
                        if self.stop.is_set():
                            return
                        try:
                            if cleaner.is_link(entry):
                                continue
                            if entry.is_dir(follow_symlinks=False):
                                children[cur].append(entry.path)
                                stack.append(entry.path)
                            elif entry.is_file(follow_symlinks=False):
                                sz = entry.stat(follow_symlinks=False).st_size
                                direct[cur] += sz
                                self.total_bytes += sz
                                self.file_count += 1
                                cat = self._quick_cat(entry.name)
                                self.cat_bytes[cat] = self.cat_bytes.get(cat, 0) + sz
                                if sz >= 5 * 1024 * 1024:
                                    self.big_files.append((entry.path, sz))
                        except (PermissionError, OSError):
                            continue
            except (PermissionError, OSError):
                continue
            now = time.time()
            if now - last_report > 0.15:
                last_report = now
                self.q.put(("progress", {
                    "current": cur, "total_bytes": self.total_bytes,
                    "file_count": self.file_count,
                }))
        if self.stop.is_set():
            return
        sizes = dict(direct)
        for d in sorted(all_dirs, key=lambda p: p.count(os.sep), reverse=True):
            total = direct.get(d, 0)
            for ch in children.get(d, []):
                total += sizes.get(ch, 0)
            sizes[d] = total
        self.dir_sizes = sizes


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.scale = max(1.0, self.winfo_fpixels("1i") / 96.0)
        self.tk.call("tk", "scaling", self.scale * 96 / 72)
        self.title(APP_NAME)
        want_w, want_h = self.px(1320), self.px(800)
        w = min(want_w, self.winfo_screenwidth() - 40)
        h = min(want_h, self.winfo_screenheight() - 80)
        self.geometry(f"{w}x{h}")
        self.minsize(min(self.px(1080), w), min(self.px(660), h))
        if w < want_w or h < want_h:
            self.state("zoomed")
        self.configure(bg=C["bg"])
        try:
            self.iconbitmap(default=resource("icon.ico"))
        except tk.TclError:
            pass
        try:
            size = 88 if self.scale >= 1.75 else 66 if self.scale >= 1.25 else 44
            self._logo = tk.PhotoImage(file=resource(f"logo_{size}.png"))
        except tk.TclError:
            self._logo = None

        self.stop_event = threading.Event()
        self.progress_q = queue.Queue()
        self.dup_stop = threading.Event()
        self.dup_q = queue.Queue()
        self.boost_q = queue.Queue()
        self.result = None
        self.current_root = None
        self.dup_groups = []
        self._info_cache = {}
        self._tree_nodes = {}
        self._junk_rows = {}
        self._junk_busy = False

        self._build_style()
        self._build_widgets()
        self._refresh_drives()

    def px(self, n):
        return int(round(n * self.scale))

    def _build_style(self):
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure(".", font=(FONT, 10), background=C["bg"])
        style.configure("Treeview", background=C["card"], fieldbackground=C["card"],
                        foreground=C["text"], rowheight=self.px(28), font=(FONT, 10), borderwidth=0)
        style.map("Treeview", background=[("selected", C["blue_t"])],
                  foreground=[("selected", C["text"])])
        style.configure("Treeview.Heading", font=(FONT, 10, "bold"), background=C["head"],
                        foreground=C["text"], relief="flat", padding=(6, 6))
        style.map("Treeview.Heading", background=[("active", C["gray_h"])])
        style.configure("TProgressbar", background=C["green"], troughcolor=C["gray"], borderwidth=0)

    def _build_widgets(self):
        self._build_header()
        self._build_steps()

        self.drives_frame = tk.Frame(self, bg=C["bg"])
        self.drives_frame.pack(fill="x", padx=14, pady=(10, 4))

        self._build_credits()
        self._build_bottom()

        main = tk.Frame(self, bg=C["bg"])
        main.pack(fill="both", expand=True, padx=14, pady=6)

        self._build_details_panel(main)

        self.nb = TabView(main, on_change=self._clear_details)
        self.nb.pack(side="right", fill="both", expand=True)
        self._build_tree_tab()
        self._build_files_tab()
        self._build_dup_tab()
        self._build_junk_tab()
        self.nb.select(0)

    def _build_credits(self):
        strip = tk.Frame(self, bg=C["navy"], padx=14, pady=6)
        strip.pack(fill="x", side="bottom")
        tk.Label(strip, text=f"v{APP_VERSION}", bg=C["navy"], fg=C["navy_sub"],
                 font=(FONT, 9)).pack(side="right")
        tk.Label(strip, text=APP_NAME, bg=C["navy"], fg="#FFFFFF",
                 font=(FONT, 10, "bold")).pack(side="right", padx=(0, 8))
        Btn(strip, "License", self._show_license, kind="navy", size=9, padx=16, pady=3).pack(side="left")
        self.update_box = tk.Frame(strip, bg=C["navy"])
        self.after(2000, self._check_updates)

    def _check_updates(self):
        q = queue.Queue()
        threading.Thread(target=lambda: q.put(updater.newer_release(APP_VERSION)), daemon=True).start()

        def poll():
            try:
                rel = q.get_nowait()
            except queue.Empty:
                self.after(500, poll)
                return
            if rel:
                self._show_update(*rel)

        self.after(500, poll)

    def _manual_update_check(self, win, btn, result):
        def show(text, fg):
            for w in result.winfo_children():
                w.destroy()
            tk.Label(result, text=text, bg=C["card"], fg=fg, font=(FONT, 10, "bold")).pack(side="right")

        btn.config(state="disabled")
        show("جاري الفحص", C["blue"])
        q = queue.Queue()
        threading.Thread(target=lambda: q.put(updater.check(APP_VERSION)), daemon=True).start()

        def poll():
            if not win.winfo_exists():
                return
            try:
                state, tag, url = q.get_nowait()
            except queue.Empty:
                win.after(200, poll)
                return
            btn.config(state="normal")
            if state == "newer":
                show("يتوفر اصدار جديد", C["green"])
                tk.Label(result, text=tag, bg=C["card"], fg=C["green"],
                         font=(FONT, 10, "bold")).pack(side="right", padx=(0, 6))
                Btn(result, "تنزيل", lambda: webbrowser.open(url or REPO_URL + "/releases/latest"),
                    kind="success", size=9, padx=12, pady=3).pack(side="right", padx=(0, 10))
                self._show_update(tag, url)
            elif state == "latest":
                show("لديك احدث اصدار", C["green"])
            elif state == "none":
                show("لا توجد اصدارات منشورة بعد", C["muted"])
            else:
                show("تعذر الاتصال، تاكد من الانترنت", C["red"])

        win.after(200, poll)

    def _show_update(self, tag, url):
        box = self.update_box
        if box.winfo_children():
            return
        Btn(box, "يتوفر اصدار جديد", lambda: webbrowser.open(url or REPO_URL + "/releases/latest"),
            kind="success", size=9, padx=14, pady=3).pack(side="left")
        tk.Label(box, text=tag, bg=C["navy"], fg="#8FE3AE", font=(FONT, 9, "bold")).pack(side="left", padx=8)
        box.pack(side="left", padx=12)

    def _show_license(self):
        if getattr(self, "_license_win", None) and self._license_win.winfo_exists():
            self._license_win.lift()
            return
        win = tk.Toplevel(self)
        self._license_win = win
        win.title("License")
        win.configure(bg=C["card"])
        win.resizable(False, False)
        win.transient(self)
        try:
            win.iconbitmap(resource("icon.ico"))
        except tk.TclError:
            pass

        head = tk.Frame(win, bg=C["navy"], padx=20, pady=14)
        head.pack(fill="x")
        if self._logo:
            tk.Label(head, image=self._logo, bg=C["navy"]).pack(side="right", padx=(12, 0))
        titles = tk.Frame(head, bg=C["navy"])
        titles.pack(side="right")
        tk.Label(titles, text=APP_NAME, bg=C["navy"], fg="#FFFFFF",
                 font=(FONT, 15, "bold")).pack(anchor="e")
        tk.Label(titles, text=f"v{APP_VERSION}", bg=C["navy"], fg=C["navy_sub"],
                 font=(FONT, 10)).pack(anchor="e")

        body = tk.Frame(win, bg=C["card"], padx=24, pady=18)
        body.pack(fill="both", expand=True)
        tk.Label(body, text="جميع حقوق البرنامج محفوظة", bg=C["card"], fg=C["navy"],
                 font=(FONT, 13, "bold")).pack(anchor="e")
        tk.Label(body, text="للمهندس محمد عبدالرحمن", bg=C["card"], fg=C["text"],
                 font=(FONT, 12)).pack(anchor="e", pady=(2, 14))

        def row(label, value, url=None):
            line = tk.Frame(body, bg=C["card"])
            line.pack(fill="x", pady=4)
            tk.Label(line, text=label, bg=C["card"], fg=C["muted"], width=10, anchor="e",
                     font=(FONT, 10, "bold")).pack(side="right")
            val = tk.Label(line, text=value, bg=C["card"], anchor="e",
                           fg=C["blue"] if url else C["text"],
                           font=(FONT, 10, "underline") if url else (FONT, 10),
                           cursor="hand2" if url else "arrow")
            val.pack(side="right", padx=(0, 10))
            if url:
                val.bind("<Button-1>", lambda e: webbrowser.open(url))

        row("الموقع", SITE_URL.split("//")[1].rstrip("/"), SITE_URL)
        row("البريد", CONTACT_EMAIL, "mailto:" + CONTACT_EMAIL)
        row("المصدر", REPO_URL.split("//")[1], REPO_URL)
        row("الاصدار", APP_VERSION)

        upd = tk.Frame(body, bg=C["card"])
        upd.pack(fill="x", pady=(10, 0))
        upd_btn = Btn(upd, "فحص التحديثات", None, kind="primary", size=9, padx=14, pady=4)
        upd_btn.pack(side="right")
        upd_result = tk.Frame(upd, bg=C["card"])
        upd_result.pack(side="right", padx=(0, 12))
        upd_btn.config(command=lambda: self._manual_update_check(win, upd_btn, upd_result))

        lic = tk.Frame(body, bg=C["green_t"], padx=12, pady=8)
        lic.pack(fill="x", pady=(16, 0))
        tk.Label(lic, text="يعمل البرنامج تحت رخصة", bg=C["green_t"], fg=C["green"],
                 font=(FONT, 10, "bold")).pack(side="right")
        lic_link = tk.Label(lic, text="MIT License", bg=C["green_t"], fg=C["green"], cursor="hand2",
                            font=(FONT, 10, "bold", "underline"))
        lic_link.pack(side="right", padx=(0, 4))
        lic_link.bind("<Button-1>", lambda e: webbrowser.open(REPO_URL + "/blob/main/LICENSE"))

        note = tk.Frame(body, bg=C["blue_t"], padx=12, pady=8)
        note.pack(fill="x", pady=(8, 0))
        tk.Label(note, text="تطوير البرنامج متاح للمستخدمين حصرا عبر", bg=C["blue_t"], fg=C["blue"],
                 font=(FONT, 10, "bold")).pack(side="right")
        tk.Label(note, text="GitHub", bg=C["blue_t"], fg=C["blue"],
                 font=(FONT, 10, "bold")).pack(side="right", padx=(0, 4))
        tk.Label(body, text="Copyright 2026 Mohammed Abd Alrahman", bg=C["card"], fg=C["muted"],
                 font=(FONT, 9)).pack(anchor="e", pady=(12, 0))

        foot = tk.Frame(win, bg=C["card"], padx=24, pady=14)
        foot.pack(fill="x")
        Btn(foot, "اغلاق", win.destroy, kind="primary", padx=24).pack(side="left")

        win.update_idletasks()
        x = self.winfo_rootx() + (self.winfo_width() - win.winfo_width()) // 2
        y = self.winfo_rooty() + (self.winfo_height() - win.winfo_height()) // 2
        win.geometry(f"+{max(x, 0)}+{max(y, 0)}")
        win.bind("<Escape>", lambda e: win.destroy())
        win.grab_set()
        win.focus_set()

    def _build_bottom(self):
        bottom = tk.Frame(self, bg=C["card"], highlightbackground=C["line"], highlightthickness=1)
        bottom.pack(fill="x", side="bottom")
        inner = tk.Frame(bottom, bg=C["card"], padx=14, pady=8)
        inner.pack(fill="x")
        mode = "سلة المهملات" if HAS_SEND2TRASH else "حذف نهائي"
        self.del_btn = Btn(inner, f"حذف المحدد ({mode})", self._delete_selected, kind="danger")
        self.del_btn.pack(side="left")
        self.open_btn = Btn(inner, "فتح الموقع", self._open_selected)
        self.open_btn.pack(side="left", padx=8)
        self.status = tk.Label(inner, text="جاهز، اختر القرص واضغط ابدأ الفحص", bg=C["card"],
                               fg=C["muted"], font=(FONT, 10), anchor="e")
        self.progress = ttk.Progressbar(inner, mode="indeterminate", length=180)
        self.status.pack(side="right", fill="x", expand=True, padx=(12, 0))

    def _busy(self, on):
        if on:
            if not self.progress.winfo_ismapped():
                self.progress.pack(side="right", after=self.status)
            self.progress.start(12)
        else:
            self.progress.stop()
            self.progress.pack_forget()

    def _build_header(self):
        header = tk.Frame(self, bg=C["navy"], padx=18, pady=12)
        header.pack(fill="x")
        brand = tk.Frame(header, bg=C["navy"])
        brand.pack(side="right")
        if self._logo:
            tk.Label(brand, image=self._logo, bg=C["navy"]).pack(side="right", padx=(12, 0))
        titles = tk.Frame(brand, bg=C["navy"])
        titles.pack(side="right")
        tk.Label(titles, text=APP_NAME, font=(FONT, 16, "bold"),
                 fg="#FFFFFF", bg=C["navy"]).pack(anchor="e")
        tk.Label(titles, text="اعرف ما الذي يستهلك مساحة جهازك ونظفه بامان",
                 font=(FONT, 10), fg=C["navy_sub"], bg=C["navy"]).pack(anchor="e")

        actions = tk.Frame(header, bg=C["navy"])
        actions.pack(side="left")
        self.boost_btn = self._header_action(actions, "تسريع الحاسوب", "يمسح الملفات المؤقتة",
                                             self._speed_up, "success")
        self.bin_btn = self._header_action(actions, "تفريغ سلة المهملات", "يحرر مساحة الملفات المحذوفة",
                                           self._clean_recycle_bin, "navy")

    def _header_action(self, parent, text, caption, command, kind):
        box = tk.Frame(parent, bg=C["navy"])
        box.pack(side="left", padx=(0, 14))
        btn = Btn(box, text, command, kind=kind, size=12, padx=24, pady=9)
        btn.pack(fill="x")
        tk.Label(box, text=caption, font=(FONT, 9), fg=C["navy_sub"], bg=C["navy"]).pack(pady=(4, 0))
        return btn

    def _step_badge(self, parent, number, text):
        box = tk.Frame(parent, bg=C["card"])
        d = self.px(24)
        cv = tk.Canvas(box, width=d, height=d, bg=C["card"], highlightthickness=0)
        cv.create_oval(1, 1, d - 1, d - 1, fill=C["blue"], outline="")
        cv.create_text(d // 2, d // 2, text=str(number), fill="#FFFFFF", font=(FONT, 10, "bold"))
        cv.pack(side="right")
        tk.Label(box, text=text, bg=C["card"], fg=C["text"],
                 font=(FONT, 10, "bold")).pack(side="right", padx=(6, 8))
        return box

    def _build_steps(self):
        wrap = card(self)
        wrap.pack(fill="x", padx=14, pady=(12, 0))
        row = tk.Frame(wrap, bg=C["card"], padx=12, pady=10)
        row.pack(fill="x")

        self._step_badge(row, 1, "اختر القرص").pack(side="right")
        self.drive_var = tk.StringVar()
        self.drive_combo = ttk.Combobox(row, textvariable=self.drive_var, width=16, state="readonly")
        self.drive_combo.pack(side="right", padx=(0, 6))
        Btn(row, "او مجلد محدد", self._pick_folder).pack(side="right", padx=(0, 4))

        tk.Frame(row, bg=C["line"], width=1).pack(side="right", fill="y", padx=16)

        self._step_badge(row, 2, "افحص").pack(side="right")
        self.scan_btn = Btn(row, "ابدأ الفحص", self._start_scan, kind="primary", padx=20)
        self.scan_btn.pack(side="right", padx=(0, 6))
        self.stop_btn = Btn(row, "ايقاف", self._stop_scan, state="disabled")
        self.stop_btn.pack(side="right")

        tk.Frame(row, bg=C["line"], width=1).pack(side="right", fill="y", padx=16)

        self._step_badge(row, 3, "راجع النتائج واحذف ما لا تحتاجه").pack(side="right")

        Btn(row, "تحديث الاقراص", self._refresh_drives).pack(side="left")

    def _tab_frame(self, title):
        frame = tk.Frame(self.nb.body, bg=C["card"])
        self.nb.add(frame, title)
        return frame

    def _toolbar(self, parent):
        bar = tk.Frame(parent, bg=C["card"], padx=10, pady=8)
        bar.pack(fill="x")
        return bar

    def _hint(self, parent, text, **kw):
        return tk.Label(parent, text=text, bg=C["card"], fg=C["muted"], font=(FONT, 10), **kw)

    @staticmethod
    def _stripe_tags(tree):
        tree.tag_configure("even", background=C["stripe"])
        tree.tag_configure("group", background=C["blue_t"], font=(FONT, 10, "bold"))

    def _scrolled(self, parent, tree):
        vsb = ttk.Scrollbar(parent, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        tree.pack(side="left", fill="both", expand=True)
        self._stripe_tags(tree)

    def _build_tree_tab(self):
        frame = self._tab_frame("شجرة المجلدات")
        bar = self._toolbar(frame)
        self._hint(bar, "المجلدات مرتبة من الاكبر للاصغر، افتح اي مجلد لترى ما بداخله").pack(side="right")
        cont = tk.Frame(frame, bg=C["card"])
        cont.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(cont, columns=("size", "pct"), selectmode="extended")
        self.tree.heading("#0", text="المجلد", anchor="w")
        self.tree.heading("size", text="الحجم", anchor="e")
        self.tree.heading("pct", text="النسبة", anchor="w")
        self.tree.column("#0", width=self.px(460), anchor="w")
        self.tree.column("size", width=self.px(120), anchor="e")
        self.tree.column("pct", width=self.px(170), anchor="w")
        self._scrolled(cont, self.tree)
        self.tree.tag_configure("big", foreground=C["red"])
        self.tree.tag_configure("mid", foreground=C["amber"])
        self.tree.bind("<<TreeviewOpen>>", self._on_tree_expand)
        self.tree.bind("<<TreeviewSelect>>", lambda e: self._show_details_for(self._tree_sel_path()))
        self.tree.bind("<Double-1>", lambda e: self._open_selected())

    def _build_files_tab(self):
        frame = self._tab_frame("اكبر الملفات")
        bar = self._toolbar(frame)
        tk.Label(bar, text="اعرض:", bg=C["card"], fg=C["text"], font=(FONT, 10, "bold")).pack(side="right")
        self.filter_var = tk.StringVar(value="الكل")
        fcombo = ttk.Combobox(bar, textvariable=self.filter_var, width=22, state="readonly",
                              values=["الكل", "وسائط", "مستندات", "مضغوط",
                                      "تنفيذي", "نظام او برنامج", "مخلفات", "غير مصنف"])
        fcombo.pack(side="right", padx=6)
        fcombo.bind("<<ComboboxSelected>>", lambda e: self._populate_files())
        self._hint(bar, "الملفات الاكبر من 5 ميكا").pack(side="right", padx=10)

        cont = tk.Frame(frame, bg=C["card"])
        cont.pack(fill="both", expand=True)
        self.files_tree = ttk.Treeview(cont, columns=("size", "cat", "owner", "path"),
                                       show="headings", selectmode="extended")
        for col, txt, w, anc in (("size", "الحجم", 100, "e"), ("cat", "النوع", 150, "w"),
                                 ("owner", "تابع لـ", 220, "w"), ("path", "المسار", 480, "w")):
            self.files_tree.heading(col, text=txt, anchor=anc)
            self.files_tree.column(col, width=self.px(w), anchor=anc)
        self._scrolled(cont, self.files_tree)
        self.files_tree.bind("<<TreeviewSelect>>", lambda e: self._show_details_for(self._files_sel_path()))
        self.files_tree.bind("<Double-1>", lambda e: self._open_selected())

    def _build_dup_tab(self):
        frame = self._tab_frame("الملفات المكررة")
        bar = self._toolbar(frame)
        Btn(bar, "ابحث عن المكررات", self._start_dup_scan, kind="primary").pack(side="right")
        tk.Label(bar, text="الحد الادنى للحجم:", bg=C["card"], fg=C["text"],
                 font=(FONT, 10)).pack(side="right", padx=(12, 4))
        self.dup_min_var = tk.StringVar(value="1 MB")
        ttk.Combobox(bar, textvariable=self.dup_min_var, width=10, state="readonly",
                     values=["100 KB", "500 KB", "1 MB", "5 MB", "10 MB", "50 MB"]).pack(side="right")
        self.dup_stop_btn = Btn(bar, "ايقاف", lambda: self.dup_stop.set(), state="disabled")
        self.dup_stop_btn.pack(side="right", padx=8)
        self.dup_summary = tk.Label(bar, text="احتفظ بنسخة واحدة من كل مجموعة واحذف الباقي",
                                    bg=C["card"], fg=C["muted"], font=(FONT, 10, "bold"))
        self.dup_summary.pack(side="right", padx=10)

        cont = tk.Frame(frame, bg=C["card"])
        cont.pack(fill="both", expand=True)
        self.dup_tree = ttk.Treeview(cont, columns=("size",), selectmode="extended")
        self.dup_tree.heading("#0", text="مجموعات الملفات المتطابقة", anchor="w")
        self.dup_tree.heading("size", text="الحجم", anchor="e")
        self.dup_tree.column("#0", width=self.px(720), anchor="w")
        self.dup_tree.column("size", width=self.px(120), anchor="e")
        self._scrolled(cont, self.dup_tree)
        self.dup_tree.bind("<<TreeviewSelect>>", lambda e: self._show_details_for(self._dup_sel_path()))
        self.dup_tree.bind("<Double-1>", lambda e: self._open_selected())

    def _build_junk_tab(self):
        frame = self._tab_frame("المخلفات")
        bar = self._toolbar(frame)
        self.junk_scan_btn = Btn(bar, "فحص المخلفات", self._scan_junk, kind="primary")
        self.junk_scan_btn.pack(side="right")
        self.junk_bin_btn = Btn(bar, "تفريغ سلة المهملات", self._clean_recycle_bin, kind="navy")
        self.junk_bin_btn.pack(side="left")
        self.junk_summary = tk.Label(bar, text="ملفات مؤقتة وكاش وسلة المهملات، امنة للحذف عادة",
                                     bg=C["card"], fg=C["muted"], font=(FONT, 10, "bold"))
        self.junk_summary.pack(side="right", padx=12)

        cont = tk.Frame(frame, bg=C["card"])
        cont.pack(fill="both", expand=True)
        self.junk_tree = ttk.Treeview(cont, columns=("size", "type", "path"),
                                      show="headings", selectmode="extended")
        for col, txt, w, anc in (("size", "الحجم", 100, "e"), ("type", "النوع", 200, "w"),
                                 ("path", "الموقع", 640, "w")):
            self.junk_tree.heading(col, text=txt, anchor=anc)
            self.junk_tree.column(col, width=self.px(w), anchor=anc)
        self._scrolled(cont, self.junk_tree)
        self.junk_tree.bind("<<TreeviewSelect>>", lambda e: self._show_details_for(self._junk_sel_path()))

    def _build_details_panel(self, parent):
        panel = card(parent, width=self.px(330))
        panel.pack(side="left", fill="y", padx=(0, 10))
        panel.pack_propagate(False)
        tk.Label(panel, text="تفاصيل العنصر", bg=C["head"], fg=C["text"], font=(FONT, 11, "bold"),
                 anchor="e", padx=12, pady=8).pack(fill="x")
        self.guide = self._build_guide(panel)
        self.details = tk.Text(panel, width=38, height=30, wrap="word", font=(FONT, 10),
                               relief="flat", state="disabled", bg=C["card"], fg=C["text"],
                               padx=12, pady=10, cursor="arrow", highlightthickness=0)
        d = self.details
        d.tag_configure("rtl", justify="right")
        d.tag_configure("h", font=(FONT, 13, "bold"), foreground=C["navy"], spacing3=2)
        d.tag_configure("sub", foreground=C["blue"], font=(FONT, 10, "bold"))
        d.tag_configure("label", font=(FONT, 9, "bold"), foreground=C["muted"], spacing1=6)
        d.tag_configure("value", spacing3=2)
        d.tag_configure("path", font=("Consolas", 9), foreground=C["muted"])
        for tag, fg, bg in (("safe", C["green"], C["green_t"]), ("review", C["amber"], C["amber_t"]),
                            ("unsafe", C["red"], C["red_t"])):
            d.tag_configure(tag, foreground=fg, background=bg, font=(FONT, 11, "bold"),
                            spacing1=8, spacing3=8)
        self._clear_details()

    def _build_guide(self, panel):
        # widgets, not Text runs: Tk puts a number tagged apart from Arabic text on the wrong side
        guide = tk.Frame(panel, bg=C["card"], padx=12, pady=12)
        tk.Label(guide, text="كيف تستخدم البرنامج", bg=C["card"], fg=C["navy"],
                 font=(FONT, 13, "bold")).pack(anchor="e", pady=(0, 10))
        for i, line in enumerate((
                "اختر القرص من الاعلى واضغط ابدأ الفحص",
                "تصفح المجلدات واكبر الملفات",
                "اضغط على اي عنصر لتعرف ما هو ولمن يتبع",
                "اللون الاخضر يعني امن للحذف، البرتقالي راجعه، الاحمر لا تحذفه",
                "حدد ما لا تحتاجه واضغط حذف المحدد"), 1):
            row = tk.Frame(guide, bg=C["card"])
            row.pack(fill="x", pady=4)
            d = self.px(22)
            cv = tk.Canvas(row, width=d, height=d, bg=C["card"], highlightthickness=0)
            cv.create_oval(1, 1, d - 1, d - 1, fill=C["blue_t"], outline="")
            cv.create_text(d // 2, d // 2, text=str(i), fill=C["blue"], font=(FONT, 9, "bold"))
            cv.pack(side="right", anchor="n")
            tk.Label(row, text=line, bg=C["card"], fg=C["text"], font=(FONT, 10),
                     wraplength=self.px(250), justify="right").pack(side="right", padx=(0, 8))
        tk.Label(guide, text="زر تسريع الحاسوب ينظف الملفات المؤقتة وسلة المهملات، "
                             "وزر تفريغ السلة يحرر مساحة ما حذفته سابقا",
                 bg=C["green_t"], fg=C["green"], font=(FONT, 10, "bold"), wraplength=self.px(270),
                 justify="right", padx=10, pady=8).pack(fill="x", pady=(16, 0))
        return guide

    def _clear_details(self):
        self.details.pack_forget()
        self.guide.pack(fill="both", expand=True)

    def _show_details_for(self, path):
        if not path or path == "__RECYCLE__":
            return
        info = self._info_cache.get(path)
        if info is None:
            info = fileinfo.analyze(path)
            self._info_cache[path] = info
        self.guide.pack_forget()
        self.details.pack(fill="both", expand=True)
        d = self.details
        d.config(state="normal")
        d.delete("1.0", "end")
        d.insert("end", info["name"] + "\n", "h")
        d.insert("end", info["category_label"] + "\n\n", "sub")

        def row(label, value):
            if value and value != "-":
                d.insert("end", label + "\n", "label")
                d.insert("end", str(value) + "\n", "value")

        if info["is_dir"] and self.result and path in self.result["dir_sizes"]:
            row("حجم المجلد", ar_size(self.result["dir_sizes"][path]))
        elif not info["is_dir"]:
            row("الحجم", ar_size(info["size"]))
        row("النوع", info["type_desc"])
        row("تابع لـ", info["owner"])
        row("الناشر", info["publisher"])
        row("المنتج", info["product"])
        row("الوصف", info["description"])
        row("الاصدار", info["version"])
        row("اخر تعديل", info["modified"])
        row("تاريخ الانشاء", info["created"])
        d.insert("end", "المسار\n", "label")
        d.insert("end", info["path"] + "\n\n", "path")

        if info["owner_note"]:
            row("ملاحظة", info["owner_note"])
            d.insert("end", "\n")

        d.insert("end", info["safe_text"] + "\n", info["safe"])
        d.tag_add("rtl", "1.0", "end")
        d.config(state="disabled")

    def _set_status(self, text, tone="muted"):
        colors = {"muted": C["muted"], "ok": C["green"], "warn": C["amber"],
                  "error": C["red"], "busy": C["blue"]}
        self.status.config(text=text, fg=colors.get(tone, C["muted"]))

    def _refresh_drives(self):
        for w in self.drives_frame.winfo_children():
            w.destroy()
        drives = []
        for letter in string.ascii_uppercase:
            root = f"{letter}:\\"
            if os.path.exists(root):
                try:
                    u = shutil.disk_usage(root)
                    drives.append((root, u.total, u.used, u.free))
                except Exception:
                    continue
        self.drive_combo["values"] = [d[0] for d in drives]
        if drives and not self.drive_var.get():
            self.drive_var.set(drives[0][0])
        per_row = max(1, min(4, len(drives)))
        for c in range(4):
            self.drives_frame.columnconfigure(c, weight=1 if c < per_row else 0,
                                              uniform="drive" if c < per_row else "")
        for i, (root, total, used, free) in enumerate(drives):
            r, c = divmod(i, per_row)
            self._drive_card(root, total, used, free).grid(
                row=r, column=per_row - 1 - c, sticky="ew", padx=4, pady=4)

    def _drive_card(self, root, total, used, free):
        pct = (used / total * 100) if total else 0
        if pct > 90:
            state, fg, tint = "ممتلئ", C["red"], C["red_t"]
        elif pct > 75:
            state, fg, tint = "شبه ممتلئ", C["amber"], C["amber_t"]
        else:
            state, fg, tint = "جيد", C["green"], C["green_t"]
        box = card(self.drives_frame, padx=12, pady=8)
        top = tk.Frame(box, bg=C["card"])
        top.pack(fill="x")
        tk.Label(top, text="القرص", bg=C["card"], fg=C["text"],
                 font=(FONT, 11, "bold")).pack(side="right")
        tk.Label(top, text=root[0], bg=C["card"], fg=C["blue"],
                 font=(FONT, 12, "bold")).pack(side="right", padx=(0, 6))
        tk.Label(top, text=state, bg=tint, fg=fg, font=(FONT, 9, "bold"),
                 padx=10, pady=1).pack(side="left")
        bar = tk.Canvas(box, height=self.px(10), bg=C["gray"], highlightthickness=0)
        bar.pack(fill="x", pady=7)

        def paint(event, cv=bar, p=pct, col=fg):
            cv.delete("all")
            w = event.width
            cv.create_rectangle(w - w * p / 100, 0, w, event.height, fill=col, outline="")

        bar.bind("<Configure>", paint)
        foot = tk.Frame(box, bg=C["card"])
        foot.pack(fill="x")
        tk.Label(foot, text=f"متبقي {ar_size(free)} من {ar_size(total)}",
                 bg=C["card"], fg=C["muted"], font=(FONT, 9)).pack(side="right")
        tk.Label(foot, text=f"{pct:.0f}%", bg=C["card"], fg=fg,
                 font=(FONT, 10, "bold")).pack(side="left")
        return box

    def _speed_up(self):
        root = cleaner.temp_dir()
        if not root:
            messagebox.showerror("تسريع الحاسوب", "تعذر تحديد مجلد الملفات المؤقتة بشكل امن.")
            return
        self.boost_btn.config(state="disabled")
        self.bin_btn.config(state="disabled")
        self.boost_q = queue.Queue()
        self._busy(True)
        self._set_status("جاري حساب حجم الملفات المؤقتة وسلة المهملات", "busy")

        def work():
            size, count = cleaner.measure(root, cleaner.default_skip())
            rb_size, rb_items = cleaner.recycle_bin_info()
            self.boost_q.put(("measured", (root, size, count, rb_size, rb_items)))

        threading.Thread(target=work, daemon=True).start()
        self.after(100, self._poll_boost)

    def _run_clear(self, root, count, rb_size, rb_items):
        self._busy(True)
        self._set_status("جاري التنظيف", "busy")

        def report(deleted, freed):
            self.boost_q.put(("progress", (deleted, freed)))

        def work():
            freed, deleted, skipped = cleaner.clear(root, cleaner.default_skip(), report) if count else (0, 0, 0)
            bin_ok, bin_freed = True, 0
            if rb_items:
                bin_ok = cleaner.empty_recycle_bin()
                bin_freed = max(0, rb_size - cleaner.recycle_bin_info()[0])
            self.boost_q.put(("cleared", (freed, deleted, skipped, bin_freed, bin_ok)))

        threading.Thread(target=work, daemon=True).start()
        self.after(100, self._poll_boost)

    def _end_boost(self):
        self._busy(False)
        self.boost_btn.config(state="normal")
        self.bin_btn.config(state="normal")

    def _poll_boost(self):
        try:
            while True:
                kind, payload = self.boost_q.get_nowait()
                if kind == "measured":
                    self._busy(False)
                    root, size, count, rb_size, rb_items = payload
                    if count == 0 and rb_items == 0:
                        self._end_boost()
                        self._set_status("الملفات المؤقتة وسلة المهملات نظيفة اصلا", "ok")
                        messagebox.showinfo("تسريع الحاسوب", "لا توجد ملفات مؤقتة ولا عناصر بالسلة، جهازك نظيف.")
                        return
                    if not messagebox.askyesno(
                            "تسريع الحاسوب",
                            "سيتم التنظيف نهائيا:\n\n"
                            f"الملفات المؤقتة: {count:,} ملف بحجم {ar_size(size)}\n"
                            f"سلة المهملات: {rb_items:,} عنصر بحجم {ar_size(rb_size)}\n\n"
                            "ما في السلة لا يمكن استرجاعه بعد التفريغ.\n"
                            "الملفات التي تستخدمها برامج مفتوحة الان ستبقى ولن تتاثر.\n\n"
                            "متابعة؟", icon="warning"):
                        self._end_boost()
                        self._set_status("تم الغاء التسريع")
                        return
                    self._run_clear(root, count, rb_size, rb_items)
                    return
                if kind == "progress":
                    deleted, freed = payload
                    self._set_status(f"تم حذف {deleted:,} ملف، حرر {ar_size(freed)}", "busy")
                elif kind == "cleared":
                    self._on_boost_done(*payload)
                    return
        except queue.Empty:
            pass
        self.after(100, self._poll_boost)

    def _on_boost_done(self, freed, deleted, skipped, bin_freed, bin_ok):
        self._end_boost()
        self._refresh_drives()
        self._update_bin_row()
        total = freed + bin_freed
        self._set_status(f"تم التسريع، حرر {ar_size(total)}", "ok" if bin_ok else "warn")
        lines = [f"تم التسريع، حرر {ar_size(total)} بالمجموع.", "",
                 f"الملفات المؤقتة: حذف {deleted:,} ملف، {ar_size(freed)}",
                 f"سلة المهملات: {ar_size(bin_freed)}"]
        if skipped:
            lines += ["", f"بقي {skipped:,} ملف مؤقت لان برامج مفتوحة تستخدمه حاليا، وهذا طبيعي."]
        if not bin_ok:
            lines += ["", "تعذر تفريغ السلة بالكامل، قد تكون بعض الملفات مستخدمة حاليا."]
        messagebox.showinfo("تسريع الحاسوب", "\n".join(lines))

    def _clean_recycle_bin(self):
        size, items = cleaner.recycle_bin_info()
        if items == 0:
            self._set_status("سلة المهملات فارغة اصلا", "ok")
            messagebox.showinfo("سلة المهملات", "سلة المهملات فارغة، لا يوجد شيء لحذفه.")
            return
        if not messagebox.askyesno(
                "تفريغ سلة المهملات",
                f"في السلة {items:,} عنصر بحجم {ar_size(size)}.\n\n"
                "سيتم حذفها نهائيا ولا يمكن استرجاعها بعد التفريغ.\n\nمتابعة؟", icon="warning"):
            return
        self.bin_btn.config(state="disabled")
        self.junk_bin_btn.config(state="disabled")
        self._busy(True)
        self._set_status("جاري تفريغ سلة المهملات", "busy")
        done = queue.Queue()
        threading.Thread(target=lambda: done.put(cleaner.empty_recycle_bin()), daemon=True).start()

        def poll():
            try:
                ok = done.get_nowait()
            except queue.Empty:
                self.after(150, poll)
                return
            self._busy(False)
            self.bin_btn.config(state="normal")
            self.junk_bin_btn.config(state="normal")
            self._refresh_drives()
            left, _ = cleaner.recycle_bin_info()
            self._update_bin_row()
            freed = max(0, size - left)
            if ok:
                msg = f"تم تفريغ سلة المهملات وتحرير {ar_size(freed)}."
                self._set_status(msg, "ok")
                messagebox.showinfo("سلة المهملات", msg)
            else:
                self._set_status("تعذر تفريغ سلة المهملات بالكامل", "error")
                messagebox.showwarning("سلة المهملات",
                                       "تعذر تفريغ السلة بالكامل، قد تكون بعض الملفات مستخدمة حاليا.")

        self.after(150, poll)

    @staticmethod
    def _bin_row_values(size):
        label = "سلة المهملات" if size else "سلة المهملات فارغة"
        return human_size(size), label, "Recycle Bin"

    def _update_bin_row(self):
        size, _ = cleaner.recycle_bin_info()
        for item, row in self._junk_rows.items():
            if row["kind"] == "bin" and self.junk_tree.exists(item):
                row["size"] = size
                self.junk_tree.item(item, values=self._bin_row_values(size))

    def _pick_folder(self):
        folder = filedialog.askdirectory(title="اختر مجلدا للفحص")
        if folder:
            self.drive_var.set(os.path.normpath(folder))

    def _start_scan(self):
        target = self.drive_var.get().strip()
        if not target or not os.path.exists(target):
            messagebox.showwarning("تنبيه", "اختر قرصا او مجلدا صحيحا اولا.")
            return
        self.current_root = target
        self.stop_event.clear()
        self.progress_q = queue.Queue()
        self.result = None
        self._info_cache.clear()
        self.tree.delete(*self.tree.get_children())
        self.files_tree.delete(*self.files_tree.get_children())
        self.scan_btn.config(state="disabled")
        self.stop_btn.config(state="normal")
        self.del_btn.config(state="disabled")
        self._busy(True)
        self._set_status("جاري الفحص، انتظر قليلا", "busy")
        engine = ScanEngine(target, self.progress_q, self.stop_event)
        threading.Thread(target=engine.run, daemon=True).start()
        self.after(100, self._poll_queue)

    def _stop_scan(self):
        self.stop_event.set()
        self._set_status("جاري الايقاف", "warn")

    def _poll_queue(self):
        try:
            while True:
                kind, payload = self.progress_q.get_nowait()
                if kind == "progress":
                    self._set_status(
                        f"جاري الفحص: {payload['file_count']:,} ملف، {ar_size(payload['total_bytes'])}",
                        "busy")
                elif kind == "done":
                    self._on_scan_done(payload); return
                elif kind == "cancelled":
                    self._finish_scan("تم الايقاف", "warn"); return
                elif kind == "error":
                    self._finish_scan("خطأ اثناء الفحص", "error")
                    messagebox.showerror("خطأ", payload); return
        except queue.Empty:
            pass
        self.after(100, self._poll_queue)

    def _finish_scan(self, msg, tone="muted"):
        self._busy(False)
        self.scan_btn.config(state="normal")
        self.stop_btn.config(state="disabled")
        self.del_btn.config(state="normal")
        self._set_status(msg, tone)

    def _on_scan_done(self, payload):
        self.result = payload
        cat = payload.get("cat_bytes", {})
        top_cats = sorted(cat.items(), key=lambda x: x[1], reverse=True)[:1]
        cat_txt = "، ".join(f"{fileinfo._category_label(c)} {ar_size(b)}" for c, b in top_cats)
        self._finish_scan(
            f"اكتمل الفحص: {payload['file_count']:,} ملف بحجم {ar_size(payload['total_bytes'])}، "
            f"اكثرها {cat_txt}", "ok")
        self._populate_tree()
        self._populate_files()

    def _populate_tree(self):
        self.tree.delete(*self.tree.get_children())
        sizes = self.result["dir_sizes"]
        root = self.current_root
        total = sizes.get(root, self.result["total_bytes"]) or 1
        node = self.tree.insert("", "end", text=root, tags=("group",),
                                values=(human_size(sizes.get(root, 0)), self._bar(100)), open=True)
        self._tree_nodes = {node: root}
        self._add_children(node, root, total)

    def _bar(self, pct):
        filled = int(round(pct / 10))
        return "#" * filled + "-" * (10 - filled) + f" {pct:.0f}%"

    def _add_children(self, parent_node, parent_path, grand_total):
        sizes = self.result["dir_sizes"]
        subdirs = []
        try:
            for name in os.listdir(parent_path):
                full = os.path.join(parent_path, name)
                if full in sizes and os.path.isdir(full):
                    subdirs.append((full, sizes[full]))
        except (PermissionError, OSError):
            pass
        subdirs.sort(key=lambda x: x[1], reverse=True)
        for full, sz in subdirs:
            if sz == 0:
                continue
            pct = sz / grand_total * 100 if grand_total else 0
            tags = ("big",) if pct >= 20 else ("mid",) if pct >= 5 else ()
            node = self.tree.insert(parent_node, "end", text=os.path.basename(full) or full,
                                    values=(human_size(sz), self._bar(pct)), tags=tags)
            self._tree_nodes[node] = full
            has_sub = any(os.path.join(full, n) in sizes and sizes[os.path.join(full, n)] > 0
                          for n in self._safe_listdir(full))
            if has_sub:
                self.tree.insert(node, "end", text="...")

    @staticmethod
    def _safe_listdir(path):
        try:
            return os.listdir(path)
        except (PermissionError, OSError):
            return []

    def _on_tree_expand(self, event):
        node = self.tree.focus()
        path = self._tree_nodes.get(node)
        if not path:
            return
        children = self.tree.get_children(node)
        if len(children) == 1 and self.tree.item(children[0], "text") == "...":
            self.tree.delete(children[0])
            total = self.result["dir_sizes"].get(self.current_root, 1) or 1
            self._add_children(node, path, total)

    _FILTER_CAT = {
        "وسائط": "media", "مستندات": "doc", "مضغوط": "archive",
        "تنفيذي": "exec", "نظام او برنامج": "system", "مخلفات": "junk",
        "غير مصنف": "other",
    }

    def _populate_files(self):
        self.files_tree.delete(*self.files_tree.get_children())
        if not self.result:
            return
        flt = self.filter_var.get()
        want_cat = self._FILTER_CAT.get(flt)
        shown = 0
        for path, sz in self.result["big_files"]:
            ext = os.path.splitext(path)[1].lstrip(".").lower()
            d = fileinfo._EXT_MAP.get(ext)
            cat = d[1] if d else "other"
            if want_cat and cat != want_cat:
                continue
            cat_label = fileinfo._category_label(cat)
            owner = self._light_owner(path)
            self.files_tree.insert("", "end", values=(human_size(sz), cat_label, owner, path),
                                   tags=("even",) if shown % 2 else ())
            shown += 1
            if shown >= 800:
                break

    @staticmethod
    def _light_owner(path):
        owner, _ = fileinfo._owner_from_path(path)
        return owner or "-"

    def _start_dup_scan(self):
        target = self.current_root or self.drive_var.get().strip()
        if not target or not os.path.exists(target):
            messagebox.showwarning("تنبيه", "اختر قرصا او مجلدا وافحصه اولا.")
            return
        sizes = {"100 KB": 100*1024, "500 KB": 500*1024, "1 MB": 1024*1024,
                 "5 MB": 5*1024*1024, "10 MB": 10*1024*1024, "50 MB": 50*1024*1024}
        min_size = sizes.get(self.dup_min_var.get(), 1024*1024)
        self.dup_tree.delete(*self.dup_tree.get_children())
        self.dup_stop.clear()
        self.dup_q = queue.Queue()
        self.dup_stop_btn.config(state="normal")
        self.dup_summary.config(text="جاري البحث", fg=C["blue"])
        self._set_status("جاري البحث عن الملفات المكررة", "busy")
        eng = DuplicateEngine(target, min_size, self.dup_q, self.dup_stop)
        threading.Thread(target=eng.run, daemon=True).start()
        self.after(120, self._poll_dup)

    def _poll_dup(self):
        try:
            while True:
                kind, payload = self.dup_q.get_nowait()
                if kind == "dup_progress":
                    self._set_status(payload, "busy")
                elif kind == "dup_done":
                    self._on_dup_done(payload); return
                elif kind == "dup_cancelled":
                    self.dup_stop_btn.config(state="disabled")
                    self.dup_summary.config(text="تم الايقاف", fg=C["amber"])
                    self._set_status("تم ايقاف بحث المكررات", "warn"); return
                elif kind == "dup_error":
                    self.dup_stop_btn.config(state="disabled")
                    messagebox.showerror("خطأ", payload); return
        except queue.Empty:
            pass
        self.after(120, self._poll_dup)

    def _on_dup_done(self, payload):
        self.dup_stop_btn.config(state="disabled")
        self.dup_groups = payload["groups"]
        wasted = payload["wasted"]
        self.dup_tree.delete(*self.dup_tree.get_children())
        for i, g in enumerate(self.dup_groups, 1):
            saving = g["size"] * (g["count"] - 1)
            parent = self.dup_tree.insert(
                "", "end", tags=("group",),
                text=f"مجموعة {i}: {g['count']} نسخ متطابقة، يمكن توفير {ar_size(saving)}",
                values=(human_size(g["size"]),), open=False)
            for p in g["paths"]:
                self.dup_tree.insert(parent, "end", text="   " + p, values=(human_size(g["size"]),))
        self.dup_summary.config(
            text=f"وجد {len(self.dup_groups)} مجموعة مكررة، توفير محتمل {ar_size(wasted)}",
            fg=C["green"] if self.dup_groups else C["muted"])
        self._set_status(f"اكتمل بحث المكررات، يمكن توفير {ar_size(wasted)}", "ok")
        if not self.dup_groups:
            messagebox.showinfo("نتيجة", "لا توجد ملفات مكررة بهذا الحجم.")

    def _junk_candidates(self):
        ex = os.path.expandvars
        return [
            (os.environ.get("TEMP", ""), "ملفات مؤقتة للمستخدم", "clean"),
            (ex(r"%SystemRoot%\Temp"), "ملفات مؤقتة للنظام", "clean"),
            (ex(r"%LOCALAPPDATA%\Temp"), "ملفات مؤقتة", "clean"),
            (ex(r"%LOCALAPPDATA%\Microsoft\Windows\INetCache"), "كاش الانترنت", "clean"),
            (ex(r"%LOCALAPPDATA%\CrashDumps"), "تفريغات الاعطال", "clean"),
            (ex(r"%LOCALAPPDATA%\Google\Chrome\User Data\Default\Cache"), "كاش كروم", "clean"),
            (ex(r"%LOCALAPPDATA%\Microsoft\Edge\User Data\Default\Cache"), "كاش ايدج", "clean"),
            (ex(r"%LOCALAPPDATA%\pip\cache"), "كاش بيب", "clean"),
            (ex(r"%LOCALAPPDATA%\NVIDIA\DXCache"), "كاش انفيديا", "clean"),
            (ex(r"%USERPROFILE%\Downloads"), "التنزيلات راجعها بنفسك", "review"),
        ]

    def _scan_junk(self):
        if self._junk_busy:
            return
        self._junk_busy = True
        self.junk_tree.delete(*self.junk_tree.get_children())
        self._junk_rows = {}
        self.junk_scan_btn.config(state="disabled")
        self._busy(True)
        self._set_status("جاري فحص المخلفات", "busy")
        q = queue.Queue()
        candidates = self._junk_candidates()

        def work():
            seen = set()
            for path, label, kind in candidates:
                if not path:
                    continue
                path = os.path.normpath(path)
                key = os.path.normcase(path)
                if key in seen or not os.path.isdir(path):
                    continue
                seen.add(key)
                size, _ = cleaner.measure(path)
                if size > 0:
                    q.put(("row", (path, label, kind, size)))
            q.put(("row", ("Recycle Bin", "", "bin", cleaner.recycle_bin_info()[0])))
            q.put(("done", None))

        threading.Thread(target=work, daemon=True).start()

        def poll():
            try:
                while True:
                    kind, payload = q.get_nowait()
                    if kind == "row":
                        self._add_junk_row(*payload)
                    else:
                        self._junk_busy = False
                        self._busy(False)
                        self.junk_scan_btn.config(state="normal")
                        total = sum(r["size"] for r in self._junk_rows.values() if r["kind"] != "review")
                        self.junk_summary.config(
                            text=f"اجمالي المخلفات القابلة للتنظيف نحو {ar_size(total)}", fg=C["green"])
                        self._set_status(f"اكتمل فحص المخلفات، نحو {ar_size(total)} قابلة للتحرير", "ok")
                        return
            except queue.Empty:
                pass
            self.after(100, poll)

        self.after(100, poll)

    def _add_junk_row(self, path, label, kind, size):
        if kind == "bin":
            values = self._bin_row_values(size)
        else:
            values = (human_size(size), label, path)
        item = self.junk_tree.insert("", "end", values=values,
                                     tags=("even",) if len(self._junk_rows) % 2 else ())
        self._junk_rows[item] = {"path": path, "kind": kind, "size": size, "label": label}

    def _clean_junk_rows(self, items):
        rows = [self._junk_rows[i] for i in items if i in self._junk_rows]
        if any(r["kind"] == "bin" for r in rows):
            self._clean_recycle_bin()
        review = [r for r in rows if r["kind"] == "review"]
        if review:
            messagebox.showinfo("راجعها بنفسك",
                                "مجلد التنزيلات فيه ملفاتك الشخصية لذلك لا يحذفه البرنامج.\n"
                                "سيتم فتحه لتراجعه وتحذف ما لا تحتاجه بنفسك.")
            open_in_explorer(review[0]["path"])
        targets = [(i, r) for i, r in zip(items, rows) if r["kind"] == "clean"]
        if not targets:
            return
        total = sum(r["size"] for _, r in targets)
        names = "\n".join(f"  {r['label']}" for _, r in targets[:8])
        if not messagebox.askyesno(
                "تنظيف المخلفات",
                f"سيتم حذف محتويات هذه المجلدات نهائيا:\n\n{names}\n\n"
                f"الحجم نحو {ar_size(total)}. المجلدات نفسها تبقى، والملفات المستخدمة حاليا ستبقى.\n\n"
                "متابعة؟", icon="warning"):
            return
        self._busy(True)
        self.junk_scan_btn.config(state="disabled")
        self._set_status("جاري تنظيف المخلفات", "busy")
        q = queue.Queue()

        def work():
            freed = skipped = 0
            for item, r in targets:
                f, _, s = cleaner.clear(r["path"], cleaner.default_skip())
                freed += f
                skipped += s
                q.put(("row", (item, cleaner.measure(r["path"])[0])))
            q.put(("done", (freed, skipped)))

        threading.Thread(target=work, daemon=True).start()

        def poll():
            try:
                while True:
                    kind, payload = q.get_nowait()
                    if kind == "row":
                        item, size = payload
                        if self.junk_tree.exists(item):
                            r = self._junk_rows[item]
                            r["size"] = size
                            self.junk_tree.item(item, values=(human_size(size), r["label"], r["path"]))
                    else:
                        freed, skipped = payload
                        self._busy(False)
                        self.junk_scan_btn.config(state="normal")
                        self._refresh_drives()
                        msg = f"تم تنظيف المخلفات وتحرير {ar_size(freed)}."
                        self._set_status(msg, "ok")
                        if skipped:
                            msg += f"\n\nبقي {skipped:,} ملف لانه مستخدم حاليا او يحتاج صلاحيات مدير."
                        messagebox.showinfo("تنظيف المخلفات", msg)
                        return
            except queue.Empty:
                pass
            self.after(100, poll)

        self.after(100, poll)

    def _tree_sel_path(self):
        sel = self.tree.selection()
        return self._tree_nodes.get(sel[0]) if sel else None

    def _files_sel_path(self):
        sel = self.files_tree.selection()
        if sel:
            vals = self.files_tree.item(sel[0], "values")
            return vals[3] if vals else None
        return None

    def _dup_sel_path(self):
        sel = self.dup_tree.selection()
        if sel:
            txt = self.dup_tree.item(sel[0], "text").strip()
            if txt and not txt.startswith("مجموعة"):
                return txt
        return None

    def _junk_path(self, item):
        row = self._junk_rows.get(item)
        if not row:
            return None
        return "__RECYCLE__" if row["kind"] == "bin" else row["path"]

    def _junk_sel_path(self):
        sel = self.junk_tree.selection()
        return self._junk_path(sel[0]) if sel else None

    def _selected_paths(self):
        tab = self.nb.current
        paths = []
        if tab == 0:
            for n in self.tree.selection():
                p = self._tree_nodes.get(n)
                if p:
                    paths.append(p)
        elif tab == 1:
            for item in self.files_tree.selection():
                vals = self.files_tree.item(item, "values")
                if vals:
                    paths.append(vals[3])
        elif tab == 2:
            for item in self.dup_tree.selection():
                txt = self.dup_tree.item(item, "text").strip()
                if txt and not txt.startswith("مجموعة"):
                    paths.append(txt)
        elif tab == 3:
            for item in self.junk_tree.selection():
                p = self._junk_path(item)
                if p:
                    paths.append(p)
        return paths

    def _open_selected(self):
        paths = self._selected_paths()
        if not paths:
            messagebox.showinfo("معلومة", "اختر عنصرا اولا.")
            return
        p = paths[0]
        if p == "__RECYCLE__":
            os.startfile("shell:RecycleBinFolder")
        else:
            open_in_explorer(p)

    def _delete_selected(self):
        paths = self._selected_paths()
        if not paths:
            messagebox.showinfo("معلومة", "اختر عنصرا او اكثر للحذف.")
            return
        if self.nb.current == 3:
            self._clean_junk_rows(list(self.junk_tree.selection()))
            return
        if "__RECYCLE__" in paths:
            self._clean_recycle_bin()
            paths = [p for p in paths if p != "__RECYCLE__"]
            if not paths:
                return
        blocked = [p for p in paths if is_protected(p)]
        if blocked:
            messagebox.showerror("ممنوع",
                "لا يمكن حذف مجلدات النظام او مجلداتك الاساسية:\n\n" + "\n".join(blocked[:5]))
            paths = [p for p in paths if not is_protected(p)]
            if not paths:
                return
        risky = [p for p in paths if self._is_system_file(p)]
        if risky:
            if not messagebox.askyesno("تحذير",
                    "العناصر التالية تبدو تابعة للنظام او لبرنامج مثبت:\n\n"
                    + "\n".join(risky[:5]) +
                    "\n\nحذفها قد يعطل برنامجا او النظام. الافضل ازالتها من ازالة البرامج.\n\n"
                    "متأكد تريد الاستمرار؟", icon="warning"):
                return
        total = 0
        for p in paths:
            if self.result and p in self.result["dir_sizes"]:
                total += self.result["dir_sizes"][p]
            elif os.path.isfile(p):
                try:
                    total += os.path.getsize(p)
                except OSError:
                    pass
        mode = "سيتم نقلها الى سلة المهملات وتبقى قابلة للاستعادة" if HAS_SEND2TRASH \
            else "سيتم حذفها نهائيا وغير قابلة للاستعادة"
        preview = "\n".join(f"  {p}" for p in paths[:8])
        if len(paths) > 8:
            preview += f"\n  و {len(paths) - 8} عنصر اخر"
        if not messagebox.askyesno("تأكيد الحذف",
                f"عدد العناصر: {len(paths)}\nالحجم التقريبي: {ar_size(total)}\n\n"
                f"{preview}\n\n{mode}\n\nهل انت متأكد؟", icon="warning"):
            return
        errors, removed = [], {}
        for p in paths:
            size = self.result["dir_sizes"].get(p) if self.result else None
            if size is None:
                try:
                    size = os.path.getsize(p) if os.path.isfile(p) else 0
                except OSError:
                    size = 0
            try:
                if HAS_SEND2TRASH:
                    send2trash(os.path.normpath(p))
                else:
                    self._hard_delete(p)
                removed[p] = size
            except Exception as e:
                errors.append(f"{p}: {e}")
        deleted = len(removed)
        self._remove_deleted_from_views(list(removed))
        self._apply_removed_sizes(removed)
        self._refresh_drives()
        msg = f"تم حذف {deleted} عنصر، حرر نحو {ar_size(sum(removed.values()))}."
        if errors:
            msg += f"\nفشل {len(errors)} عنصر، قد تحتاج صلاحيات مدير."
            messagebox.showwarning("اكتمل مع اخطاء", msg + "\n\n" + "\n".join(errors[:5]))
        else:
            messagebox.showinfo("تم", msg)
        self._set_status(msg.split("\n")[0], "warn" if errors else "ok")

    @staticmethod
    def _is_system_file(path):
        low = os.path.normpath(path).lower()
        win = os.environ.get("SystemRoot", r"C:\Windows").lower()
        if low.startswith(win) or "program files" in low:
            if not fileinfo._is_junk_location(path):
                return True
        return False

    @staticmethod
    def _hard_delete(path):
        if os.path.isdir(path):
            shutil.rmtree(path, ignore_errors=False)
        else:
            os.remove(path)

    def _remove_deleted_from_views(self, paths):
        pset = set(os.path.normcase(os.path.normpath(p)) for p in paths)

        def gone(p):
            np = os.path.normcase(os.path.normpath(p))
            return np in pset or any(np.startswith(d.rstrip("\\") + "\\") for d in pset)

        for item in self.files_tree.get_children():
            vals = self.files_tree.item(item, "values")
            if vals and gone(vals[3]):
                self.files_tree.delete(item)
        for parent in self.dup_tree.get_children():
            for child in self.dup_tree.get_children(parent):
                txt = self.dup_tree.item(child, "text").strip()
                if txt and gone(txt):
                    self.dup_tree.delete(child)
        for node, p in list(self._tree_nodes.items()):
            if gone(p):
                try:
                    self.tree.delete(node)
                except tk.TclError:
                    pass
                del self._tree_nodes[node]
        if self.result:
            self.result["big_files"] = [(p, s) for p, s in self.result["big_files"] if not gone(p)]

    def _apply_removed_sizes(self, removed):
        """Subtract deleted sizes from every ancestor folder so the tree stays accurate."""
        if not self.result:
            return
        sizes = self.result["dir_sizes"]
        for path, size in removed.items():
            sizes.pop(path, None)
            parent = os.path.dirname(path)
            while size and parent in sizes:
                sizes[parent] = max(0, sizes[parent] - size)
                up = os.path.dirname(parent)
                if up == parent:
                    break
                parent = up
        total = sizes.get(self.current_root, 0) or 1
        for node, path in self._tree_nodes.items():
            if path in sizes and self.tree.exists(node):
                pct = 100 if path == self.current_root else sizes[path] / total * 100
                self.tree.item(node, values=(human_size(sizes[path]), self._bar(pct)))


def enable_dpi_awareness():
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except (AttributeError, OSError):
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except (AttributeError, OSError):
            pass


def main():
    enable_dpi_awareness()
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("dvlinuxx.Cleanix")
    except Exception:
        pass
    app = App()
    if not HAS_SEND2TRASH:
        app.after(500, lambda: messagebox.showwarning(
            "تنبيه", "مكتبة send2trash غير مثبتة.\nالحذف سيكون نهائيا.\n"
                     "للتثبيت: pip install send2trash"))
    app.mainloop()


if __name__ == "__main__":
    main()
