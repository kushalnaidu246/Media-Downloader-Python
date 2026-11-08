import os
import queue
import re
import shutil
import subprocess
import threading
import time
import tkinter as tk
from tkinter import filedialog

import customtkinter as ctk
import static_ffmpeg
import yt_dlp

# Deno (JS runtime used by yt-dlp for YouTube) and FFmpeg
deno_path = os.path.expanduser("~/.deno/bin")
if os.path.exists(deno_path) and deno_path not in os.environ["PATH"]:
    os.environ["PATH"] = deno_path + os.path.pathsep + os.environ["PATH"]
static_ffmpeg.add_paths()

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
# Default clients can 403 partway through a download (then only 360p is left),
# so retry with clients that still serve HD streams.
CLIENT_ATTEMPTS = [None, ["web_embedded"], ["tv", "mweb"]]
BROWSERS = ["None", "Chrome", "Safari", "Firefox", "Edge", "Brave"]
QUALITIES = ["Best", "2160p", "1440p", "1080p", "720p", "480p", "360p"]
KIND_LABELS = {"Video  ·  MP4": "mp4", "Audio  ·  MP3": "mp3"}

# Palette
BG = "#0A0C12"
CARD = "#131722"
FIELD = "#0E111A"
BORDER = "#242B3B"
TEXT = "#EEF0F6"
MUTED = "#8A93A8"
ACCENT = "#7B61FF"
ACCENT_HOVER = "#6A4FEF"
OK = "#34D399"
ERR = "#F87171"
TONES = {"info": TEXT, "ok": OK, "err": ERR}

ctk.set_appearance_mode("dark")


def video_format(quality):
    cap = "" if quality == "Best" else f"[height<={quality[:-1]}]"
    # Resolution wins; format_sort then prefers H.264/AAC among equal resolutions
    return f"bv*{cap}+ba/b{cap}"


def font(size, weight="normal"):
    return ctk.CTkFont(family="SF Pro Display", size=size, weight=weight)


class App(ctk.CTk):
    def __init__(self):
        super().__init__(fg_color=BG)
        self.title("Media Downloader")
        self.geometry("780x700")
        self.resizable(False, False)

        self.url = tk.StringVar()
        self.kind = tk.StringVar(value="mp4")
        self.quality = tk.StringVar(value="Best")
        self.compat = tk.BooleanVar(value=True)
        self.cookies = tk.StringVar(value="None")
        self.folder = tk.StringVar(value=os.path.expanduser("~/Downloads"))

        self.cancel_ev = threading.Event()
        self.touched = set()  # files written by the current download
        self.q = queue.Queue()

        self._build()
        self._poll()
        self.bind("<Return>", lambda e: self._start())

    # ---------- layout ----------
    def _card(self, parent):
        return ctk.CTkFrame(parent, fg_color=CARD, corner_radius=18,
                            border_width=1, border_color=BORDER)

    def _label(self, parent, text, **kw):
        return ctk.CTkLabel(parent, text=text, text_color=kw.pop("color", MUTED),
                            font=kw.pop("font", font(12)), **kw)

    def _build(self):
        root = ctk.CTkFrame(self, fg_color="transparent")
        root.pack(fill="both", expand=True, padx=30, pady=26)

        # Header
        head = ctk.CTkFrame(root, fg_color="transparent")
        head.pack(fill="x", pady=(0, 20))
        logo = ctk.CTkFrame(head, width=46, height=46, corner_radius=14, fg_color=ACCENT)
        logo.pack(side="left")
        logo.pack_propagate(False)
        ctk.CTkLabel(logo, text="↓", font=font(24, "bold"), text_color="white").pack(expand=True)
        titles = ctk.CTkFrame(head, fg_color="transparent")
        titles.pack(side="left", padx=14)
        ctk.CTkLabel(titles, text="Media Downloader", font=font(22, "bold"),
                     text_color=TEXT).pack(anchor="w")
        self._label(titles, "YouTube & Instagram  ·  up to 4K").pack(anchor="w")

        # Link card
        link = self._card(root)
        link.pack(fill="x", pady=(0, 14))
        self._label(link, "LINK", font=font(11, "bold")).pack(anchor="w", padx=20, pady=(16, 6))
        row = ctk.CTkFrame(link, fg_color="transparent")
        row.pack(fill="x", padx=20, pady=(0, 18))
        self.entry = ctk.CTkEntry(
            row, textvariable=self.url, height=46, corner_radius=12, fg_color=FIELD,
            border_color=BORDER, text_color=TEXT, font=font(14),
            placeholder_text="Paste a YouTube or Instagram link…")
        self.entry.pack(side="left", fill="x", expand=True)
        ctk.CTkButton(row, text="Paste", width=76, height=46, corner_radius=12,
                      fg_color=FIELD, hover_color=BORDER, border_width=1, border_color=BORDER,
                      text_color=TEXT, font=font(13), command=self._paste).pack(side="left", padx=(10, 0))

        # Options card
        opt = self._card(root)
        opt.pack(fill="x", pady=(0, 14))
        grid = ctk.CTkFrame(opt, fg_color="transparent")
        grid.pack(fill="x", padx=20, pady=18)
        grid.columnconfigure(0, weight=1, uniform="c")
        grid.columnconfigure(1, weight=1, uniform="c")

        self._label(grid, "FORMAT", font=font(11, "bold")).grid(row=0, column=0, sticky="w")
        self.seg = ctk.CTkSegmentedButton(
            grid, values=list(KIND_LABELS), command=self._kind_changed, height=38,
            corner_radius=10, fg_color=FIELD, unselected_color=FIELD,
            unselected_hover_color=BORDER, selected_color=ACCENT, selected_hover_color=ACCENT_HOVER,
            text_color=TEXT, font=font(13))
        self.seg.set("Video  ·  MP4")
        self.seg.grid(row=1, column=0, sticky="ew", padx=(0, 10), pady=(6, 16))

        self._label(grid, "QUALITY", font=font(11, "bold")).grid(row=0, column=1, sticky="w")
        self.qmenu = self._menu(grid, self.quality, QUALITIES)
        self.qmenu.grid(row=1, column=1, sticky="ew", padx=(10, 0), pady=(6, 16))

        self._label(grid, "LOGIN COOKIES", font=font(11, "bold")).grid(row=2, column=0, sticky="w")
        self._menu(grid, self.cookies, BROWSERS).grid(
            row=3, column=0, sticky="ew", padx=(0, 10), pady=(6, 0))
        self._label(grid, 'Choose your browser if you see "not a bot".', font=font(11),
                    wraplength=330, justify="left").grid(row=4, column=0, sticky="w", pady=(6, 0))

        self.compat_sw = ctk.CTkSwitch(
            grid, text="QuickTime-compatible", variable=self.compat, onvalue=True, offvalue=False,
            progress_color=ACCENT, button_color=TEXT, button_hover_color="white",
            fg_color=BORDER, text_color=TEXT, font=font(13))
        self.compat_sw.grid(row=3, column=1, sticky="w", padx=(10, 0), pady=(6, 0))
        self._label(grid, "Converts 1440p / 4K to H.264 so it plays everywhere.", font=font(11),
                    wraplength=330, justify="left").grid(row=4, column=1, sticky="w", padx=(10, 0),
                                                         pady=(6, 0))

        # Save-to row
        sep = ctk.CTkFrame(opt, height=1, fg_color=BORDER)
        sep.pack(fill="x", padx=20)
        save = ctk.CTkFrame(opt, fg_color="transparent")
        save.pack(fill="x", padx=20, pady=14)
        self._label(save, "SAVE TO", font=font(11, "bold")).pack(side="left")
        ctk.CTkButton(save, text="Change", width=80, height=32, corner_radius=10,
                      fg_color=FIELD, hover_color=BORDER, border_width=1, border_color=BORDER,
                      text_color=TEXT, font=font(12), command=self._browse).pack(side="right")
        self.folder_lbl = ctk.CTkLabel(save, text=self._short(self.folder.get()), text_color=TEXT,
                                       font=font(13), anchor="e")
        self.folder_lbl.pack(side="right", padx=14, fill="x", expand=True)

        # Progress card
        prog = self._card(root)
        prog.pack(fill="x", pady=(0, 18))
        top = ctk.CTkFrame(prog, fg_color="transparent")
        top.pack(fill="x", padx=20, pady=(16, 8))
        self.stage = ctk.CTkLabel(top, text="Ready", font=font(16, "bold"), text_color=TEXT)
        self.stage.pack(side="left")
        self.pct = ctk.CTkLabel(top, text="", font=font(16, "bold"), text_color=ACCENT)
        self.pct.pack(side="right")
        self.bar = ctk.CTkProgressBar(prog, height=10, corner_radius=5, fg_color=FIELD,
                                      progress_color=ACCENT)
        self.bar.set(0)
        self.bar.pack(fill="x", padx=20)
        self.detail = ctk.CTkLabel(prog, text="Paste a link above and press Download.",
                                   font=font(12), text_color=MUTED, anchor="w", justify="left",
                                   wraplength=680)
        self.detail.pack(fill="x", padx=20, pady=(10, 16))

        # Buttons
        btns = ctk.CTkFrame(root, fg_color="transparent")
        btns.pack(fill="x")
        self.btn = ctk.CTkButton(btns, text="Download", height=54, corner_radius=14,
                                 fg_color=ACCENT, hover_color=ACCENT_HOVER, text_color="white",
                                 text_color_disabled="#B9B0F5", font=font(17, "bold"),
                                 command=self._start)
        self.btn.pack(side="left", fill="x", expand=True)
        self.cancel_btn = ctk.CTkButton(btns, text="Cancel", width=120, height=54, corner_radius=14,
                                        fg_color=FIELD, hover_color="#2A1E24", border_width=1,
                                        border_color=BORDER, text_color=ERR, text_color_disabled=MUTED,
                                        font=font(15, "bold"), command=self._cancel, state="disabled")
        self.cancel_btn.pack(side="left", padx=(12, 0))

    def _menu(self, parent, var, values):
        return ctk.CTkOptionMenu(
            parent, variable=var, values=values, height=38, corner_radius=10, fg_color=FIELD,
            button_color=BORDER, button_hover_color=ACCENT, dropdown_fg_color=CARD,
            dropdown_hover_color=BORDER, dropdown_text_color=TEXT, text_color=TEXT,
            text_color_disabled=MUTED, font=font(13), dropdown_font=font(13))

    @staticmethod
    def _short(path, n=44):
        path = path.replace(os.path.expanduser("~"), "~")
        return path if len(path) <= n else "…" + path[-(n - 1):]

    # ---------- small handlers ----------
    def _poll(self):
        try:
            while True:
                self.q.get_nowait()()
        except queue.Empty:
            pass
        self.after(100, self._poll)

    def _paste(self):
        try:
            self.url.set(self.clipboard_get().strip())
        except tk.TclError:
            pass

    def _kind_changed(self, label):
        self.kind.set(KIND_LABELS[label])
        video = self.kind.get() == "mp4"
        self.qmenu.configure(state="normal" if video else "disabled")
        self.compat_sw.configure(state="normal" if video else "disabled")

    def _browse(self):
        d = filedialog.askdirectory(initialdir=self.folder.get())
        if d:
            self.folder.set(d)
            self.folder_lbl.configure(text=self._short(d))

    def _set(self, stage=None, detail=None, pct=None, busy=None, tone=None):
        """Thread-safe UI update (applied by the main thread via _poll)."""
        def apply():
            if stage is not None:
                self.stage.configure(text=stage, text_color=TONES.get(tone or "info", TEXT))
            if detail is not None:
                self.detail.configure(text=detail)
            if pct is not None:
                self.bar.set(pct / 100)
                self.pct.configure(text=f"{pct:.0f}%" if pct else "")
            if busy is not None:
                self.btn.configure(state="disabled" if busy else "normal",
                                   text="Working…" if busy else "Download")
                self.cancel_btn.configure(state="normal" if busy else "disabled")
        self.q.put(apply)

    def _cancel(self):
        self.cancel_ev.set()
        self.cancel_btn.configure(state="disabled")
        self.stage.configure(text="Cancelling…", text_color=TEXT)

    def _after_done(self, path, title):
        """Ask whether to play the file or start the next download."""
        win = ctk.CTkToplevel(self, fg_color=BG)
        win.title("Download complete")
        win.geometry("460x270")
        win.resizable(False, False)
        win.transient(self)

        badge = ctk.CTkFrame(win, width=56, height=56, corner_radius=28, fg_color="#10372B")
        badge.pack(pady=(26, 10))
        badge.pack_propagate(False)
        ctk.CTkLabel(badge, text="✓", font=font(26, "bold"), text_color=OK).pack(expand=True)
        ctk.CTkLabel(win, text="Download complete", font=font(18, "bold"), text_color=TEXT).pack()
        ctk.CTkLabel(win, text=title, font=font(12), text_color=MUTED, wraplength=400,
                     justify="center").pack(padx=24, pady=(6, 16))

        def play():
            if path and os.path.exists(path):
                subprocess.Popen(["open", path])
            win.destroy()

        def show():
            if path and os.path.exists(path):
                subprocess.Popen(["open", "-R", path])
            win.destroy()

        def nxt():
            win.destroy()
            self.url.set("")
            self._set("Ready", "Paste the next link and press Download.", 0)
            self.entry.focus()

        row = ctk.CTkFrame(win, fg_color="transparent")
        row.pack(fill="x", padx=24)
        ctk.CTkButton(row, text="▶  Play", height=42, corner_radius=12, fg_color=ACCENT,
                      hover_color=ACCENT_HOVER, font=font(14, "bold"), command=play).pack(
            side="left", fill="x", expand=True)
        for text, cmd in (("Show in Finder", show), ("Download next", nxt)):
            ctk.CTkButton(row, text=text, height=42, corner_radius=12, fg_color=FIELD,
                          hover_color=BORDER, border_width=1, border_color=BORDER,
                          text_color=TEXT, font=font(13), command=cmd).pack(
                side="left", fill="x", expand=True, padx=(8, 0))
        win.protocol("WM_DELETE_WINDOW", win.destroy)
        win.after(150, lambda: (win.lift(), win.focus_force()))

    # ---------- download logic ----------
    def _start(self):
        url = self.url.get().strip()
        if not url:
            self._set("Need a link", "Please paste a YouTube or Instagram link first.", 0, tone="err")
            return
        if str(self.btn.cget("state")) == "disabled":
            return
        self.cancel_ev.clear()
        self.touched.clear()
        self._set("Starting…", "Fetching video info", 0, True)
        optsets = [self._opts(c) for c in CLIENT_ATTEMPTS]
        compat = self.kind.get() == "mp4" and self.compat.get()  # read Tk vars on the main thread
        threading.Thread(target=self._run, args=(url, optsets, compat), daemon=True).start()

    def _hook(self, d):
        if d.get("filename"):
            self.touched.add(d["filename"])
        if self.cancel_ev.is_set():
            raise yt_dlp.utils.DownloadCancelled()
        if d["status"] == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            if total:
                pct = d["downloaded_bytes"] * 100 / total
                bits = []
                if d.get("speed"):
                    bits.append(f"{d['speed'] / 1048576:.2f} MiB/s")
                if d.get("eta") is not None:
                    bits.append(f"{d['eta'] // 60:02d}:{d['eta'] % 60:02d} left")
                bits.append(f"{total / 1048576:.0f} MiB")
                self._set("Downloading", "  ·  ".join(bits), pct)
        elif d["status"] == "finished":
            self._set("Processing", "Merging audio and video…", 100)

    def _opts(self, clients=None):
        opts = {
            "nocheckcertificate": True,
            "outtmpl": os.path.join(self.folder.get(), "%(title)s.%(ext)s"),
            "noplaylist": True,
            "quiet": True,
            "no_warnings": True,
            "remote_components": {"ejs:github"},
            "progress_hooks": [self._hook],
        }
        cookies = os.path.join(SCRIPT_DIR, "cookies.txt")
        if os.path.exists(cookies):
            opts["cookiefile"] = cookies
        browser = self.cookies.get()
        if browser != "None":
            opts["cookiesfrombrowser"] = (browser.lower(),)
        if self.kind.get() == "mp3":
            opts.update({
                "format": "bestaudio/best",
                "postprocessors": [{"key": "FFmpegExtractAudio",
                                    "preferredcodec": "mp3", "preferredquality": "192"}],
            })
        else:
            opts.update({
                "format": video_format(self.quality.get()),
                "format_sort": ["res", "fps", "vcodec:h264", "acodec:aac"],
                "merge_output_format": "mp4",
            })
        if clients:
            opts["extractor_args"] = {"youtube": {"player_client": clients}}
        return opts

    def _make_compatible(self, info):
        """QuickTime can't play VP9/AV1; re-encode those to H.264 (hardware encoder)."""
        for d in info.get("requested_downloads") or [info]:
            path, vcodec = d.get("filepath"), d.get("vcodec") or ""
            if not path or vcodec.startswith("avc1") or not os.path.exists(path):
                continue
            self._set("Converting", "Re-encoding to H.264 for QuickTime — about 1–2 min for 4K", 100)
            tmp = path + ".conv.mp4"
            cmd = [shutil.which("ffmpeg") or "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                   "-i", path, "-c:v", "h264_videotoolbox", "-b:v", "16M", "-tag:v", "avc1",
                   "-c:a", "copy", "-movflags", "+faststart", tmp]
            proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
            while proc.poll() is None:
                if self.cancel_ev.is_set():
                    proc.kill()
                    proc.wait()
                    break
                time.sleep(0.2)
            if self.cancel_ev.is_set() or proc.returncode != 0:
                err = proc.stderr.read() if proc.returncode else ""
                if os.path.exists(tmp):
                    os.remove(tmp)
                if self.cancel_ev.is_set():
                    raise yt_dlp.utils.DownloadCancelled()
                raise RuntimeError("Conversion failed: " + err.strip()[-200:])
            os.replace(tmp, path)

    def _cleanup_partials(self):
        """Remove only the partial files this download created."""
        for name in self.touched:
            for p in (name, name + ".part", name + ".ytdl"):
                # a bare final file is only removed if it's an intermediate stream (.f137.mp4)
                if os.path.exists(p) and (p != name or re.search(r"\.f\d+\.", name)):
                    try:
                        os.remove(p)
                    except OSError:
                        pass
        self.touched.clear()

    def _run(self, url, optsets, compat):
        try:
            for n, opts in enumerate(optsets):
                try:
                    with yt_dlp.YoutubeDL(opts) as ydl:
                        info = ydl.extract_info(url, download=True)
                    if compat:
                        self._make_compatible(info)
                    reqs = info.get("requested_downloads") or [info]
                    path = reqs[0].get("filepath")
                    title = info.get("title", "")
                    self._set("Done", title, 100, tone="ok")
                    self.q.put(lambda: self._after_done(path, title))
                    return
                except Exception as e:
                    msg = str(e)
                    retryable = any(k in msg for k in ("403", "Forbidden", "JavaScript runtime", "reloaded"))
                    if n == len(optsets) - 1 or not retryable:
                        raise
                    self._set("Retrying", "Switching client to keep full HD quality…", 0)
        except yt_dlp.utils.DownloadCancelled:
            self._cleanup_partials()
            self._set("Cancelled", "Partial files were removed.", 0)
        except Exception as e:
            if self.cancel_ev.is_set():
                self._cleanup_partials()
                self._set("Cancelled", "Partial files were removed.", 0)
            else:
                msg = str(e)
                if "not a bot" in msg or "Sign in" in msg:
                    msg = ("YouTube wants a login. Choose your browser under 'Login cookies' "
                           "(be signed in to YouTube there) and try again.")
                elif "cookie" in msg.lower() and ("could not" in msg.lower() or "permission" in msg.lower()):
                    msg = ("Couldn't read browser cookies: " + msg[:200] + "  (For Safari, grant "
                           "Terminal Full Disk Access; or pick Chrome/Firefox.)")
                self._set("Something went wrong", msg[:300], 0, tone="err")
        finally:
            self._set(busy=False)


if __name__ == "__main__":
    App().mainloop()
