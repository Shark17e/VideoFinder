"""Video Finder: cerca un video per titolo su YouTube, Dailymotion e su tutti i siti
supportati da yt-dlp, con anteprima integrata (mpv) e download video/audio.
"""

import ctypes
import html as html_mod
import json
import os
import queue
import re
import sys
import threading
import tkinter as tk
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from itertools import zip_longest
from tkinter import filedialog, messagebox
from urllib.parse import urlsplit

import ttkbootstrap as tb
from ttkbootstrap.constants import BOTH, END, LEFT, RIGHT, W, X
import yt_dlp
from ddgs import DDGS
from yt_dlp.extractor import gen_extractor_classes

APP_NAME = "Video Finder"
APP_DIR = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else os.path.dirname(os.path.abspath(__file__))
LIB_DIR = getattr(sys, "_MEIPASS", os.path.join(APP_DIR, "vendor"))
os.environ["PATH"] = LIB_DIR + os.pathsep + os.environ.get("PATH", "")

try:
    import mpv
    MPV_READY, MPV_ERROR = True, ""
except Exception as exc:  # il programma resta usabile senza player
    mpv, MPV_READY, MPV_ERROR = None, False, str(exc)

user32 = ctypes.windll.user32 if sys.platform == "win32" else None
if user32:
    user32.CreateWindowExW.restype = ctypes.c_void_p

WS_CHILD = 0x40000000
WS_VISIBLE = 0x10000000
WS_CLIPCHILDREN = 0x02000000

TOP_SITES = (
    "youtube.com", "dailymotion.com", "vimeo.com", "tiktok.com", "facebook.com",
    "instagram.com", "x.com", "soundcloud.com", "bilibili.com", "nicovideo.jp",
    "archive.org", "rumble.com", "odysee.com", "twitch.tv",
)
NATIVE_SEARCH = {
    "youtube.com": "ytsearch",
    "soundcloud.com": "scsearch",
    "bilibili.com": "bilisearch",
    "nicovideo.jp": "nicosearch",
    "rokfin.com": "rkfnsearch",
}
QUALITIES = ("Migliore", "2160p", "1440p", "1080p", "720p", "480p", "360p", "240p")
AUDIO_QUALITIES = ("320 kbps", "256 kbps", "192 kbps", "128 kbps", "96 kbps")
PUBLIC_SUFFIXES = {"co", "com", "net", "org", "gov", "ac", "edu", "or", "ne", "go"}

_sites = None
_sites_lock = threading.Lock()


def hhmmss(seconds):
    if not seconds:
        return ""
    seconds = int(seconds)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def clock(seconds):
    seconds = max(0, int(seconds or 0))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def registrable(host):
    host = (host or "").lower().strip(".").removeprefix("www.")
    parts = host.split(".")
    if len(parts) >= 3 and len(parts[-1]) == 2 and parts[-2] in PUBLIC_SUFFIXES:
        return ".".join(parts[-3:])
    return ".".join(parts[-2:])


def build_sites():
    """Elenco dei siti supportati da yt-dlp, ricavato dai suoi extractor."""
    sites = set(TOP_SITES)
    for extractor in gen_extractor_classes():
        for test in getattr(extractor, "_TESTS", None) or []:
            if not isinstance(test, dict) or not isinstance(test.get("url"), str):
                continue
            host = (urlsplit(test["url"]).hostname or "").lower().removeprefix("www.")
            if host and "." in host and re.fullmatch(r"[a-z0-9.-]+\.[a-z]{2,}", host):
                sites.add(registrable(host))
    return sorted(sites)


def get_sites():
    global _sites
    with _sites_lock:
        if _sites is None:
            _sites = build_sites()
        return _sites


def ffmpeg_path():
    candidate = os.path.join(getattr(sys, "_MEIPASS", APP_DIR), "ffmpeg.exe")
    return candidate if os.path.isfile(candidate) else None


def search_youtube(query, limit=12):
    opts = {"quiet": True, "no_warnings": True, "extract_flat": True, "playlistend": limit}
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(f"ytsearch{limit}:{query}", download=False)
    results = []
    for entry in info.get("entries") or []:
        vid = entry.get("id")
        results.append({
            "title": entry.get("title") or vid,
            "duration": hhmmss(entry.get("duration")),
            "author": entry.get("channel") or entry.get("uploader") or "",
            "url": entry.get("url") or f"https://www.youtube.com/watch?v={vid}",
            "platform": "youtube.com",
        })
    return results


def search_dailymotion(query, limit=12):
    fields = "id,title,duration,owner.screenname,url"
    qs = urllib.parse.urlencode({"search": query, "fields": fields, "limit": limit})
    with urllib.request.urlopen("https://api.dailymotion.com/videos?" + qs, timeout=20) as resp:
        data = json.load(resp)
    results = []
    for video in data.get("list", []):
        owner = video.get("owner")
        author = owner.get("screenname", "") if isinstance(owner, dict) else ""
        results.append({
            "title": video.get("title") or video.get("id"),
            "duration": hhmmss(video.get("duration")),
            "author": author or video.get("owner.screenname", ""),
            "url": video.get("url") or f"https://www.dailymotion.com/video/{video['id']}",
            "platform": "dailymotion.com",
        })
    return results


def search_native(key, query, platform, limit=12):
    opts = {"quiet": True, "no_warnings": True, "extract_flat": True, "playlistend": limit}
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(f"{key}{limit}:{query}", download=False)
    results = []
    for entry in info.get("entries") or []:
        url = entry.get("url") or entry.get("webpage_url") or ""
        if not url.startswith("http"):
            continue
        results.append({
            "title": entry.get("title") or url,
            "duration": hhmmss(entry.get("duration")),
            "author": entry.get("channel") or entry.get("uploader") or "",
            "url": url,
            "platform": platform,
        })
    return results


def web_search(query, domain=None, limit=15):
    """Ricerca web (DuckDuckGo/Google tramite ddgs) limitata ai siti supportati."""
    text = f"site:{domain} {query}" if domain else query
    backends = ("google", "auto", "yahoo") if domain is None else ("auto", "google", "yahoo")
    sites = get_sites()
    results, seen = [], set()
    for backend in backends:
        try:
            with DDGS() as ddgs:
                rows = ddgs.text(text, max_results=limit * 2, backend=backend)
        except Exception:
            rows = []
        for row in rows:
            url = row.get("href") or ""
            if not url.startswith("http") or url in seen:
                continue
            host = (urlsplit(url).hostname or "").lower().removeprefix("www.")
            if not host:
                continue
            if domain:
                if not (host == domain or host.endswith("." + domain)):
                    continue
            else:
                if not any(host == site or host.endswith("." + site) for site in sites):
                    continue
                if host.endswith("youtube.com") or host.endswith("dailymotion.com"):
                    continue
            seen.add(url)
            results.append({
                "title": html_mod.unescape(row.get("title") or url),
                "duration": "",
                "author": "",
                "url": url,
                "platform": registrable(host),
            })
        if results:
            break
    return results[:limit]


def search_all(query, per=8):
    jobs = [(search_youtube, (query, per)), (search_dailymotion, (query, per)), (web_search, (query, None, 12))]
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = [pool.submit(fn, *args) for fn, args in jobs]
    groups, errors = [], []
    for future in futures:
        try:
            groups.append(future.result())
        except Exception as exc:
            errors.append(exc)
            groups.append([])
    if len(errors) == len(jobs):
        raise errors[0]
    return [item for group in zip_longest(*groups) for item in group if item]


def build_format(mode, height):
    limit = f"[height<={height}]" if height else ""
    if mode == "audio":
        return "bestaudio/best"
    if mode == "both":
        return f"bv*{limit}+ba/b{limit}"
    return f"bv*{limit}/b{limit}"


def download(url, folder, mode, height, progress_cb, audio_kbps=192):
    def hook(status):
        if status["status"] == "downloading":
            total = status.get("total_bytes") or status.get("total_bytes_estimate")
            got = status.get("downloaded_bytes") or 0
            progress_cb((got / total * 100) if total else None)
        elif status["status"] == "finished":
            progress_cb(None)

    opts = {
        "format": build_format(mode, height),
        "outtmpl": os.path.join(folder, "%(title)s [%(id)s].%(ext)s"),
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "windowsfilenames": True,
        "progress_hooks": [hook],
    }
    ffmpeg = ffmpeg_path()
    if ffmpeg:
        opts["ffmpeg_location"] = ffmpeg
    if mode == "audio":
        opts["postprocessors"] = [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": str(audio_kbps),
        }]
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
        path = ydl.prepare_filename(info)
    return os.path.splitext(path)[0] + ".mp3" if mode == "audio" else path


def resolve_preview(url):
    """Restituisce URL diretti video/audio per il player integrato."""
    opts = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "format": "bestvideo[height<=720]+bestaudio/best[height<=720]/best",
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
    parts = info.get("requested_formats") or [info]
    video = next((f for f in parts if f.get("vcodec") not in (None, "none")), None)
    audio = next((f for f in parts if f.get("acodec") not in (None, "none") and f.get("vcodec") == "none"), None)
    if not video or not video.get("url"):
        raise RuntimeError("nessun flusso video disponibile")
    return {
        "video": video["url"],
        "audio": audio["url"] if audio else None,
        "headers": info.get("http_headers") or {},
        "title": info.get("title") or "",
    }


class VideoFinderApp:
    def __init__(self, root):
        self.root = root
        self.messages = queue.Queue()
        self.results = []
        self.sites = list(TOP_SITES)
        self.searching = False
        self.downloading = False

        self.vp = None
        self.ap = None
        self.video_hwnd = None
        self._preview_token = 0
        self._player_job = None
        self._place_job = None
        self.seeking = False
        self.suggest = None
        self.suggest_list = None

        root.title(APP_NAME)
        root.geometry("1180x760")
        root.minsize(900, 560)
        root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.style = tb.Style()
        self.style.configure("Treeview", rowheight=32, font=("Segoe UI", 10))
        self.style.configure("Treeview.Heading", font=("Segoe UI Semibold", 10))
        self.style.configure("TEntry", fieldbackground=self.style.colors.dark, padding=7)

        header = tb.Frame(root, padding=(24, 20, 24, 4))
        header.pack(fill=X)
        tb.Label(header, text=APP_NAME, font=("Segoe UI Semibold", 22)).pack(side=LEFT)
        tb.Label(header, text="Cerca e scarica da oltre 1000 siti supportati",
                 bootstyle="secondary", font=("Segoe UI", 10)).pack(side=LEFT, padx=(12, 0), pady=(10, 0))

        bar = tb.Frame(root, padding=(24, 8, 24, 12))
        bar.pack(fill=X)
        self.platform = tb.Combobox(bar, values=["Multipiattaforma"] + list(TOP_SITES),
                                    width=24, bootstyle="secondary")
        self.platform.insert(0, "Multipiattaforma")
        self.platform.pack(side=LEFT)
        self.platform.bind("<KeyRelease>", self.filter_sites)
        self.platform.bind("<Down>", lambda e: self.move_suggestion(1))
        self.platform.bind("<Up>", lambda e: self.move_suggestion(-1))
        self.platform.bind("<Return>", self.on_platform_return)
        self.platform.bind("<Escape>", lambda e: (self.hide_suggestions(), "break")[1])
        self.platform.bind("<FocusOut>", lambda e: self.root.after(220, self.hide_suggestions))
        self.query = tb.Entry(bar, bootstyle="secondary")
        self.query.pack(side=LEFT, fill=X, expand=True, padx=8)
        self.query.bind("<Return>", lambda _e: self.start_search())
        self.search_btn = tb.Button(bar, text="Cerca", bootstyle="primary", command=self.start_search)
        self.search_btn.pack(side=LEFT)
        self.preview_btn = tb.Button(bar, text="▶ Riproduci", bootstyle="secondary-outline", command=self.preview)
        self.preview_btn.pack(side=LEFT, padx=(8, 0))

        content = tb.Frame(root, padding=(24, 0, 24, 0))
        content.pack(fill=BOTH, expand=True)
        content.columnconfigure(0, weight=1)
        content.rowconfigure(0, weight=1)
        self.table_frame = tb.Frame(content)
        self.table_frame.grid(row=0, column=0, sticky="nsew")

        columns = ("title", "duration", "author", "platform")
        self.tree = tb.Treeview(self.table_frame, columns=columns, show="headings", selectmode="browse")
        for col, label, width, stretch, anchor in (
            ("title", "Titolo", 620, True, W),
            ("duration", "Durata", 80, False, W),
            ("author", "Canale", 220, False, W),
            ("platform", "Sito", 140, False, W),
        ):
            self.tree.heading(col, text=label, anchor=anchor)
            self.tree.column(col, width=width, stretch=stretch, anchor=anchor)
        scroll = tb.Scrollbar(self.table_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side=LEFT, fill=BOTH, expand=True)
        scroll.pack(side=LEFT, fill="y")
        self.tree.bind("<Double-1>", lambda _e: self.preview())
        self.tree.bind("<Return>", lambda _e: self.preview())
        self.tree.tag_configure("odd", background=self.style.colors.inputbg)

        self.preview_panel = tb.Frame(content, width=460)
        self.preview_panel.pack_propagate(False)
        phead = tb.Frame(self.preview_panel)
        phead.pack(fill=X, padx=14, pady=(0, 6))
        self.preview_title = tb.Label(phead, text="Anteprima", font=("Segoe UI Semibold", 10),
                                      wraplength=380, justify=LEFT)
        self.preview_title.pack(side=LEFT, fill=X, expand=True)
        tb.Button(phead, text="✕", bootstyle="secondary-outline", width=3,
                  command=self.close_preview).pack(side=RIGHT)
        self.video_holder = tk.Frame(self.preview_panel, bg="#000000", height=243)
        self.video_holder.pack(fill=X, padx=14)
        self.video_holder.pack_propagate(False)
        self.preview_status = tk.Label(self.video_holder, text="", bg="#000000", fg="#c0caf5",
                                       font=("Segoe UI", 10), wraplength=400, justify="center")
        self.preview_status.place(relx=0.5, rely=0.5, anchor="center")
        ctrl = tb.Frame(self.preview_panel)
        ctrl.pack(fill=X, padx=14, pady=(8, 0))
        self.play_btn = tb.Button(ctrl, text="▶", width=4, bootstyle="primary",
                                  command=self.toggle_pause, state="disabled")
        self.play_btn.pack(side=LEFT)
        self.time_label = tb.Label(ctrl, text="0:00 / 0:00", bootstyle="secondary")
        self.time_label.pack(side=RIGHT)
        self.seek = tb.Scale(self.preview_panel, from_=0, to=1000, command=self.on_seek,
                             bootstyle="primary")
        self.seek.pack(fill=X, padx=14, pady=(8, 0))
        self.seek.bind("<ButtonPress-1>", lambda e: setattr(self, "seeking", True))
        self.seek.bind("<ButtonRelease-1>", lambda e: setattr(self, "seeking", False))
        self.video_holder.bind("<Configure>", lambda e: self.place_video())
        self.root.bind("<Configure>", lambda e: self.place_video())

        panel = tb.Frame(root, padding=(24, 14, 24, 18))
        panel.pack(fill=X)
        tb.Label(panel, text="Scarica", bootstyle="secondary").grid(row=0, column=0, sticky=W)
        modes = tb.Frame(panel)
        modes.grid(row=0, column=1, columnspan=3, sticky=W, padx=(10, 0))
        self.mode = tb.StringVar(value="both")
        for value, label in (("both", "Video + audio"), ("video", "Solo video"), ("audio", "Solo audio (mp3)")):
            tb.Radiobutton(modes, text=label, value=value, variable=self.mode,
                           bootstyle="primary", command=self.on_mode_change).pack(side=LEFT, padx=(0, 14))
        tb.Label(panel, text="Qualità video", bootstyle="secondary").grid(row=0, column=4, sticky="e", padx=(24, 8))
        self.quality = tb.Combobox(panel, values=QUALITIES, state="readonly", width=10, bootstyle="secondary")
        self.quality.current(0)
        self.quality.grid(row=0, column=5, sticky=W)
        tb.Label(panel, text="Qualità audio", bootstyle="secondary").grid(row=0, column=6, sticky="e", padx=(18, 8))
        self.audio_quality = tb.Combobox(panel, values=AUDIO_QUALITIES, state="readonly", width=10,
                                         bootstyle="secondary")
        self.audio_quality.current(2)
        self.audio_quality.configure(state="disabled")
        self.audio_quality.grid(row=0, column=7, sticky=W)

        tb.Label(panel, text="Cartella", bootstyle="secondary").grid(row=1, column=0, sticky=W, pady=(12, 0))
        self.folder = tb.Entry(panel, bootstyle="secondary")
        self.folder.insert(0, os.path.join(os.path.expanduser("~"), "Downloads"))
        self.folder.grid(row=1, column=1, columnspan=3, sticky="ew", padx=(10, 0), pady=(12, 0))
        tb.Button(panel, text="Sfoglia…", bootstyle="secondary-outline",
                  command=self.pick_folder).grid(row=1, column=4, padx=(24, 8), pady=(12, 0))
        self.download_btn = tb.Button(panel, text="Scarica", bootstyle="success",
                                      width=12, command=self.start_download)
        self.download_btn.grid(row=1, column=5, sticky="ew", pady=(12, 0))
        panel.columnconfigure(2, weight=1)

        self.bar = tb.Progressbar(panel, mode="determinate", maximum=100, bootstyle="success-striped")
        self.bar.grid(row=2, column=0, columnspan=8, sticky="ew", pady=(14, 6))
        self.status = tb.Label(panel, text="Scrivi un titolo e premi Cerca. Doppio clic per riprodurre.",
                               bootstyle="secondary")
        self.status.grid(row=3, column=0, columnspan=8, sticky=W)

        threading.Thread(target=self.load_sites, daemon=True).start()
        self.root.after(50, self.apply_dark_titlebar)
        self.root.after(120, self.poll)

    # ---------- suggerimenti piattaforma ----------
    def ensure_suggest(self):
        if self.suggest:
            return
        self.suggest = tk.Toplevel(self.root)
        self.suggest.withdraw()
        self.suggest.overrideredirect(True)
        self.suggest.attributes("-topmost", True)
        border = tk.Frame(self.suggest, bg=self.style.colors.border)
        border.pack(fill=BOTH, expand=True)
        self.suggest_list = tk.Listbox(
            border, activestyle="none", borderwidth=0, highlightthickness=0,
            bg=self.style.colors.dark, fg=self.style.colors.fg,
            selectbackground=self.style.colors.primary,
            selectforeground=self.style.colors.selectfg,
            font=("Segoe UI", 10))
        self.suggest_list.pack(fill=BOTH, expand=True, padx=1, pady=1)
        self.suggest_list.bind("<ButtonRelease-1>", self.pick_suggestion)
        self.suggest_list.bind("<MouseWheel>", self.scroll_suggestions)

    def filter_sites(self, event=None):
        if event and event.keysym in ("Up", "Down", "Return", "Escape", "Tab",
                                      "Shift_L", "Shift_R", "Control_L", "Control_R"):
            return
        text = self.platform.get().strip().lower()
        if not text or text == "multipiattaforma":
            self.platform["values"] = ["Multipiattaforma"] + self.sites
            self.hide_suggestions()
            return
        matches = [s for s in self.sites if text in s.lower()][:60]
        self.platform["values"] = ["Multipiattaforma"] + matches
        self.show_suggestions(matches)

    def show_suggestions(self, matches):
        if not matches:
            self.hide_suggestions()
            return
        self.ensure_suggest()
        self.suggest_list.delete(0, END)
        for item in matches:
            self.suggest_list.insert(END, item)
        self.suggest_list.selection_clear(0, END)
        self.suggest_list.selection_set(0)
        self.suggest_list.activate(0)
        rows = min(10, len(matches))
        self.suggest_list.configure(height=rows)
        width = max(self.platform.winfo_width(), 220)
        height = rows * 21 + 6
        x = self.platform.winfo_rootx()
        y = self.platform.winfo_rooty() + self.platform.winfo_height() + 2
        self.suggest.geometry(f"{width}x{height}+{x}+{y}")
        self.suggest.deiconify()
        self.suggest.lift()

    def hide_suggestions(self):
        if self.suggest:
            self.suggest.withdraw()

    def move_suggestion(self, delta):
        if not self.suggest or not self.suggest.winfo_ismapped():
            if self.platform.get().strip() and self.platform.get().strip().lower() != "multipiattaforma":
                self.filter_sites()
            return "break"
        size = self.suggest_list.size()
        if not size:
            return "break"
        current = self.suggest_list.curselection()
        index = (current[0] if current else -1) + delta
        index = max(0, min(size - 1, index))
        self.suggest_list.selection_clear(0, END)
        self.suggest_list.selection_set(index)
        self.suggest_list.activate(index)
        self.suggest_list.see(index)
        return "break"

    def scroll_suggestions(self, event):
        self.suggest_list.yview_scroll(-1 if event.delta > 0 else 1, "units")
        return "break"

    def pick_suggestion(self, _event=None):
        if not self.suggest or not self.suggest_list.curselection():
            return
        self.platform.set(self.suggest_list.get(self.suggest_list.curselection()[0]))
        self.platform["values"] = ["Multipiattaforma"] + self.sites
        self.hide_suggestions()
        self.query.focus_set()

    def on_platform_return(self, _event=None):
        if self.suggest and self.suggest.winfo_ismapped():
            self.pick_suggestion()
            return "break"
        return None

    # ---------- ricerca ----------
    def load_sites(self):
        try:
            self.messages.put(("sites", get_sites()))
        except Exception as exc:
            self.messages.put(("sites_error", f"Elenco siti non disponibile: {exc}"))

    def on_mode_change(self):
        audio = self.mode.get() == "audio"
        self.quality.configure(state="disabled" if audio else "readonly")
        self.audio_quality.configure(state="readonly" if audio else "disabled")

    def pick_folder(self):
        chosen = filedialog.askdirectory(initialdir=self.folder.get() or os.path.expanduser("~"))
        if chosen:
            self.folder.delete(0, "end")
            self.folder.insert(0, chosen)

    def resolve_site(self):
        text = self.platform.get().strip()
        if text.lower() == "multipiattaforma":
            return None
        if text in self.sites:
            return text
        matches = [s for s in self.sites if text.lower() in s]
        if len(matches) == 1:
            self.platform.set(matches[0])
            return matches[0]
        messagebox.showinfo("Sito", "Scrivi parte del nome del sito e scegli una voce dall'elenco.")
        return ""

    def start_search(self):
        if self.searching or self.downloading:
            return
        text = self.query.get().strip()
        if not text:
            return
        self.hide_suggestions()
        if text.lower().startswith(("http://", "https://")):
            self.set_results([{"title": text, "duration": "", "author": "", "url": text, "platform": "link"}])
            self.status.config(text="Link caricato. Scegli il formato e premi Scarica.")
            return
        site = self.resolve_site()
        if site == "":
            return
        self.search_btn.config(state="disabled")
        self.searching = True
        self.status.config(text=f"Cerco su {site or 'tutti i siti'}…")
        threading.Thread(target=self.search_worker, args=(site, text), daemon=True).start()

    def search_worker(self, site, text):
        try:
            if site is None:
                results = search_all(text)
            elif site == "youtube.com":
                results = search_youtube(text, 15)
            elif site == "dailymotion.com":
                results = search_dailymotion(text, 15)
            elif site in NATIVE_SEARCH:
                results = search_native(NATIVE_SEARCH[site], text, site, 15)
            else:
                results = web_search(text, site, 15)
            self.messages.put(("results", results))
        except Exception as exc:
            self.messages.put(("error", f"Ricerca fallita: {exc}"))

    def set_results(self, results):
        self.searching = False
        self.results = results
        self.tree.delete(*self.tree.get_children())
        for index, item in enumerate(results):
            self.tree.insert("", "end", iid=str(index), values=(
                item["title"], item["duration"], item["author"], item["platform"]),
                tags=("odd",) if index % 2 else ())
        self.search_btn.config(state="normal")
        self.status.config(text=f"{len(results)} risultati." if results else "Nessun risultato.")

    # ---------- anteprima / player ----------
    def preview(self):
        selection = self.tree.selection()
        if not selection:
            messagebox.showinfo("Anteprima", "Seleziona prima un video dall'elenco.")
            return
        if not MPV_READY:
            messagebox.showerror("Anteprima", f"Player integrato non disponibile: {MPV_ERROR}")
            return
        item = self.results[int(selection[0])]
        self._preview_token += 1
        token = self._preview_token
        self.open_preview_panel(item["title"])
        threading.Thread(target=self.preview_worker, args=(token, item["url"]), daemon=True).start()

    def open_preview_panel(self, title):
        if not self.preview_panel.winfo_ismapped():
            self.preview_panel.grid(row=0, column=1, sticky="ns", padx=(16, 0))
        self.preview_title.config(text=title)
        self.preview_status.config(text="Carico anteprima…")
        self.play_btn.config(state="disabled")
        self.seek.set(0)
        self.time_label.config(text="0:00 / 0:00")
        self.root.update_idletasks()

    def preview_worker(self, token, url):
        try:
            self.messages.put(("preview_ready", (token, resolve_preview(url))))
        except Exception as exc:
            self.messages.put(("preview_error", (token, f"Anteprima non disponibile: {exc}")))

    def start_player(self, data):
        self.destroy_players()
        self.root.update_idletasks()
        if not user32:
            self.preview_status.config(text="Player integrato solo su Windows.")
            return
        x, y, w, h = self.holder_rect()
        if w < 20 or h < 20:
            self.preview_status.config(text="Spazio insufficiente per il player.")
            return
        self.video_hwnd = user32.CreateWindowExW(
            0, "STATIC", "", WS_CHILD | WS_VISIBLE | WS_CLIPCHILDREN,
            x, y, w, h, ctypes.c_void_p(self.root.winfo_id()), None, None, None)
        try:
            self.vp = mpv.MPV(wid=str(self.video_hwnd), osc=False, pause=True, keep_open="yes")
            if data["audio"]:
                self.ap = mpv.MPV(vid="no", audio_display="no", pause=True)
                self.ap.volume = 85
                self.vp.mute = True
            fields = [f"{k}: {v}" for k, v in (data.get("headers") or {}).items()]
            if fields:
                self.vp.http_header_fields = fields
                if self.ap:
                    self.ap.http_header_fields = fields
            self.vp.play(data["video"])
            if self.ap:
                self.ap.play(data["audio"])
            self.preview_status.config(text="")
            self.play_btn.config(state="normal")
            self.root.after(300, self.place_video)
            self.root.after(350, self.resume_playback)
            self.poll_player()
        except Exception as exc:
            self.destroy_players()
            self.preview_status.config(text=f"Errore player: {exc}")

    def holder_rect(self):
        self.root.update_idletasks()
        return (self.video_holder.winfo_rootx() - self.root.winfo_rootx(),
                self.video_holder.winfo_rooty() - self.root.winfo_rooty(),
                self.video_holder.winfo_width(), self.video_holder.winfo_height())

    def place_video(self):
        if not self.video_hwnd:
            return
        x, y, w, h = self.holder_rect()
        if w < 20 or h < 20:
            return
        user32.MoveWindow(ctypes.c_void_p(self.video_hwnd), x, y, w, h, True)
        child = user32.GetWindow(ctypes.c_void_p(self.video_hwnd), 5)
        if child:
            user32.MoveWindow(ctypes.c_void_p(child), 0, 0, w, h, True)

    def resume_playback(self):
        if not self.vp:
            return
        try:
            self.vp.pause = False
            if self.ap:
                self.ap.pause = False
            self.play_btn.config(text="⏸")
        except Exception:
            pass

    def toggle_pause(self):
        if not self.vp:
            return
        try:
            if self.vp.eof_reached:
                self.vp.seek(0, reference="absolute")
                if self.ap:
                    self.ap.seek(0, reference="absolute")
                paused = False
            else:
                paused = not bool(self.vp.pause)
            self.vp.pause = paused
            if self.ap:
                self.ap.pause = paused
            self.play_btn.config(text="▶" if paused else "⏸")
        except Exception:
            pass

    def on_seek(self, value):
        if not self.seeking or not self.vp:
            return
        try:
            duration = self.vp.duration or 0
            target = float(value) / 1000 * duration
            self.vp.seek(target, reference="absolute")
            if self.ap:
                self.ap.seek(target, reference="absolute")
        except Exception:
            pass

    def poll_player(self):
        if not self.vp:
            return
        try:
            pos = self.vp.time_pos or 0
            duration = self.vp.duration or 0
            if duration and not self.seeking:
                self.seek.set(max(0, min(1000, pos / duration * 1000)))
            self.time_label.config(text=f"{clock(pos)} / {clock(duration)}")
            self.play_btn.config(text="▶" if self.vp.pause or self.vp.eof_reached else "⏸")
        except Exception:
            pass
        self._player_job = self.root.after(400, self.poll_player)

    def close_preview(self):
        self._preview_token += 1
        self.destroy_players()
        self.preview_panel.grid_remove()
        self.preview_status.config(text="")
        self.preview_title.config(text="Anteprima")

    def destroy_players(self):
        if self._player_job:
            try:
                self.root.after_cancel(self._player_job)
            except Exception:
                pass
            self._player_job = None
        for player in (self.vp, self.ap):
            if player:
                try:
                    player.terminate()
                except Exception:
                    pass
        self.vp = self.ap = None
        if self.video_hwnd and user32:
            user32.DestroyWindow(ctypes.c_void_p(self.video_hwnd))
        self.video_hwnd = None

    def on_close(self):
        self.destroy_players()
        self.root.destroy()

    # ---------- download ----------
    def start_download(self):
        if self.downloading:
            return
        selection = self.tree.selection()
        if not selection:
            messagebox.showinfo("Video", "Seleziona prima un video dall'elenco.")
            return
        item = self.results[int(selection[0])]
        folder = self.folder.get().strip()
        if not os.path.isdir(folder):
            messagebox.showerror("Cartella", "La cartella di destinazione non esiste.")
            return
        mode = self.mode.get()
        height = None if self.quality.get() == "Migliore" or mode == "audio" else int(self.quality.get().rstrip("p"))
        audio_kbps = int(self.audio_quality.get().split()[0]) if mode == "audio" else 192
        self.download_btn.config(state="disabled")
        self.search_btn.config(state="disabled")
        self.downloading = True
        self.bar["value"] = 0
        self.status.config(text="Preparo il download…")
        threading.Thread(target=self.download_worker,
                         args=(item["url"], folder, mode, height, audio_kbps), daemon=True).start()

    def download_worker(self, url, folder, mode, height, audio_kbps):
        def progress(pct):
            self.messages.put(("progress", pct))

        try:
            path = download(url, folder, mode, height, progress, audio_kbps)
            self.messages.put(("done", f"Fatto: {os.path.basename(path)}"))
        except Exception as exc:
            self.messages.put(("error", f"Download fallito: {exc}"))

    # ---------- ciclo eventi ----------
    def apply_dark_titlebar(self):
        if sys.platform != "win32":
            return
        try:
            self.root.update_idletasks()
            hwnd = user32.GetParent(self.root.winfo_id())
            value = ctypes.c_int(1)
            for attribute in (20, 19):
                ctypes.windll.dwmapi.DwmSetWindowAttribute(
                    hwnd, attribute, ctypes.byref(value), ctypes.sizeof(value))
        except Exception:
            pass

    def poll(self):
        while True:
            try:
                kind, payload = self.messages.get_nowait()
            except queue.Empty:
                break
            if kind == "sites":
                self.sites = payload
                current = self.platform.get()
                self.platform["values"] = ["Multipiattaforma"] + self.sites
                self.platform.set(current)
            elif kind == "sites_error":
                self.status.config(text=payload)
            elif kind == "results":
                self.set_results(payload)
            elif kind == "preview_ready":
                token, data = payload
                if token == self._preview_token:
                    self.start_player(data)
            elif kind == "preview_error":
                token, msg = payload
                if token == self._preview_token:
                    self.preview_status.config(text=msg)
            elif kind == "progress":
                if payload is None:
                    self.status.config(text="Conversione/merge in corso…")
                else:
                    self.bar["value"] = payload
                    self.status.config(text=f"Download {payload:.0f}%")
            elif kind == "done":
                self.bar["value"] = 100
                self.status.config(text=payload)
                self.downloading = False
                self.download_btn.config(state="normal")
                self.search_btn.config(state="normal")
            elif kind == "error":
                self.status.config(text="Errore.")
                self.searching = False
                self.downloading = False
                self.download_btn.config(state="normal")
                self.search_btn.config(state="normal")
                messagebox.showerror("Errore", payload)
        self.root.after(120, self.poll)


def selftest():
    """Verifica end-to-end dell'exe (--selftest), inclusi ffmpeg e mpv incorporati."""
    import time
    import traceback

    base = os.environ.get("TEMP", ".")
    log_path = os.path.join(base, "VideoFinder_selftest.log")
    ok = False
    with open(log_path, "w", encoding="utf-8") as log:
        try:
            if getattr(sys, "frozen", False):
                os.environ["PATH"] = ""  # forza l'uso di ffmpeg/mpv dentro l'exe
            log.write(f"ffmpeg={ffmpeg_path()}\n")
            log.write(f"mpv={MPV_READY} {MPV_ERROR}\n")
            results = search_youtube("me at the zoo", 1)
            log.write(f"youtube={len(results)}\n")
            web = web_search("big buck bunny", "vimeo.com", 3)
            log.write(f"web_vimeo={len(web)}\n")
            folder = os.path.join(base, "vf_selftest")
            os.makedirs(folder, exist_ok=True)
            audio = download(results[0]["url"], folder, "audio", None, lambda pct: None, audio_kbps=320)
            merged = download(results[0]["url"], folder, "both", 360, lambda pct: None)
            dm = search_dailymotion("big buck bunny", 1)
            dm_audio = download(dm[0]["url"], folder, "audio", None, lambda pct: None)
            audio_bitrate = 0
            try:
                import shutil
                import subprocess
                ff = ffmpeg_path() or shutil.which("ffmpeg")
                if ff and os.path.isfile(audio):
                    probe = subprocess.run([ff, "-hide_banner", "-i", audio],
                                           capture_output=True, text=True).stderr
                    match = re.search(r"Audio:\s*mp3[^\n]*?(\d+)\s*kb/s", probe)
                    if match:
                        audio_bitrate = int(match.group(1)) * 1000
            except Exception:
                pass
            play_pos = 0
            video_pos = 0
            if MPV_READY:
                player = mpv.MPV(vid="no", audio_display="no", ao="null", pause=True)
                player.play(audio)
                player.pause = False
                time.sleep(2)
                play_pos = player.time_pos or 0
                player.terminate()

                gui = tk.Tk()
                gui.geometry("420x240+40+40")
                gui.update()
                hwnd = user32.CreateWindowExW(
                    0, "STATIC", "", WS_CHILD | WS_VISIBLE | WS_CLIPCHILDREN,
                    0, 0, 400, 225, ctypes.c_void_p(gui.winfo_id()), None, None, None)
                vplayer = mpv.MPV(wid=str(hwnd), osc=False, pause=True)
                vplayer.play(merged)
                vplayer.pause = False
                end = time.time() + 4
                while time.time() < end:
                    gui.update()
                    time.sleep(0.05)
                video_pos = vplayer.time_pos or 0
                vplayer.terminate()
                user32.DestroyWindow(ctypes.c_void_p(hwnd))
                gui.destroy()
            ok = (os.path.isfile(audio) and os.path.isfile(merged) and os.path.isfile(dm_audio)
                  and play_pos > 0 and video_pos > 0 and audio_bitrate >= 300000)
            log.write(f"audio={audio} exists={os.path.isfile(audio)}\n")
            log.write(f"audio_bitrate={audio_bitrate}\n")
            log.write(f"merged={merged} exists={os.path.isfile(merged)}\n")
            log.write(f"dailymotion={dm_audio} exists={os.path.isfile(dm_audio)}\n")
            log.write(f"mpv_play_pos={play_pos}\n")
            log.write(f"mpv_video_pos={video_pos}\n")
        except Exception:
            log.write(traceback.format_exc())
    return 0 if ok else 1


def main():
    root = tb.Window(themename="tokyo-night-dark")
    icon = os.path.join(getattr(sys, "_MEIPASS", APP_DIR), "ThaSkull.ico")
    if os.path.isfile(icon):
        try:
            root.iconbitmap(icon)
        except Exception:
            pass
    VideoFinderApp(root)
    root.mainloop()


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(selftest())
    main()
