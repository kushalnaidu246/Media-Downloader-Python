# Media Downloader

A simple desktop app for downloading YouTube and Instagram videos or audio on macOS. Paste a link, choose video or audio, pick a quality, and download.

## Features

- Video (MP4) up to 4K, or audio (MP3)
- Quality picker: Best, 2160p, 1440p, 1080p, 720p, 480p, 360p
- Progress with speed, time remaining and file size
- Cancel any time; partial files are cleaned up
- After a download: Play, Show in Finder, or Download next
- QuickTime-compatible output: 1440p/4K videos (VP9/AV1) are converted to H.264 so they open in QuickTime
- Automatic retry with another client if YouTube cuts off the first one, so you still get HD
- Optional login cookies from your browser for videos that ask you to "confirm you're not a bot"

## Requirements

- macOS (the QuickTime conversion uses the Apple hardware encoder)
- Python 3.10 or newer, from [python.org](https://www.python.org/downloads/)
- Optional: [Deno](https://deno.com), which yt-dlp can use for some YouTube videos

FFmpeg is downloaded automatically on first run.

## How to run

### Option 1: Double-click

1. Open the project folder in Finder.
2. Double-click **YT Downloader.command**.
3. The first run sets up a private environment and installs dependencies (about a minute). After that the app window opens.

If macOS blocks the file, right-click it, choose **Open**, then confirm. You only need to do this once.

### Option 2: From a terminal

```bash
git clone https://github.com/kushalnaidu246/Media-Downloader-Python.git
cd Media-Downloader-Python
./"YT Downloader.command"
```

### Option 3: Manual setup

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python ytgui.py
```

### Command-line version

A text-only version is also included:

```bash
.venv/bin/python ytscript.py
```

## How to use

1. Paste a YouTube or Instagram link (or click **Paste**).
2. Choose **Video · MP4** or **Audio · MP3**.
3. Pick a quality. **Best** gives the highest resolution available; **1080p** is a good balance of size and compatibility.
4. Choose where to save the file (default: `~/Downloads`).
5. Click **Download**. Use **Cancel** to stop.

## Troubleshooting

**"Sign in to confirm you're not a bot"**
YouTube sometimes blocks anonymous downloads. Sign in to YouTube in your browser, then set **Login cookies** in the app to that browser and download again.
- Chrome or Firefox: macOS may ask you to allow keychain access. Click **Allow**.
- Safari: give Terminal **Full Disk Access** in System Settings → Privacy & Security, then restart Terminal.

You can also try a different network, such as a phone hotspot.

**Video is not HD**
Choose **Best** or a specific resolution, and keep **QuickTime-compatible** on. The app retries with other clients automatically if the first one fails.

**"Not compatible with QuickTime Player"**
This happens with 1440p/4K files in the VP9 codec. Keep **QuickTime-compatible** switched on and the app converts them to H.264. Files downloaded earlier can be converted with:

```bash
"$(find .venv -name ffmpeg -type f | head -1)" -i input.mp4 -c:v h264_videotoolbox -b:v 16M -tag:v avc1 -c:a copy -movflags +faststart output.mp4
```

**Downloads stopped working**
YouTube changes often. The launcher updates yt-dlp each time it starts; you can also run `.venv/bin/pip install -U yt-dlp`.

## Project files

| File | Purpose |
| --- | --- |
| `ytgui.py` | The app window |
| `ytscript.py` | Command-line version |
| `YT Downloader.command` | Double-click launcher |
| `requirements.txt` | Python dependencies |

## Notes

Only download content you have the right to download, and follow the terms of the sites you use.
