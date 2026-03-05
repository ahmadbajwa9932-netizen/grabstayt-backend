from updater import auto_update_ytdlp

# Always update yt-dlp first — YouTube changes structures frequently
auto_update_ytdlp()

import sys
import os
from youtube_video_downloader import YouTubeVideoDownloader
from utils import is_valid_youtube_url, normalize_yt_url


def print_banner():
    print("=" * 60)
    print("📥  YouTube Video Downloader v1.0")
    print("=" * 60)
    print("Features:")
    print("• Download videos in ANY quality (1080p60, 720p, 360p, ...)")
    print("• Audio-only download (m4a)")
    print("• Shorts, Live recordings, and regular videos")
    print("• Auto retry on network failures")
    print("• Smart filename handling")
    print("=" * 60)


def print_help():
    print("\n📖 Help:")
    print("Supported URLs:")
    print("  https://www.youtube.com/watch?v=...")
    print("  https://youtu.be/...")
    print("  https://www.youtube.com/shorts/...")
    print("  https://www.youtube.com/live/...")
    print("Commands:")
    print("  help   – show this message")
    print("  test   – check YouTube connectivity")
    print("  exit   – quit")


def choose_quality(qualities: list) -> str:
    """Interactive quality picker. Returns the format_id string."""
    print("\n🎬 Available qualities:")
    for i, q in enumerate(qualities, 1):
        audio_tag = "🔊" if q['has_audio'] else "🔇 (audio added automatically)"
        print(f"  [{i}] {q['label']:<12} {audio_tag}")

    while True:
        choice = input("\nSelect quality number (or press Enter for best): ").strip()
        if choice == '':
            return qualities[0]['format_id']   # best = first entry
        if choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(qualities):
                return qualities[idx]['format_id']
        print("⚠️  Invalid choice, try again.")


def main():
    print_banner()

    try:
        downloader = YouTubeVideoDownloader()
    except Exception as e:
        print(f"❌ Failed to initialize downloader: {e}")
        sys.exit(1)

    print(f"📁 Download folder: {os.path.abspath(downloader.download_folder)}")
    print("\nReady! Type 'help' for usage information.")

    while True:
        try:
            url = input("\n🔗 Enter YouTube URL: ").strip()

            if url.lower() in ('exit', 'quit', 'q'):
                print("👋 Thanks for using YouTube Video Downloader!")
                break
            elif url.lower() == 'help':
                print_help()
                continue
            elif url.lower() == 'test':
                print("🔍 Testing connection to YouTube...")
                if downloader.check_connection():
                    print("✅ Connection successful!")
                else:
                    print("❌ Connection failed. Check your internet.")
                continue
            elif not url:
                print("⚠️  Please enter a URL.")
                continue

            if not is_valid_youtube_url(url):
                print("⚠️  Invalid YouTube URL.")
                print("   Supported: youtube.com/watch, youtu.be, /shorts, /live")
                continue

            url = normalize_yt_url(url)
            print(f"\n🎯 Processing: {url}")

            # ── Step 1: fetch metadata & qualities ────────────────────
            meta = downloader.extract_video_metadata(url)
            if not meta:
                print("💥 Could not fetch video info. Check the URL and try again.")
                continue

            print(f"\n📌 Title    : {meta['title']}")
            print(f"   Channel  : {meta['uploader']}")
            print(f"   Duration : {meta['duration_formatted']}")
            print(f"   Views    : {meta['view_count_formatted']}")

            # ── Step 2: let user pick quality ─────────────────────────
            format_id = choose_quality(meta['available_qualities'])

            # ── Step 3: download ──────────────────────────────────────
            result = downloader.download_video(url, format_id=format_id)

            if result['success']:
                print(f"\n🎉 Download complete!")
                print(f"   Saved as: {result['filename']}")
            else:
                print(f"\n💥 Download failed: {result['error']}")

            print("\n" + "-" * 50)

        except KeyboardInterrupt:
            print("\n\n🛑 Interrupted.")
            continue
        except EOFError:
            print("\n👋 Goodbye!")
            break
        except Exception as e:
            print(f"💥 Unexpected error: {e}")
            continue


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n👋 Goodbye!")
        sys.exit(0)
    except Exception as e:
        print(f"\n💥 Fatal error: {e}")
        sys.exit(1)