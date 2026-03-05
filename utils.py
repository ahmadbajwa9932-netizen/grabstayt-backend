import re


# ─────────────────────────────────────────────────────────────
# FILENAME SANITIZER
# ─────────────────────────────────────────────────────────────
def sanitize_title(title: str) -> str:
    """
    Make a video title safe for use as a filename.
    - Strips OS-unsafe characters
    - Drops non-ASCII (emojis etc.)
    - Collapses whitespace → underscores
    - Caps at 80 characters
    """
    safe = re.sub(r'[\\/*?:"<>|]', '', title)
    safe = safe.encode('ascii', 'ignore').decode('ascii')
    safe = re.sub(r'\s+', '_', safe.strip())
    return safe[:80]


# ─────────────────────────────────────────────────────────────
# URL VALIDATION
# ─────────────────────────────────────────────────────────────
def is_valid_youtube_url(url: str) -> bool:
    """
    Accept the main YouTube URL patterns:
      https://www.youtube.com/watch?v=XXXXXXXXXXX
      https://youtu.be/XXXXXXXXXXX
      https://www.youtube.com/shorts/XXXXXXXXXXX
      https://www.youtube.com/live/XXXXXXXXXXX
      https://m.youtube.com/watch?v=XXXXXXXXXXX
    """
    patterns = [
        r'(https?://)?(www\.|m\.)?youtube\.com/watch\?.*v=[\w-]{11}',
        r'(https?://)?youtu\.be/[\w-]{11}',
        r'(https?://)?(www\.)?youtube\.com/shorts/[\w-]{11}',
        r'(https?://)?(www\.)?youtube\.com/live/[\w-]{11}',
        r'(https?://)?(www\.)?youtube\.com/embed/[\w-]{11}',
    ]
    return any(re.search(p, url) for p in patterns)


# ─────────────────────────────────────────────────────────────
# URL NORMALIZER
# ─────────────────────────────────────────────────────────────
def normalize_yt_url(url: str) -> str:
    """
    Normalize any YouTube URL variant to the canonical watch URL.

    Examples
    --------
    youtu.be/dQw4w9WgXcQ          → https://www.youtube.com/watch?v=dQw4w9WgXcQ
    youtube.com/shorts/dQw4w9WgXcQ → https://www.youtube.com/watch?v=dQw4w9WgXcQ
    youtube.com/live/dQw4w9WgXcQ   → https://www.youtube.com/watch?v=dQw4w9WgXcQ
    youtube.com/watch?v=...&list=... → keeps the v= only (strips playlist noise)
    m.youtube.com/watch?v=...       → https://www.youtube.com/watch?v=...
    """
    url = url.strip()

    # ── Extract video ID ──────────────────────────────────────
    video_id = None

    # youtu.be/<id>
    m = re.search(r'youtu\.be/([\w-]{11})', url)
    if m:
        video_id = m.group(1)

    # /shorts/<id>  or  /live/<id>  or  /embed/<id>
    if not video_id:
        m = re.search(r'youtube\.com/(?:shorts|live|embed)/([\w-]{11})', url)
        if m:
            video_id = m.group(1)

    # standard watch?v=<id>
    if not video_id:
        m = re.search(r'[?&]v=([\w-]{11})', url)
        if m:
            video_id = m.group(1)

    if video_id:
        return f'https://www.youtube.com/watch?v={video_id}'

    # Fallback: return as-is (yt-dlp may still handle it)
    return url