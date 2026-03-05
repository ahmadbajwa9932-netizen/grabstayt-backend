import subprocess
import sys


def auto_update_ytdlp():
    """
    Silently upgrade yt-dlp to the latest version every time the app starts.
    This is the #1 reason YouTube downloaders stop working —
    YouTube changes its signature algorithm frequently and yt-dlp patches it fast.
    Keeping it latest = always working.
    """
    try:
        print("🔄 Checking for yt-dlp updates...")
        result = subprocess.run(
            [sys.executable, '-m', 'pip', 'install', '-U', 'yt-dlp', '--quiet'],
            capture_output=True,
            text=True
        )
        if result.returncode == 0:
            print("✅ yt-dlp is up to date.")
        else:
            print(f"⚠️  yt-dlp update warning: {result.stderr.strip()}")
    except Exception as e:
        print(f"⚠️  Auto-update failed (continuing anyway): {e}")