import yt_dlp
import static_ffmpeg

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
}

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
        "format": "bv*+ba/b",
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
    print("\nError:")
    print(e)