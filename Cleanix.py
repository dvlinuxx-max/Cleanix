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
    hasSend2trash = True
except ImportError:
    hasSend2trash = False


appVersion = "2.3.0"
siteUrl = "https://mohmadev.com/"
appName = "Cleanix"
repoUrl = "https://github.com/dvlinuxx-max/Cleanix"
contactEmail = "dvlinuxx@gmail.com"

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


def humanSize(num):
    for unit in ("B", "KB", "MB", "GB", "TB", "PB"):
        if abs(num) < 1024.0:
            return f"{num:,.1f} {unit}"
        num /= 1024.0
    return f"{num:,.1f} EB"


arUnits = ("بايت", "كيلوبايت", "ميغابايت", "غيغابايت", "تيرابايت")


def arSize(num):
    """Size with Arabic units; Tk misorders Latin units inside Arabic sentences."""
    for unit in arUnits:
        if abs(num) < 1024.0:
            return f"{num:,.1f} {unit}"
        num /= 1024.0
    return f"{num * 1024:,.1f} {arUnits[-1]}"


def openInExplorer(path):
    try:
        if os.path.isdir(path):
            os.startfile(path)
        else:
            subprocess.run(["explorer", "/select,", os.path.normpath(path)])
    except Exception as e:
        messagebox.showerror("خطأ", f"تعذر فتح المسار:\n{e}")


userFolders = ("Desktop", "Documents", "Downloads", "Pictures", "Videos", "Music", "AppData",
                "OneDrive", "Favorites", "Contacts", "Links", "Saved Games", "Searches", "3D Objects")


def protectedPaths():
    env = os.environ
    items = [r"C:\Windows", r"C:\Program Files", r"C:\Program Files (x86)", r"C:\ProgramData",
             r"C:\Users"]
    items += [env.get(k, "") for k in ("SystemRoot", "ProgramFiles", "ProgramFiles(x86)", "ProgramData",
                                       "PUBLIC", "USERPROFILE", "LOCALAPPDATA", "APPDATA", "OneDrive",
                                       "TEMP", "TMP")]
    for base in (env.get("USERPROFILE", ""), env.get("OneDrive", "")):
        if base:
            items += [os.path.join(base, name) for name in userFolders]
    if env.get("USERPROFILE"):
        items += [os.path.join(env["USERPROFILE"], "AppData", n) for n in ("Local", "LocalLow", "Roaming")]
    return {os.path.normcase(os.path.normpath(p)) for p in items if p}


PROTECTED = protectedPaths()


def isProtected(path):
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
        self.baseBg, self.hover, fg = self.KINDS[kind]
        super().__init__(master, text=text, command=command, bg=self.baseBg, fg=fg,
                         activebackground=self.hover, activeforeground=fg,
                         disabledforeground=C["disabled"], relief="flat", bd=0,
                         highlightthickness=0, cursor="hand2", padx=padx, pady=pady,
                         font=(FONT, size, "bold"))
        self.bind("<Enter>", self.enter)
        self.bind("<Leave>", self.leave)
        self.configure(state=state)

    def configure(self, cnf=None, **kw):
        if "state" in kw:
            on = kw["state"] == "normal"
            kw["bg"] = self.baseBg if on else C["gray"]
            kw["cursor"] = "hand2" if on else "arrow"
        return super().configure(cnf, **kw)

    config = configure

    def enter(self, _):
        if str(self["state"]) == "normal":
            tk.Button.configure(self, bg=self.hover)

    def leave(self, _):
        if str(self["state"]) == "normal":
            tk.Button.configure(self, bg=self.baseBg)


class TabView(tk.Frame):
    """Right-aligned tab bar; ttk.Notebook cannot place tabs on the right."""

    def __init__(self, master, onChange=None):
        super().__init__(master, bg=C["bg"])
        self.onChange = onChange
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
        tab.bind("<Enter>", lambda e, i=idx: self.hover(i, True))
        tab.bind("<Leave>", lambda e, i=idx: self.hover(i, False))
        self.tabs.append(tab)
        self.frames.append(frame)
        self.paintTab(idx)

    def select(self, idx):
        if idx == self.current:
            return
        if self.current >= 0:
            self.frames[self.current].pack_forget()
        self.current = idx
        self.frames[idx].pack(fill="both", expand=True)
        for i in range(len(self.tabs)):
            self.paintTab(i)
        if self.onChange:
            self.onChange()

    def paintTab(self, i):
        if i == self.current:
            self.tabs[i].config(bg=C["card"], fg=C["blue"])
        else:
            self.tabs[i].config(bg=C["gray"], fg=C["muted"])

    def hover(self, i, inside):
        if i != self.current:
            self.tabs[i].config(bg=C["gray_h"] if inside else C["gray"])


def card(parent, **kw):
    return tk.Frame(parent, bg=C["card"], highlightbackground=C["line"], highlightthickness=1, **kw)


class ScanEngine:
    def __init__(self, rootPath, progressQ, stopEvent):
        self.rootPath = rootPath
        self.q = progressQ
        self.stop = stopEvent
        self.totalBytes = 0
        self.fileCount = 0
        self.dirSizes = {}
        self.bigFiles = []
        self.catBytes = {}

    def run(self):
        try:
            self.scan(self.rootPath)
        except Exception as e:
            self.q.put(("error", str(e)))
            return
        if self.stop.is_set():
            self.q.put(("cancelled", None))
            return
        self.bigFiles.sort(key=lambda x: x[1], reverse=True)
        self.q.put(("done", {
            "dir_sizes": self.dirSizes,
            "big_files": self.bigFiles[:1000],
            "total_bytes": self.totalBytes,
            "file_count": self.fileCount,
            "cat_bytes": self.catBytes,
        }))

    def quickCat(self, name):
        ext = os.path.splitext(name)[1].lstrip(".").lower()
        d = fileinfo.extMap.get(ext)
        return d[1] if d else "other"

    def scan(self, path):
        stack = [path]
        direct = {}
        children = {}
        lastReport = time.time()
        allDirs = []
        while stack:
            if self.stop.is_set():
                return
            cur = stack.pop()
            allDirs.append(cur)
            direct.setdefault(cur, 0)
            children.setdefault(cur, [])
            try:
                with os.scandir(cur) as it:
                    for entry in it:
                        if self.stop.is_set():
                            return
                        try:
                            if cleaner.isLink(entry):
                                continue
                            if entry.is_dir(follow_symlinks=False):
                                children[cur].append(entry.path)
                                stack.append(entry.path)
                            elif entry.is_file(follow_symlinks=False):
                                sz = entry.stat(follow_symlinks=False).st_size
                                direct[cur] += sz
                                self.totalBytes += sz
                                self.fileCount += 1
                                cat = self.quickCat(entry.name)
                                self.catBytes[cat] = self.catBytes.get(cat, 0) + sz
                                if sz >= 5 * 1024 * 1024:
                                    self.bigFiles.append((entry.path, sz))
                        except (PermissionError, OSError):
                            continue
            except (PermissionError, OSError):
                continue
            now = time.time()
            if now - lastReport > 0.15:
                lastReport = now
                self.q.put(("progress", {
                    "current": cur, "total_bytes": self.totalBytes,
                    "file_count": self.fileCount,
                }))
        if self.stop.is_set():
            return
        sizes = dict(direct)
        for d in sorted(allDirs, key=lambda p: p.count(os.sep), reverse=True):
            total = direct.get(d, 0)
            for ch in children.get(d, []):
                total += sizes.get(ch, 0)
            sizes[d] = total
        self.dirSizes = sizes


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.scale = max(1.0, self.winfo_fpixels("1i") / 96.0)
        self.tk.call("tk", "scaling", self.scale * 96 / 72)
        self.title(appName)
        wantW, wantH = self.px(1320), self.px(800)
        w = min(wantW, self.winfo_screenwidth() - 40)
        h = min(wantH, self.winfo_screenheight() - 80)
        self.geometry(f"{w}x{h}")
        self.minsize(min(self.px(1080), w), min(self.px(660), h))
        if w < wantW or h < wantH:
            self.state("zoomed")
        self.configure(bg=C["bg"])
        try:
            self.iconbitmap(default=resource("icon.ico"))
        except tk.TclError:
            pass
        try:
            size = 88 if self.scale >= 1.75 else 66 if self.scale >= 1.25 else 44
            self.logoImage = tk.PhotoImage(file=resource(f"logo_{size}.png"))
        except tk.TclError:
            self.logoImage = None

        self.stopEvent = threading.Event()
        self.progressQ = queue.Queue()
        self.dupStop = threading.Event()
        self.dupQ = queue.Queue()
        self.boostQ = queue.Queue()
        self.result = None
        self.currentRoot = None
        self.dupGroups = []
        self.infoCache = {}
        self.treeNodes = {}
        self.junkRows = {}
        self.junkBusy = False

        self.buildStyle()
        self.buildWidgets()
        self.refreshDrives()

    def px(self, n):
        return int(round(n * self.scale))

    def buildStyle(self):
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

    def buildWidgets(self):
        self.buildHeader()
        self.buildSteps()

        self.drivesFrame = tk.Frame(self, bg=C["bg"])
        self.drivesFrame.pack(fill="x", padx=14, pady=(10, 4))

        self.buildCredits()
        self.buildBottom()

        main = tk.Frame(self, bg=C["bg"])
        main.pack(fill="both", expand=True, padx=14, pady=6)

        self.buildDetailsPanel(main)

        self.nb = TabView(main, onChange=self.clearDetails)
        self.nb.pack(side="right", fill="both", expand=True)
        self.buildTreeTab()
        self.buildFilesTab()
        self.buildDupTab()
        self.buildJunkTab()
        self.nb.select(0)

    def buildCredits(self):
        strip = tk.Frame(self, bg=C["navy"], padx=14, pady=6)
        strip.pack(fill="x", side="bottom")
        tk.Label(strip, text=f"v{appVersion}", bg=C["navy"], fg=C["navy_sub"],
                 font=(FONT, 9)).pack(side="right")
        tk.Label(strip, text=appName, bg=C["navy"], fg="#FFFFFF",
                 font=(FONT, 10, "bold")).pack(side="right", padx=(0, 8))
        Btn(strip, "License", self.showLicense, kind="navy", size=9, padx=16, pady=3).pack(side="left")
        self.updateBox = tk.Frame(strip, bg=C["navy"])
        self.after(2000, self.checkUpdates)

    def checkUpdates(self):
        q = queue.Queue()
        threading.Thread(target=lambda: q.put(updater.newerRelease(appVersion)), daemon=True).start()

        def poll():
            try:
                rel = q.get_nowait()
            except queue.Empty:
                self.after(500, poll)
                return
            if rel:
                self.showUpdate(*rel)

        self.after(500, poll)

    def manualUpdateCheck(self, win, btn, result):
        def show(text, fg):
            for w in result.winfo_children():
                w.destroy()
            tk.Label(result, text=text, bg=C["card"], fg=fg, font=(FONT, 10, "bold")).pack(side="right")

        btn.config(state="disabled")
        show("جاري الفحص", C["blue"])
        q = queue.Queue()
        threading.Thread(target=lambda: q.put(updater.check(appVersion)), daemon=True).start()

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
                Btn(result, "تنزيل", lambda: webbrowser.open(url or repoUrl + "/releases/latest"),
                    kind="success", size=9, padx=12, pady=3).pack(side="right", padx=(0, 10))
                self.showUpdate(tag, url)
            elif state == "latest":
                show("لديك احدث اصدار", C["green"])
            elif state == "none":
                show("لا توجد اصدارات منشورة بعد", C["muted"])
            else:
                show("تعذر الاتصال، تاكد من الانترنت", C["red"])

        win.after(200, poll)

    def showUpdate(self, tag, url):
        box = self.updateBox
        if box.winfo_children():
            return
        Btn(box, "يتوفر اصدار جديد", lambda: webbrowser.open(url or repoUrl + "/releases/latest"),
            kind="success", size=9, padx=14, pady=3).pack(side="left")
        tk.Label(box, text=tag, bg=C["navy"], fg="#8FE3AE", font=(FONT, 9, "bold")).pack(side="left", padx=8)
        box.pack(side="left", padx=12)

    def showLicense(self):
        if getattr(self, "licenseWin", None) and self.licenseWin.winfo_exists():
            self.licenseWin.lift()
            return
        win = tk.Toplevel(self)
        self.licenseWin = win
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
        if self.logoImage:
            tk.Label(head, image=self.logoImage, bg=C["navy"]).pack(side="right", padx=(12, 0))
        titles = tk.Frame(head, bg=C["navy"])
        titles.pack(side="right")
        tk.Label(titles, text=appName, bg=C["navy"], fg="#FFFFFF",
                 font=(FONT, 15, "bold")).pack(anchor="e")
        tk.Label(titles, text=f"v{appVersion}", bg=C["navy"], fg=C["navy_sub"],
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

        row("الموقع", siteUrl.split("//")[1].rstrip("/"), siteUrl)
        row("البريد", contactEmail, "mailto:" + contactEmail)
        row("المصدر", repoUrl.split("//")[1], repoUrl)
        row("الاصدار", appVersion)

        upd = tk.Frame(body, bg=C["card"])
        upd.pack(fill="x", pady=(10, 0))
        updBtn = Btn(upd, "فحص التحديثات", None, kind="primary", size=9, padx=14, pady=4)
        updBtn.pack(side="right")
        updResult = tk.Frame(upd, bg=C["card"])
        updResult.pack(side="right", padx=(0, 12))
        updBtn.config(command=lambda: self.manualUpdateCheck(win, updBtn, updResult))

        lic = tk.Frame(body, bg=C["green_t"], padx=12, pady=8)
        lic.pack(fill="x", pady=(16, 0))
        tk.Label(lic, text="يعمل البرنامج تحت رخصة", bg=C["green_t"], fg=C["green"],
                 font=(FONT, 10, "bold")).pack(side="right")
        licLink = tk.Label(lic, text="MIT License", bg=C["green_t"], fg=C["green"], cursor="hand2",
                            font=(FONT, 10, "bold", "underline"))
        licLink.pack(side="right", padx=(0, 4))
        licLink.bind("<Button-1>", lambda e: webbrowser.open(repoUrl + "/blob/main/LICENSE"))

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

    def buildBottom(self):
        bottom = tk.Frame(self, bg=C["card"], highlightbackground=C["line"], highlightthickness=1)
        bottom.pack(fill="x", side="bottom")
        inner = tk.Frame(bottom, bg=C["card"], padx=14, pady=8)
        inner.pack(fill="x")
        mode = "سلة المهملات" if hasSend2trash else "حذف نهائي"
        self.delBtn = Btn(inner, f"حذف المحدد ({mode})", self.deleteSelected, kind="danger")
        self.delBtn.pack(side="left")
        self.openBtn = Btn(inner, "فتح الموقع", self.openSelected)
        self.openBtn.pack(side="left", padx=8)
        self.status = tk.Label(inner, text="جاهز، اختر القرص واضغط ابدأ الفحص", bg=C["card"],
                               fg=C["muted"], font=(FONT, 10), anchor="e")
        self.progress = ttk.Progressbar(inner, mode="indeterminate", length=180)
        self.status.pack(side="right", fill="x", expand=True, padx=(12, 0))

    def busy(self, on):
        if on:
            if not self.progress.winfo_ismapped():
                self.progress.pack(side="right", after=self.status)
            self.progress.start(12)
        else:
            self.progress.stop()
            self.progress.pack_forget()

    def buildHeader(self):
        header = tk.Frame(self, bg=C["navy"], padx=18, pady=12)
        header.pack(fill="x")
        brand = tk.Frame(header, bg=C["navy"])
        brand.pack(side="right")
        if self.logoImage:
            tk.Label(brand, image=self.logoImage, bg=C["navy"]).pack(side="right", padx=(12, 0))
        titles = tk.Frame(brand, bg=C["navy"])
        titles.pack(side="right")
        tk.Label(titles, text=appName, font=(FONT, 16, "bold"),
                 fg="#FFFFFF", bg=C["navy"]).pack(anchor="e")
        tk.Label(titles, text="اعرف ما الذي يستهلك مساحة جهازك ونظفه بامان",
                 font=(FONT, 10), fg=C["navy_sub"], bg=C["navy"]).pack(anchor="e")

        actions = tk.Frame(header, bg=C["navy"])
        actions.pack(side="left")
        self.boostBtn = self.headerAction(actions, "تسريع الحاسوب", "يمسح الملفات المؤقتة",
                                             self.speedUp, "success")
        self.binBtn = self.headerAction(actions, "تفريغ سلة المهملات", "يحرر مساحة الملفات المحذوفة",
                                           self.cleanRecycleBin, "navy")

    def headerAction(self, parent, text, caption, command, kind):
        box = tk.Frame(parent, bg=C["navy"])
        box.pack(side="left", padx=(0, 14))
        btn = Btn(box, text, command, kind=kind, size=12, padx=24, pady=9)
        btn.pack(fill="x")
        tk.Label(box, text=caption, font=(FONT, 9), fg=C["navy_sub"], bg=C["navy"]).pack(pady=(4, 0))
        return btn

    def stepBadge(self, parent, number, text):
        box = tk.Frame(parent, bg=C["card"])
        d = self.px(24)
        cv = tk.Canvas(box, width=d, height=d, bg=C["card"], highlightthickness=0)
        cv.create_oval(1, 1, d - 1, d - 1, fill=C["blue"], outline="")
        cv.create_text(d // 2, d // 2, text=str(number), fill="#FFFFFF", font=(FONT, 10, "bold"))
        cv.pack(side="right")
        tk.Label(box, text=text, bg=C["card"], fg=C["text"],
                 font=(FONT, 10, "bold")).pack(side="right", padx=(6, 8))
        return box

    def buildSteps(self):
        wrap = card(self)
        wrap.pack(fill="x", padx=14, pady=(12, 0))
        row = tk.Frame(wrap, bg=C["card"], padx=12, pady=10)
        row.pack(fill="x")

        self.stepBadge(row, 1, "اختر القرص").pack(side="right")
        self.driveVar = tk.StringVar()
        self.driveCombo = ttk.Combobox(row, textvariable=self.driveVar, width=16, state="readonly")
        self.driveCombo.pack(side="right", padx=(0, 6))
        Btn(row, "او مجلد محدد", self.pickFolder).pack(side="right", padx=(0, 4))

        tk.Frame(row, bg=C["line"], width=1).pack(side="right", fill="y", padx=16)

        self.stepBadge(row, 2, "افحص").pack(side="right")
        self.scanBtn = Btn(row, "ابدأ الفحص", self.startScan, kind="primary", padx=20)
        self.scanBtn.pack(side="right", padx=(0, 6))
        self.stopBtn = Btn(row, "ايقاف", self.stopScan, state="disabled")
        self.stopBtn.pack(side="right")

        tk.Frame(row, bg=C["line"], width=1).pack(side="right", fill="y", padx=16)

        self.stepBadge(row, 3, "راجع النتائج واحذف ما لا تحتاجه").pack(side="right")

        Btn(row, "تحديث الاقراص", self.refreshDrives).pack(side="left")

    def tabFrame(self, title):
        frame = tk.Frame(self.nb.body, bg=C["card"])
        self.nb.add(frame, title)
        return frame

    def toolbar(self, parent):
        bar = tk.Frame(parent, bg=C["card"], padx=10, pady=8)
        bar.pack(fill="x")
        return bar

    def hint(self, parent, text, **kw):
        return tk.Label(parent, text=text, bg=C["card"], fg=C["muted"], font=(FONT, 10), **kw)

    @staticmethod
    def stripeTags(tree):
        tree.tag_configure("even", background=C["stripe"])
        tree.tag_configure("group", background=C["blue_t"], font=(FONT, 10, "bold"))

    def scrolled(self, parent, tree):
        vsb = ttk.Scrollbar(parent, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        tree.pack(side="left", fill="both", expand=True)
        self.stripeTags(tree)

    def buildTreeTab(self):
        frame = self.tabFrame("شجرة المجلدات")
        bar = self.toolbar(frame)
        self.hint(bar, "المجلدات مرتبة من الاكبر للاصغر، افتح اي مجلد لترى ما بداخله").pack(side="right")
        cont = tk.Frame(frame, bg=C["card"])
        cont.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(cont, columns=("size", "pct"), selectmode="extended")
        self.tree.heading("#0", text="المجلد", anchor="w")
        self.tree.heading("size", text="الحجم", anchor="e")
        self.tree.heading("pct", text="النسبة", anchor="w")
        self.tree.column("#0", width=self.px(460), anchor="w")
        self.tree.column("size", width=self.px(120), anchor="e")
        self.tree.column("pct", width=self.px(170), anchor="w")
        self.scrolled(cont, self.tree)
        self.tree.tag_configure("big", foreground=C["red"])
        self.tree.tag_configure("mid", foreground=C["amber"])
        self.tree.bind("<<TreeviewOpen>>", self.onTreeExpand)
        self.tree.bind("<<TreeviewSelect>>", lambda e: self.showDetailsFor(self.treeSelPath()))
        self.tree.bind("<Double-1>", lambda e: self.openSelected())

    def buildFilesTab(self):
        frame = self.tabFrame("اكبر الملفات")
        bar = self.toolbar(frame)
        tk.Label(bar, text="اعرض:", bg=C["card"], fg=C["text"], font=(FONT, 10, "bold")).pack(side="right")
        self.filterVar = tk.StringVar(value="الكل")
        fcombo = ttk.Combobox(bar, textvariable=self.filterVar, width=22, state="readonly",
                              values=["الكل", "وسائط", "مستندات", "مضغوط",
                                      "تنفيذي", "نظام او برنامج", "مخلفات", "غير مصنف"])
        fcombo.pack(side="right", padx=6)
        fcombo.bind("<<ComboboxSelected>>", lambda e: self.populateFiles())
        self.hint(bar, "الملفات الاكبر من 5 ميكا").pack(side="right", padx=10)

        cont = tk.Frame(frame, bg=C["card"])
        cont.pack(fill="both", expand=True)
        self.filesTree = ttk.Treeview(cont, columns=("size", "cat", "owner", "path"),
                                       show="headings", selectmode="extended")
        for col, txt, w, anc in (("size", "الحجم", 100, "e"), ("cat", "النوع", 150, "w"),
                                 ("owner", "تابع لـ", 220, "w"), ("path", "المسار", 480, "w")):
            self.filesTree.heading(col, text=txt, anchor=anc)
            self.filesTree.column(col, width=self.px(w), anchor=anc)
        self.scrolled(cont, self.filesTree)
        self.filesTree.bind("<<TreeviewSelect>>", lambda e: self.showDetailsFor(self.filesSelPath()))
        self.filesTree.bind("<Double-1>", lambda e: self.openSelected())

    def buildDupTab(self):
        frame = self.tabFrame("الملفات المكررة")
        bar = self.toolbar(frame)
        Btn(bar, "ابحث عن المكررات", self.startDupScan, kind="primary").pack(side="right")
        tk.Label(bar, text="الحد الادنى للحجم:", bg=C["card"], fg=C["text"],
                 font=(FONT, 10)).pack(side="right", padx=(12, 4))
        self.dupMinVar = tk.StringVar(value="1 MB")
        ttk.Combobox(bar, textvariable=self.dupMinVar, width=10, state="readonly",
                     values=["100 KB", "500 KB", "1 MB", "5 MB", "10 MB", "50 MB"]).pack(side="right")
        self.dupStopBtn = Btn(bar, "ايقاف", lambda: self.dupStop.set(), state="disabled")
        self.dupStopBtn.pack(side="right", padx=8)
        self.dupSummary = tk.Label(bar, text="احتفظ بنسخة واحدة من كل مجموعة واحذف الباقي",
                                    bg=C["card"], fg=C["muted"], font=(FONT, 10, "bold"))
        self.dupSummary.pack(side="right", padx=10)

        cont = tk.Frame(frame, bg=C["card"])
        cont.pack(fill="both", expand=True)
        self.dupTree = ttk.Treeview(cont, columns=("size",), selectmode="extended")
        self.dupTree.heading("#0", text="مجموعات الملفات المتطابقة", anchor="w")
        self.dupTree.heading("size", text="الحجم", anchor="e")
        self.dupTree.column("#0", width=self.px(720), anchor="w")
        self.dupTree.column("size", width=self.px(120), anchor="e")
        self.scrolled(cont, self.dupTree)
        self.dupTree.bind("<<TreeviewSelect>>", lambda e: self.showDetailsFor(self.dupSelPath()))
        self.dupTree.bind("<Double-1>", lambda e: self.openSelected())

    def buildJunkTab(self):
        frame = self.tabFrame("المخلفات")
        bar = self.toolbar(frame)
        self.junkScanBtn = Btn(bar, "فحص المخلفات", self.scanJunk, kind="primary")
        self.junkScanBtn.pack(side="right")
        self.junkCleanBtn = Btn(bar, "تنظيف المخلفات", self.cleanAllJunk, kind="success", state="disabled")
        self.junkCleanBtn.pack(side="right", padx=(8, 0))
        self.junkBinBtn = Btn(bar, "تفريغ سلة المهملات", self.cleanRecycleBin, kind="navy")
        self.junkBinBtn.pack(side="left")
        self.junkSummary = tk.Label(bar, text="ملفات مؤقتة وكاش وسلة المهملات، امنة للحذف عادة",
                                     bg=C["card"], fg=C["muted"], font=(FONT, 10, "bold"))
        self.junkSummary.pack(side="right", padx=12)

        cont = tk.Frame(frame, bg=C["card"])
        cont.pack(fill="both", expand=True)
        self.junkTree = ttk.Treeview(cont, columns=("size", "type", "path"),
                                      show="headings", selectmode="extended")
        for col, txt, w, anc in (("size", "الحجم", 100, "e"), ("type", "النوع", 200, "w"),
                                 ("path", "الموقع", 640, "w")):
            self.junkTree.heading(col, text=txt, anchor=anc)
            self.junkTree.column(col, width=self.px(w), anchor=anc)
        self.scrolled(cont, self.junkTree)
        self.junkTree.bind("<<TreeviewSelect>>", lambda e: self.showDetailsFor(self.junkSelPath()))

    def buildDetailsPanel(self, parent):
        panel = card(parent, width=self.px(330))
        panel.pack(side="left", fill="y", padx=(0, 10))
        panel.pack_propagate(False)
        tk.Label(panel, text="تفاصيل العنصر", bg=C["head"], fg=C["text"], font=(FONT, 11, "bold"),
                 anchor="e", padx=12, pady=8).pack(fill="x")
        self.guide = self.buildGuide(panel)
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
        self.clearDetails()

    def buildGuide(self, panel):
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

    def clearDetails(self):
        self.details.pack_forget()
        self.guide.pack(fill="both", expand=True)

    def showDetailsFor(self, path):
        if not path or path == "__RECYCLE__":
            return
        info = self.infoCache.get(path)
        if info is None:
            info = fileinfo.analyze(path)
            self.infoCache[path] = info
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
            row("حجم المجلد", arSize(self.result["dir_sizes"][path]))
        elif not info["is_dir"]:
            row("الحجم", arSize(info["size"]))
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

    def setStatus(self, text, tone="muted"):
        colors = {"muted": C["muted"], "ok": C["green"], "warn": C["amber"],
                  "error": C["red"], "busy": C["blue"]}
        self.status.config(text=text, fg=colors.get(tone, C["muted"]))

    def refreshDrives(self):
        for w in self.drivesFrame.winfo_children():
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
        self.driveCombo["values"] = [d[0] for d in drives]
        if drives and not self.driveVar.get():
            self.driveVar.set(drives[0][0])
        perRow = max(1, min(4, len(drives)))
        for c in range(4):
            self.drivesFrame.columnconfigure(c, weight=1 if c < perRow else 0,
                                              uniform="drive" if c < perRow else "")
        for i, (root, total, used, free) in enumerate(drives):
            r, c = divmod(i, perRow)
            self.driveCard(root, total, used, free).grid(
                row=r, column=perRow - 1 - c, sticky="ew", padx=4, pady=4)

    def driveCard(self, root, total, used, free):
        pct = (used / total * 100) if total else 0
        if pct > 90:
            state, fg, tint = "ممتلئ", C["red"], C["red_t"]
        elif pct > 75:
            state, fg, tint = "شبه ممتلئ", C["amber"], C["amber_t"]
        else:
            state, fg, tint = "جيد", C["green"], C["green_t"]
        box = card(self.drivesFrame, padx=12, pady=8)
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
        tk.Label(foot, text=f"متبقي {arSize(free)} من {arSize(total)}",
                 bg=C["card"], fg=C["muted"], font=(FONT, 9)).pack(side="right")
        tk.Label(foot, text=f"{pct:.0f}%", bg=C["card"], fg=fg,
                 font=(FONT, 10, "bold")).pack(side="left")
        return box

    def speedUp(self):
        root = cleaner.tempDir()
        if not root:
            messagebox.showerror("تسريع الحاسوب", "تعذر تحديد مجلد الملفات المؤقتة بشكل امن.")
            return
        self.boostBtn.config(state="disabled")
        self.binBtn.config(state="disabled")
        self.boostQ = queue.Queue()
        self.busy(True)
        self.setStatus("جاري حساب حجم الملفات المؤقتة وسلة المهملات", "busy")

        def work():
            size, count = cleaner.measure(root, cleaner.defaultSkip())
            rbSize, rbItems = cleaner.recycleBinInfo()
            self.boostQ.put(("measured", (root, size, count, rbSize, rbItems)))

        threading.Thread(target=work, daemon=True).start()
        self.after(100, self.pollBoost)

    def runClear(self, root, count, rbSize, rbItems):
        self.busy(True)
        self.setStatus("جاري التنظيف", "busy")

        def report(deleted, freed):
            self.boostQ.put(("progress", (deleted, freed)))

        def work():
            freed, deleted, skipped = cleaner.clear(root, cleaner.defaultSkip(), report) if count else (0, 0, 0)
            binOk, binFreed = True, 0
            if rbItems:
                binOk = cleaner.emptyRecycleBin()
                binFreed = max(0, rbSize - cleaner.recycleBinInfo()[0])
            self.boostQ.put(("cleared", (freed, deleted, skipped, binFreed, binOk)))

        threading.Thread(target=work, daemon=True).start()
        self.after(100, self.pollBoost)

    def endBoost(self):
        self.busy(False)
        self.boostBtn.config(state="normal")
        self.binBtn.config(state="normal")

    def pollBoost(self):
        try:
            while True:
                kind, payload = self.boostQ.get_nowait()
                if kind == "measured":
                    self.busy(False)
                    root, size, count, rbSize, rbItems = payload
                    if count == 0 and rbItems == 0:
                        self.endBoost()
                        self.setStatus("الملفات المؤقتة وسلة المهملات نظيفة اصلا", "ok")
                        messagebox.showinfo("تسريع الحاسوب", "لا توجد ملفات مؤقتة ولا عناصر بالسلة، جهازك نظيف.")
                        return
                    if not messagebox.askyesno(
                            "تسريع الحاسوب",
                            "سيتم التنظيف نهائيا:\n\n"
                            f"الملفات المؤقتة: {count:,} ملف بحجم {arSize(size)}\n"
                            f"سلة المهملات: {rbItems:,} عنصر بحجم {arSize(rbSize)}\n\n"
                            "ما في السلة لا يمكن استرجاعه بعد التفريغ.\n"
                            "الملفات التي تستخدمها برامج مفتوحة الان ستبقى ولن تتاثر.\n\n"
                            "متابعة؟", icon="warning"):
                        self.endBoost()
                        self.setStatus("تم الغاء التسريع")
                        return
                    self.runClear(root, count, rbSize, rbItems)
                    return
                if kind == "progress":
                    deleted, freed = payload
                    self.setStatus(f"تم حذف {deleted:,} ملف، حرر {arSize(freed)}", "busy")
                elif kind == "cleared":
                    self.onBoostDone(*payload)
                    return
        except queue.Empty:
            pass
        self.after(100, self.pollBoost)

    def onBoostDone(self, freed, deleted, skipped, binFreed, binOk):
        self.endBoost()
        self.refreshDrives()
        self.updateBinRow()
        total = freed + binFreed
        self.setStatus(f"تم التسريع، حرر {arSize(total)}", "ok" if binOk else "warn")
        lines = [f"تم التسريع، حرر {arSize(total)} بالمجموع.", "",
                 f"الملفات المؤقتة: حذف {deleted:,} ملف، {arSize(freed)}",
                 f"سلة المهملات: {arSize(binFreed)}"]
        if skipped:
            lines += ["", f"بقي {skipped:,} ملف مؤقت لان برامج مفتوحة تستخدمه حاليا، وهذا طبيعي."]
        if not binOk:
            lines += ["", "تعذر تفريغ السلة بالكامل، قد تكون بعض الملفات مستخدمة حاليا."]
        messagebox.showinfo("تسريع الحاسوب", "\n".join(lines))

    def cleanRecycleBin(self):
        size, items = cleaner.recycleBinInfo()
        if items == 0:
            self.setStatus("سلة المهملات فارغة اصلا", "ok")
            messagebox.showinfo("سلة المهملات", "سلة المهملات فارغة، لا يوجد شيء لحذفه.")
            return
        if not messagebox.askyesno(
                "تفريغ سلة المهملات",
                f"في السلة {items:,} عنصر بحجم {arSize(size)}.\n\n"
                "سيتم حذفها نهائيا ولا يمكن استرجاعها بعد التفريغ.\n\nمتابعة؟", icon="warning"):
            return
        self.binBtn.config(state="disabled")
        self.junkBinBtn.config(state="disabled")
        self.busy(True)
        self.setStatus("جاري تفريغ سلة المهملات", "busy")
        done = queue.Queue()
        threading.Thread(target=lambda: done.put(cleaner.emptyRecycleBin()), daemon=True).start()

        def poll():
            try:
                ok = done.get_nowait()
            except queue.Empty:
                self.after(150, poll)
                return
            self.busy(False)
            self.binBtn.config(state="normal")
            self.junkBinBtn.config(state="normal")
            self.refreshDrives()
            left, _ = cleaner.recycleBinInfo()
            self.updateBinRow()
            freed = max(0, size - left)
            if ok:
                msg = f"تم تفريغ سلة المهملات وتحرير {arSize(freed)}."
                self.setStatus(msg, "ok")
                messagebox.showinfo("سلة المهملات", msg)
            else:
                self.setStatus("تعذر تفريغ سلة المهملات بالكامل", "error")
                messagebox.showwarning("سلة المهملات",
                                       "تعذر تفريغ السلة بالكامل، قد تكون بعض الملفات مستخدمة حاليا.")

        self.after(150, poll)

    @staticmethod
    def binRowValues(size):
        label = "سلة المهملات" if size else "سلة المهملات فارغة"
        return humanSize(size), label, "Recycle Bin"

    def updateBinRow(self):
        size, _ = cleaner.recycleBinInfo()
        for item, row in self.junkRows.items():
            if row["kind"] == "bin" and self.junkTree.exists(item):
                row["size"] = size
                self.junkTree.item(item, values=self.binRowValues(size))

    def pickFolder(self):
        folder = filedialog.askdirectory(title="اختر مجلدا للفحص")
        if folder:
            self.driveVar.set(os.path.normpath(folder))

    def startScan(self):
        target = self.driveVar.get().strip()
        if not target or not os.path.exists(target):
            messagebox.showwarning("تنبيه", "اختر قرصا او مجلدا صحيحا اولا.")
            return
        self.currentRoot = target
        self.stopEvent.clear()
        self.progressQ = queue.Queue()
        self.result = None
        self.infoCache.clear()
        self.tree.delete(*self.tree.get_children())
        self.filesTree.delete(*self.filesTree.get_children())
        self.scanBtn.config(state="disabled")
        self.stopBtn.config(state="normal")
        self.delBtn.config(state="disabled")
        self.busy(True)
        self.setStatus("جاري الفحص، انتظر قليلا", "busy")
        engine = ScanEngine(target, self.progressQ, self.stopEvent)
        threading.Thread(target=engine.run, daemon=True).start()
        self.after(100, self.pollQueue)

    def stopScan(self):
        self.stopEvent.set()
        self.setStatus("جاري الايقاف", "warn")

    def pollQueue(self):
        try:
            while True:
                kind, payload = self.progressQ.get_nowait()
                if kind == "progress":
                    self.setStatus(
                        f"جاري الفحص: {payload['file_count']:,} ملف، {arSize(payload['total_bytes'])}",
                        "busy")
                elif kind == "done":
                    self.onScanDone(payload); return
                elif kind == "cancelled":
                    self.finishScan("تم الايقاف", "warn"); return
                elif kind == "error":
                    self.finishScan("خطأ اثناء الفحص", "error")
                    messagebox.showerror("خطأ", payload); return
        except queue.Empty:
            pass
        self.after(100, self.pollQueue)

    def finishScan(self, msg, tone="muted"):
        self.busy(False)
        self.scanBtn.config(state="normal")
        self.stopBtn.config(state="disabled")
        self.delBtn.config(state="normal")
        self.setStatus(msg, tone)

    def onScanDone(self, payload):
        self.result = payload
        cat = payload.get("cat_bytes", {})
        topCats = sorted(cat.items(), key=lambda x: x[1], reverse=True)[:1]
        catTxt = "، ".join(f"{fileinfo.categoryLabel(c)} {arSize(b)}" for c, b in topCats)
        self.finishScan(
            f"اكتمل الفحص: {payload['file_count']:,} ملف بحجم {arSize(payload['total_bytes'])}، "
            f"اكثرها {catTxt}", "ok")
        self.populateTree()
        self.populateFiles()

    def populateTree(self):
        self.tree.delete(*self.tree.get_children())
        sizes = self.result["dir_sizes"]
        root = self.currentRoot
        total = sizes.get(root, self.result["total_bytes"]) or 1
        node = self.tree.insert("", "end", text=root, tags=("group",),
                                values=(humanSize(sizes.get(root, 0)), self.barText(100)), open=True)
        self.treeNodes = {node: root}
        self.addChildren(node, root, total)

    def barText(self, pct):
        filled = int(round(pct / 10))
        return "#" * filled + "-" * (10 - filled) + f" {pct:.0f}%"

    def addChildren(self, parentNode, parentPath, grandTotal):
        sizes = self.result["dir_sizes"]
        subdirs = []
        try:
            for name in os.listdir(parentPath):
                full = os.path.join(parentPath, name)
                if full in sizes and os.path.isdir(full):
                    subdirs.append((full, sizes[full]))
        except (PermissionError, OSError):
            pass
        subdirs.sort(key=lambda x: x[1], reverse=True)
        for full, sz in subdirs:
            if sz == 0:
                continue
            pct = sz / grandTotal * 100 if grandTotal else 0
            tags = ("big",) if pct >= 20 else ("mid",) if pct >= 5 else ()
            node = self.tree.insert(parentNode, "end", text=os.path.basename(full) or full,
                                    values=(humanSize(sz), self.barText(pct)), tags=tags)
            self.treeNodes[node] = full
            hasSub = any(os.path.join(full, n) in sizes and sizes[os.path.join(full, n)] > 0
                          for n in self.safeListdir(full))
            if hasSub:
                self.tree.insert(node, "end", text="...")

    @staticmethod
    def safeListdir(path):
        try:
            return os.listdir(path)
        except (PermissionError, OSError):
            return []

    def onTreeExpand(self, event):
        node = self.tree.focus()
        path = self.treeNodes.get(node)
        if not path:
            return
        children = self.tree.get_children(node)
        if len(children) == 1 and self.tree.item(children[0], "text") == "...":
            self.tree.delete(children[0])
            total = self.result["dir_sizes"].get(self.currentRoot, 1) or 1
            self.addChildren(node, path, total)

    filterCat = {
        "وسائط": "media", "مستندات": "doc", "مضغوط": "archive",
        "تنفيذي": "exec", "نظام او برنامج": "system", "مخلفات": "junk",
        "غير مصنف": "other",
    }

    def populateFiles(self):
        self.filesTree.delete(*self.filesTree.get_children())
        if not self.result:
            return
        flt = self.filterVar.get()
        wantCat = self.filterCat.get(flt)
        shown = 0
        for path, sz in self.result["big_files"]:
            ext = os.path.splitext(path)[1].lstrip(".").lower()
            d = fileinfo.extMap.get(ext)
            cat = d[1] if d else "other"
            if wantCat and cat != wantCat:
                continue
            catLabel = fileinfo.categoryLabel(cat)
            owner = self.lightOwner(path)
            self.filesTree.insert("", "end", values=(humanSize(sz), catLabel, owner, path),
                                   tags=("even",) if shown % 2 else ())
            shown += 1
            if shown >= 800:
                break

    @staticmethod
    def lightOwner(path):
        owner, _ = fileinfo.ownerFromPath(path)
        return owner or "-"

    def startDupScan(self):
        target = self.currentRoot or self.driveVar.get().strip()
        if not target or not os.path.exists(target):
            messagebox.showwarning("تنبيه", "اختر قرصا او مجلدا وافحصه اولا.")
            return
        sizes = {"100 KB": 100*1024, "500 KB": 500*1024, "1 MB": 1024*1024,
                 "5 MB": 5*1024*1024, "10 MB": 10*1024*1024, "50 MB": 50*1024*1024}
        minSize = sizes.get(self.dupMinVar.get(), 1024*1024)
        self.dupTree.delete(*self.dupTree.get_children())
        self.dupStop.clear()
        self.dupQ = queue.Queue()
        self.dupStopBtn.config(state="normal")
        self.dupSummary.config(text="جاري البحث", fg=C["blue"])
        self.setStatus("جاري البحث عن الملفات المكررة", "busy")
        eng = DuplicateEngine(target, minSize, self.dupQ, self.dupStop)
        threading.Thread(target=eng.run, daemon=True).start()
        self.after(120, self.pollDup)

    def pollDup(self):
        try:
            while True:
                kind, payload = self.dupQ.get_nowait()
                if kind == "dup_progress":
                    self.setStatus(payload, "busy")
                elif kind == "dup_done":
                    self.onDupDone(payload); return
                elif kind == "dup_cancelled":
                    self.dupStopBtn.config(state="disabled")
                    self.dupSummary.config(text="تم الايقاف", fg=C["amber"])
                    self.setStatus("تم ايقاف بحث المكررات", "warn"); return
                elif kind == "dup_error":
                    self.dupStopBtn.config(state="disabled")
                    messagebox.showerror("خطأ", payload); return
        except queue.Empty:
            pass
        self.after(120, self.pollDup)

    def onDupDone(self, payload):
        self.dupStopBtn.config(state="disabled")
        self.dupGroups = payload["groups"]
        wasted = payload["wasted"]
        self.dupTree.delete(*self.dupTree.get_children())
        for i, g in enumerate(self.dupGroups, 1):
            saving = g["size"] * (g["count"] - 1)
            parent = self.dupTree.insert(
                "", "end", tags=("group",),
                text=f"مجموعة {i}: {g['count']} نسخ متطابقة، يمكن توفير {arSize(saving)}",
                values=(humanSize(g["size"]),), open=False)
            for p in g["paths"]:
                self.dupTree.insert(parent, "end", text="   " + p, values=(humanSize(g["size"]),))
        self.dupSummary.config(
            text=f"وجد {len(self.dupGroups)} مجموعة مكررة، توفير محتمل {arSize(wasted)}",
            fg=C["green"] if self.dupGroups else C["muted"])
        self.setStatus(f"اكتمل بحث المكررات، يمكن توفير {arSize(wasted)}", "ok")
        if not self.dupGroups:
            messagebox.showinfo("نتيجة", "لا توجد ملفات مكررة بهذا الحجم.")

    def junkCandidates(self):
        ex = os.path.expandvars
        return [
            (os.environ.get("TEMP", ""), "ملفات مؤقتة للمستخدم", "clean"),
            (ex(r"%SystemRoot%\Temp"), "ملفات مؤقتة للنظام", "clean"),
            (ex(r"%LOCALAPPDATA%\Temp"), "ملفات مؤقتة", "clean"),
            (ex(r"%LOCALAPPDATA%\Microsoft\Windows\INetCache"), "كاش الانترنت", "clean"),
            (ex(r"%LOCALAPPDATA%\CrashDumps"), "تفريغات الاعطال", "clean"),
        ] + self.appCacheCandidates() + [
            (ex(r"%LOCALAPPDATA%\pip\cache"), "كاش بيب", "clean"),
            (ex(r"%LOCALAPPDATA%\NVIDIA\DXCache"), "كاش انفيديا DirectX", "clean"),
            (ex(r"%LOCALAPPDATA%\NVIDIA\GLCache"), "كاش انفيديا OpenGL", "clean"),
            (ex(r"%USERPROFILE%\AppData\LocalLow\NVIDIA\PerDriverVersion\DXCache"), "كاش انفيديا DirectX", "clean"),
            (ex(r"%USERPROFILE%\AppData\LocalLow\NVIDIA\PerDriverVersion\GLCache"), "كاش انفيديا OpenGL", "clean"),
            (ex(r"%APPDATA%\NVIDIA\ComputeCache"), "كاش انفيديا للحوسبة", "clean"),
            (ex(r"%LOCALAPPDATA%\AMD\DxCache"), "كاش AMD DirectX 11", "clean"),
            (ex(r"%LOCALAPPDATA%\AMD\DxcCache"), "كاش AMD DirectX 12", "clean"),
            (ex(r"%LOCALAPPDATA%\AMD\VkCache"), "كاش AMD Vulkan", "clean"),
            (ex(r"%LOCALAPPDATA%\AMD\GLCache"), "كاش AMD OpenGL", "clean"),
            (ex(r"%USERPROFILE%\AppData\LocalLow\Intel\ShaderCache"), "كاش انتل", "clean"),
            (ex(r"%LOCALAPPDATA%\D3DSCache"), "كاش DirectX", "clean"),
        ] + [(p, "كاش ستيم للالعاب", "clean") for p in cleaner.steamShaderDirs()] + [
            (ex(r"%USERPROFILE%\Downloads"), "التنزيلات راجعها بنفسك", "review"),
        ]

    appCaches = (
        ("كروم", r"%LOCALAPPDATA%\Google\Chrome\User Data"),
        ("ايدج", r"%LOCALAPPDATA%\Microsoft\Edge\User Data"),
        ("بريف", r"%LOCALAPPDATA%\BraveSoftware\Brave-Browser\User Data"),
        ("فيفالدي", r"%LOCALAPPDATA%\Vivaldi\User Data"),
        ("اوبرا", r"%LOCALAPPDATA%\Opera Software\Opera Stable"),
        ("اوبرا GX", r"%LOCALAPPDATA%\Opera Software\Opera GX Stable"),
        ("ديسكورد", r"%APPDATA%\discord"),
        ("تيمز", r"%APPDATA%\Microsoft\Teams"),
        ("تيمز", r"%LOCALAPPDATA%\Packages\MSTeams_8wekyb3d8bbwe\LocalCache\Microsoft\MSTeams\EBWebView"),
        ("سلاك", r"%APPDATA%\Slack"),
        ("سبوتيفاي", r"%LOCALAPPDATA%\Spotify\Browser"),
        ("VS Code", r"%APPDATA%\Code"),
    )
    webCacheLabels = {"Cache": "كاش", "Code Cache": "كاش الكود", "GPUCache": "كاش الرسوميات"}

    def appCacheCandidates(self):
        rows = []
        for app, root in self.appCaches:
            for path, profile, name in cleaner.webCacheDirs(os.path.expandvars(root)):
                label = f"{app} - {self.webCacheLabels[name]}"
                if profile and profile != "Default":
                    label += f" ({profile})"
                rows.append((path, label, "clean"))
        for path, profile in cleaner.firefoxCacheDirs():
            rows.append((path, f"فايرفوكس - كاش ({profile})", "clean"))
        return rows

    def scanJunk(self):
        if self.junkBusy:
            return
        self.junkBusy = True
        self.junkTree.delete(*self.junkTree.get_children())
        self.junkRows = {}
        self.junkButtons(False)
        self.busy(True)
        self.setStatus("جاري فحص المخلفات", "busy")
        q = queue.Queue()
        candidates = self.junkCandidates()

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
            q.put(("row", ("Recycle Bin", "", "bin", cleaner.recycleBinInfo()[0])))
            q.put(("done", None))

        threading.Thread(target=work, daemon=True).start()

        def poll():
            try:
                while True:
                    kind, payload = q.get_nowait()
                    if kind == "row":
                        self.addJunkRow(*payload)
                    else:
                        self.junkBusy = False
                        self.busy(False)
                        self.junkButtons(True)
                        total = sum(r["size"] for r in self.junkRows.values() if r["kind"] != "review")
                        self.junkSummary.config(
                            text=f"اجمالي المخلفات القابلة للتنظيف نحو {arSize(total)}", fg=C["green"])
                        self.setStatus(f"اكتمل فحص المخلفات، نحو {arSize(total)} قابلة للتحرير", "ok")
                        return
            except queue.Empty:
                pass
            self.after(100, poll)

        self.after(100, poll)

    def addJunkRow(self, path, label, kind, size):
        if kind == "bin":
            values = self.binRowValues(size)
        else:
            values = (humanSize(size), label, path)
        item = self.junkTree.insert("", "end", values=values,
                                     tags=("even",) if len(self.junkRows) % 2 else ())
        self.junkRows[item] = {"path": path, "kind": kind, "size": size, "label": label}

    def junkButtons(self, enabled):
        self.junkScanBtn.config(state="normal" if enabled else "disabled")
        self.junkCleanBtn.config(state="normal" if enabled and self.cleanableJunk() else "disabled")

    def cleanableJunk(self):
        return [i for i, r in self.junkRows.items() if r["kind"] == "clean" and r["size"] > 0]

    def cleanAllJunk(self):
        items = self.cleanableJunk()
        if not items:
            messagebox.showinfo("تنظيف المخلفات", "لا توجد مخلفات للتنظيف، اضغط فحص المخلفات اولا.")
            return
        self.cleanJunkRows(items)

    def cleanJunkRows(self, items):
        rows = [self.junkRows[i] for i in items if i in self.junkRows]
        if any(r["kind"] == "bin" for r in rows):
            self.cleanRecycleBin()
        review = [r for r in rows if r["kind"] == "review"]
        if review:
            messagebox.showinfo("راجعها بنفسك",
                                "مجلد التنزيلات فيه ملفاتك الشخصية لذلك لا يحذفه البرنامج.\n"
                                "سيتم فتحه لتراجعه وتحذف ما لا تحتاجه بنفسك.")
            openInExplorer(review[0]["path"])
        targets = [(i, r) for i, r in zip(items, rows) if r["kind"] == "clean"]
        if not targets:
            return
        total = sum(r["size"] for _, r in targets)
        names = "\n".join(f"  {r['label']}" for _, r in targets[:8])
        if len(targets) > 8:
            names += f"\n  و {len(targets) - 8} غيرها"
        if not messagebox.askyesno(
                "تنظيف المخلفات",
                f"سيتم حذف محتويات هذه المجلدات نهائيا:\n\n{names}\n\n"
                f"الحجم نحو {arSize(total)}. المجلدات نفسها تبقى، والملفات المستخدمة حاليا ستبقى.\n\n"
                "متابعة؟", icon="warning"):
            return
        self.busy(True)
        self.junkButtons(False)
        self.setStatus("جاري تنظيف المخلفات", "busy")
        q = queue.Queue()

        def work():
            freed = skipped = 0
            for item, r in targets:
                f, _, s = cleaner.clear(r["path"], cleaner.defaultSkip())
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
                        if self.junkTree.exists(item):
                            r = self.junkRows[item]
                            r["size"] = size
                            self.junkTree.item(item, values=(humanSize(size), r["label"], r["path"]))
                    else:
                        freed, skipped = payload
                        self.busy(False)
                        self.junkButtons(True)
                        self.refreshDrives()
                        msg = f"تم تنظيف المخلفات وتحرير {arSize(freed)}."
                        self.setStatus(msg, "ok")
                        if skipped:
                            msg += f"\n\nبقي {skipped:,} ملف لانه مستخدم حاليا او يحتاج صلاحيات مدير."
                        messagebox.showinfo("تنظيف المخلفات", msg)
                        return
            except queue.Empty:
                pass
            self.after(100, poll)

        self.after(100, poll)

    def treeSelPath(self):
        sel = self.tree.selection()
        return self.treeNodes.get(sel[0]) if sel else None

    def filesSelPath(self):
        sel = self.filesTree.selection()
        if sel:
            vals = self.filesTree.item(sel[0], "values")
            return vals[3] if vals else None
        return None

    def dupSelPath(self):
        sel = self.dupTree.selection()
        if sel:
            txt = self.dupTree.item(sel[0], "text").strip()
            if txt and not txt.startswith("مجموعة"):
                return txt
        return None

    def junkPath(self, item):
        row = self.junkRows.get(item)
        if not row:
            return None
        return "__RECYCLE__" if row["kind"] == "bin" else row["path"]

    def junkSelPath(self):
        sel = self.junkTree.selection()
        return self.junkPath(sel[0]) if sel else None

    def selectedPaths(self):
        tab = self.nb.current
        paths = []
        if tab == 0:
            for n in self.tree.selection():
                p = self.treeNodes.get(n)
                if p:
                    paths.append(p)
        elif tab == 1:
            for item in self.filesTree.selection():
                vals = self.filesTree.item(item, "values")
                if vals:
                    paths.append(vals[3])
        elif tab == 2:
            for item in self.dupTree.selection():
                txt = self.dupTree.item(item, "text").strip()
                if txt and not txt.startswith("مجموعة"):
                    paths.append(txt)
        elif tab == 3:
            for item in self.junkTree.selection():
                p = self.junkPath(item)
                if p:
                    paths.append(p)
        return paths

    def openSelected(self):
        paths = self.selectedPaths()
        if not paths:
            messagebox.showinfo("معلومة", "اختر عنصرا اولا.")
            return
        p = paths[0]
        if p == "__RECYCLE__":
            os.startfile("shell:RecycleBinFolder")
        else:
            openInExplorer(p)

    def deleteSelected(self):
        paths = self.selectedPaths()
        if not paths:
            messagebox.showinfo("معلومة", "اختر عنصرا او اكثر للحذف.")
            return
        if self.nb.current == 3:
            self.cleanJunkRows(list(self.junkTree.selection()))
            return
        if "__RECYCLE__" in paths:
            self.cleanRecycleBin()
            paths = [p for p in paths if p != "__RECYCLE__"]
            if not paths:
                return
        blocked = [p for p in paths if isProtected(p)]
        if blocked:
            messagebox.showerror("ممنوع",
                "لا يمكن حذف مجلدات النظام او مجلداتك الاساسية:\n\n" + "\n".join(blocked[:5]))
            paths = [p for p in paths if not isProtected(p)]
            if not paths:
                return
        risky = [p for p in paths if self.isSystemFile(p)]
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
        mode = "سيتم نقلها الى سلة المهملات وتبقى قابلة للاستعادة" if hasSend2trash\
            else "سيتم حذفها نهائيا وغير قابلة للاستعادة"
        preview = "\n".join(f"  {p}" for p in paths[:8])
        if len(paths) > 8:
            preview += f"\n  و {len(paths) - 8} عنصر اخر"
        if not messagebox.askyesno("تأكيد الحذف",
                f"عدد العناصر: {len(paths)}\nالحجم التقريبي: {arSize(total)}\n\n"
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
                if hasSend2trash:
                    send2trash(os.path.normpath(p))
                else:
                    self.hardDelete(p)
                removed[p] = size
            except Exception as e:
                errors.append(f"{p}: {e}")
        deleted = len(removed)
        self.removeDeletedFromViews(list(removed))
        self.applyRemovedSizes(removed)
        self.refreshDrives()
        msg = f"تم حذف {deleted} عنصر، حرر نحو {arSize(sum(removed.values()))}."
        if errors:
            msg += f"\nفشل {len(errors)} عنصر، قد تحتاج صلاحيات مدير."
            messagebox.showwarning("اكتمل مع اخطاء", msg + "\n\n" + "\n".join(errors[:5]))
        else:
            messagebox.showinfo("تم", msg)
        self.setStatus(msg.split("\n")[0], "warn" if errors else "ok")

    @staticmethod
    def isSystemFile(path):
        low = os.path.normpath(path).lower()
        win = os.environ.get("SystemRoot", r"C:\Windows").lower()
        if low.startswith(win) or "program files" in low:
            if not fileinfo.isJunkLocation(path):
                return True
        return False

    @staticmethod
    def hardDelete(path):
        if os.path.isdir(path):
            shutil.rmtree(path, ignore_errors=False)
        else:
            os.remove(path)

    def removeDeletedFromViews(self, paths):
        pset = set(os.path.normcase(os.path.normpath(p)) for p in paths)

        def gone(p):
            np = os.path.normcase(os.path.normpath(p))
            return np in pset or any(np.startswith(d.rstrip("\\") + "\\") for d in pset)

        for item in self.filesTree.get_children():
            vals = self.filesTree.item(item, "values")
            if vals and gone(vals[3]):
                self.filesTree.delete(item)
        for parent in self.dupTree.get_children():
            for child in self.dupTree.get_children(parent):
                txt = self.dupTree.item(child, "text").strip()
                if txt and gone(txt):
                    self.dupTree.delete(child)
        for node, p in list(self.treeNodes.items()):
            if gone(p):
                try:
                    self.tree.delete(node)
                except tk.TclError:
                    pass
                del self.treeNodes[node]
        if self.result:
            self.result["big_files"] = [(p, s) for p, s in self.result["big_files"] if not gone(p)]

    def applyRemovedSizes(self, removed):
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
        total = sizes.get(self.currentRoot, 0) or 1
        for node, path in self.treeNodes.items():
            if path in sizes and self.tree.exists(node):
                pct = 100 if path == self.currentRoot else sizes[path] / total * 100
                self.tree.item(node, values=(humanSize(sizes[path]), self.barText(pct)))


def enableDpiAwareness():
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except (AttributeError, OSError):
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except (AttributeError, OSError):
            pass


def main():
    enableDpiAwareness()
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("dvlinuxx.Cleanix")
    except Exception:
        pass
    app = App()
    if not hasSend2trash:
        app.after(500, lambda: messagebox.showwarning(
            "تنبيه", "مكتبة send2trash غير مثبتة.\nالحذف سيكون نهائيا.\n"
                     "للتثبيت: pip install send2trash"))
    app.mainloop()


if __name__ == "__main__":
    main()
