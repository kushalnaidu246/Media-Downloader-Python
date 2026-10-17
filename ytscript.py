import os
import yt_dlp
import static_ffmpeg

# Ensure Deno (JavaScript runtime required by yt-dlp) is in the PATH
deno_path = os.path.expanduser("~/.deno/bin")
if os.path.exists(deno_path) and deno_path not in os.environ["PATH"]:
    os.environ["PATH"] = deno_path + os.path.pathsep + os.environ["PATH"]

# Automatically configure FFmpeg
static_ffmpeg.add_paths()

print("=" * 40)
print("  YouTube & Instagram Downloader")
print("=" * 40)

choice = input("Download as (1 for mp3 / 4 for mp4): ").strip()

if choice == "1":
    format_choice = "mp3"
elif choice == "4":
    format_choice = "mp4"
else:
    print("Invalid choice!")
    exit()

url = input("Enter YouTube or Instagram URL: ").strip()

ydl_opts = {
    "nocheckcertificate": True,
    "outtmpl": "%(title)s.%(ext)s",
    "noplaylist": True,          # Download only one video
    "quiet": False,
    "remote_components": {"ejs:github"},
}

# Automatically load cookies.txt if present in the same directory
script_dir = os.path.dirname(os.path.abspath(__file__))
cookies_path = os.path.join(script_dir, "cookies.txt")
if os.path.exists(cookies_path):
    ydl_opts["cookiefile"] = cookies_path
    print("[Info] Loaded local cookies.txt file")

if format_choice == "mp3":
    ydl_opts.update({
        "format": "bestaudio/best",
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }
        ],
    })
else:
    ydl_opts.update({
        # Highest resolution wins; H.264/AAC preferred among equal resolutions
        "format": "bv*+ba/b",
        "format_sort": ["res", "fps", "vcodec:h264", "acodec:aac"],
        "merge_output_format": "mp4",
    })

try:
    print("\nDownloading...\n")

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)

    print("\n" + "=" * 40)
    print("Download Completed!")
    print(f"Title : {info['title']}")
    print("=" * 40)

except Exception as e:
    error_str = str(e)
    if "403" in error_str or "Forbidden" in error_str or "JavaScript runtime" in error_str:
        print("\nStandard download failed. Retrying automatically using mobile client fallback...")
        
        # NOTE: ios/android clients only expose 360p (format 18) without a PO token,
        # which is why downloads were not HD. Use clients that still serve HD formats.
        ydl_opts["extractor_args"] = {
            "youtube": {
                "player_client": ["web_embedded", "tv", "mweb"]
            }
        }
        
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
            print("\n" + "=" * 40)
            print("Download Completed (via Mobile Client Fallback)!")
            print(f"Title : {info['title']}")
            print("=" * 40)
        except Exception as retry_e:
            print("\nDownload failed:")
            print(retry_e)
    else:
        print("\nError:")
        print(e)