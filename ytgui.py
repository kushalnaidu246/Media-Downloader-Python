import os
import queue
import re
import shutil
import subprocess
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

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
QUALITIES = ["Best", "2160p", "1440p", "1080p", "720p", "480p", "360p"]


def video_format(quality):
    cap = "" if quality == "Best" else f"[height<={quality[:-1]}]"
    # Resolution wins; format_sort then prefers H.264/AAC among equal resolutions
    return f"bv*{cap}+ba/b{cap}"


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("YouTube & Instagram Downloader")
        self.geometry("700x300")
        self.resizable(False, False)

        self.url = tk.StringVar()
        self.kind = tk.StringVar(value="mp4")
        self.quality = tk.StringVar(value="Best")
        self.compat = tk.BooleanVar(value=True)
        self.folder = tk.StringVar(value=os.path.expanduser("~/Downloads"))
        self.status = tk.StringVar(value="Paste a link and press Download.")

        pad = {"padx": 14, "pady": 6}
        frm = ttk.Frame(self)
        frm.pack(fill="both", expand=True, padx=4, pady=4)
        frm.columnconfigure(1, weight=1)

        ttk.Label(frm, text="URL").grid(row=0, column=0, sticky="w", **pad)
        entry = ttk.Entry(frm, textvariable=self.url)
        entry.grid(row=0, column=1, columnspan=2, sticky="ew", **pad)
        entry.focus()

        ttk.Label(frm, text="Format").grid(row=1, column=0, sticky="w", **pad)
        kinds = ttk.Frame(frm)
        kinds.grid(row=1, column=1, columnspan=2, sticky="w", **pad)
        ttk.Radiobutton(kinds, text="Video (mp4)", variable=self.kind, value="mp4",
                        command=self._toggle).pack(side="left", padx=(0, 12))
        ttk.Radiobutton(kinds, text="Audio (mp3)", variable=self.kind, value="mp3",
                        command=self._toggle).pack(side="left")

        ttk.Label(frm, text="Quality").grid(row=2, column=0, sticky="w", **pad)
        self.qbox = ttk.Combobox(frm, textvariable=self.quality, values=QUALITIES,
                                 state="readonly", width=10)
        self.qbox.grid(row=2, column=1, sticky="w", **pad)

        ttk.Checkbutton(frm, text="Make QuickTime-compatible (converts 1440p/4K to H.264)",
                        variable=self.compat).grid(row=2, column=2, sticky="w", padx=14)

        ttk.Label(frm, text="Save to").grid(row=3, column=0, sticky="w", **pad)
        ttk.Entry(frm, textvariable=self.folder, state="readonly", width=40).grid(
            row=3, column=1, sticky="ew", **pad)
        ttk.Button(frm, text="Browse…", command=self._browse).grid(row=3, column=2, **pad)

        self.bar = ttk.Progressbar(frm, maximum=100)
        self.bar.grid(row=4, column=0, columnspan=3, sticky="ew", **pad)
        ttk.Label(frm, textvariable=self.status, wraplength=520).grid(
            row=5, column=0, columnspan=3, sticky="w", **pad)

        btns = ttk.Frame(frm)
        btns.grid(row=6, column=0, columnspan=3, **pad)
        self.btn = ttk.Button(btns, text="Download", command=self._start)
        self.btn.pack(side="left", padx=6)
        self.cancel_btn = ttk.Button(btns, text="Cancel", command=self._cancel, state="disabled")
        self.cancel_btn.pack(side="left", padx=6)
        self.cancel_ev = threading.Event()
        self.touched = set()  # files written by the current download
        self.bind("<Return>", lambda e: self._start())

        self.q = queue.Queue()
        self._poll()

    def _poll(self):
        try:
            while True:
                self.q.get_nowait()()
        except queue.Empty:
            pass
        self.after(100, self._poll)

    def _toggle(self):
        self.qbox.configure(state="readonly" if self.kind.get() == "mp4" else "disabled")

    def _browse(self):
        d = filedialog.askdirectory(initialdir=self.folder.get())
        if d:
            self.folder.set(d)

    def _set(self, text=None, pct=None, busy=None):
        """Thread-safe UI update (applied by the main thread via _poll)."""
        def apply():
            if text is not None:
                self.status.set(text)
            if pct is not None:
                self.bar["value"] = pct
            if busy is not None:
                self.btn.configure(state="disabled" if busy else "normal")
                self.cancel_btn.configure(state="normal" if busy else "disabled")
        self.q.put(apply)

    def _cancel(self):
        self.cancel_ev.set()
        self.cancel_btn.configure(state="disabled")
        self.status.set("Cancelling…")

    def _after_done(self, path, title):
        """Ask whether to play the file or start the next download."""
        win = tk.Toplevel(self)
        win.title("Download complete")
        win.transient(self)
        win.resizable(False, False)
        ttk.Label(win, text=f"Finished:\n{title}", wraplength=380, justify="center").pack(
            padx=20, pady=(18, 10))

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
            self.bar["value"] = 0
            self.status.set("Paste the next link and press Download.")

        row = ttk.Frame(win)
        row.pack(pady=(4, 16))
        ttk.Button(row, text="▶ Play", command=play).pack(side="left", padx=5)
        ttk.Button(row, text="Show in Finder", command=show).pack(side="left", padx=5)
        ttk.Button(row, text="Download next", command=nxt).pack(side="left", padx=5)
        win.protocol("WM_DELETE_WINDOW", win.destroy)
        win.grab_set()

    def _start(self):
        url = self.url.get().strip()
        if not url:
            messagebox.showwarning("Missing URL", "Please paste a YouTube or Instagram link.")
            return
        if str(self.btn["state"]) == "disabled":
            return
        self.cancel_ev.clear()
        self.touched.clear()
        self._set("Starting…", 0, True)
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
                speed = d.get("speed")
                spd = f"  {speed / 1048576:.2f} MiB/s" if speed else ""
                self._set(f"Downloading… {pct:.0f}%{spd}", pct)
        elif d["status"] == "finished":
            self._set("Processing (merging/converting)…", 100)

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
            self._set("Converting to H.264 for QuickTime (about 1–2 min for 4K)…", 100)
            tmp = path + ".conv.mp4"
            self.touched.add(tmp + ".part")  # removed on cancel via name+".part"? no: handled below
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
                    self._set(f"Done: {title}", 100)
                    self.q.put(lambda: self._after_done(path, title))
                    return
                except Exception as e:
                    msg = str(e)
                    retryable = any(k in msg for k in ("403", "Forbidden", "JavaScript runtime", "reloaded"))
                    if n == len(optsets) - 1 or not retryable:
                        raise
                    self._set("Retrying with another client for HD…", 0)
        except yt_dlp.utils.DownloadCancelled:
            self._cleanup_partials()
            self._set("Cancelled.", 0)
        except Exception as e:
            if self.cancel_ev.is_set():
                self._cleanup_partials()
                self._set("Cancelled.", 0)
            else:
                self._set(f"Error: {str(e)[:300]}", 0)
        finally:
            self._set(busy=False)


if __name__ == "__main__":
    App().mainloop()
