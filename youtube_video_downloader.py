import os
import time
import random
import uuid
import tempfile
from yt_dlp import YoutubeDL
from utils import sanitize_title, normalize_yt_url


class YouTubeVideoDownloader:
    def __init__(self):
        # ── Use OS temp folder instead of a project Downloads/ folder
        # This means:
        # 1. No permanent storage used on your server
        # 2. OS automatically cleans it up
        # 3. Works on Render, Koyeb, Railway — all free hosts
        self.download_folder = tempfile.gettempdir()
        self.max_retries = 3
        self.retry_delay = 2
        self.last_extracted_info = None

        # Cleanup any leftover files from previous runs
        self.cleanup_old_files()

    # ─────────────────────────────────────────────
    # CLEANUP — runs on startup + after every download
    # ─────────────────────────────────────────────
    def cleanup_old_files(self):
        """
        Delete grabstayt temp files older than 1 hour.
        We only delete files WE created (prefixed with 'grabstayt_')
        so we don't accidentally delete other system temp files.
        """
        now = time.time()
        one_hour = 60 * 60

        try:
            for filename in os.listdir(self.download_folder):
                # Only touch our own temp files
                if not filename.startswith('grabstayt_'):
                    continue
                file_path = os.path.join(self.download_folder, filename)
                if os.path.isfile(file_path):
                    age = now - os.path.getmtime(file_path)
                    if age > one_hour:
                        try:
                            os.remove(file_path)
                            print(f"🗑️  Cleaned up: {filename}")
                        except Exception as e:
                            print(f"⚠️  Could not delete {filename}: {e}")
        except Exception as e:
            print(f"⚠️  Cleanup error: {e}")

    # ─────────────────────────────────────────────
    # SHARED YT-DLP OPTIONS
    # ─────────────────────────────────────────────
    def _base_opts(self):
        return {
            'quiet': True,
            'no_warnings': True,
            'noplaylist': True,
            'socket_timeout': 30,
            'retries': 5,
            'fragment_retries': 5,
            'skip_unavailable_fragments': True,
            'http_headers': {
                'User-Agent': (
                    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                    'AppleWebKit/537.36 (KHTML, like Gecko) '
                    'Chrome/124.0.0.0 Safari/537.36'
                ),
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'en-us,en;q=0.5',
                'Accept-Encoding': 'gzip,deflate',
                'Connection': 'keep-alive',
            },
        }

    # ─────────────────────────────────────────────
    # METADATA
    # ─────────────────────────────────────────────
    def extract_video_metadata(self, video_url: str):
        """
        Extract full video metadata WITHOUT downloading anything.
        Zero disk usage, zero CPU-heavy work.
        """
        video_url = normalize_yt_url(video_url)
        try:
            print("🔍 Extracting video metadata...")
            opts = {**self._base_opts(), 'extract_flat': False}

            with YoutubeDL(opts) as ydl:
                info = ydl.extract_info(video_url, download=False)
                if not info:
                    return None

                def safe_num(val, default=0):
                    if val is None:
                        return default
                    try:
                        return int(float(val))
                    except (ValueError, TypeError):
                        return default

                formats = info.get('formats', [])
                qualities = self._parse_available_qualities(formats)

                metadata = {
                    'id':                  info.get('id', ''),
                    'title':               info.get('title', 'Unknown Title'),
                    'description':         info.get('description', ''),
                    'uploader':            info.get('uploader', 'Unknown'),
                    'uploader_id':         info.get('uploader_id', ''),
                    'uploader_url':        info.get('uploader_url', ''),
                    'channel':             info.get('channel', ''),
                    'channel_id':          info.get('channel_id', ''),
                    'upload_date':         info.get('upload_date', ''),
                    'duration':            safe_num(info.get('duration')),
                    'view_count':          safe_num(info.get('view_count')),
                    'like_count':          safe_num(info.get('like_count')),
                    'comment_count':       safe_num(info.get('comment_count')),
                    'thumbnail':           info.get('thumbnail', ''),
                    'webpage_url':         info.get('webpage_url', video_url),
                    'tags':                info.get('tags', []),
                    'categories':          info.get('categories', []),
                    'age_limit':           safe_num(info.get('age_limit')),
                    'availability':        info.get('availability', 'unknown'),
                    'is_live':             info.get('is_live', False),
                    'was_live':            info.get('was_live', False),
                    'available_qualities': qualities,
                }

                # Human-readable duration
                d = metadata['duration']
                if d:
                    m, s = divmod(d, 60)
                    h, m = divmod(m, 60)
                    metadata['duration_formatted'] = (
                        f"{h:02d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"
                    )
                else:
                    metadata['duration_formatted'] = 'Unknown'

                metadata['view_count_formatted']    = self.format_number(metadata['view_count'])
                metadata['like_count_formatted']    = self.format_number(metadata['like_count'])
                metadata['comment_count_formatted'] = self.format_number(metadata['comment_count'])

                if metadata['upload_date']:
                    try:
                        from datetime import datetime
                        d_obj = datetime.strptime(metadata['upload_date'], '%Y%m%d')
                        metadata['upload_date_formatted'] = d_obj.strftime('%B %d, %Y')
                    except Exception:
                        metadata['upload_date_formatted'] = metadata['upload_date']
                else:
                    metadata['upload_date_formatted'] = 'Unknown'

                self.last_extracted_info = metadata

                print(f"✅ Metadata extracted → {metadata['title']}")
                print(f"   Views: {metadata['view_count_formatted']}  |  Duration: {metadata['duration_formatted']}")
                print(f"   Available qualities: {[q['label'] for q in qualities]}")

                return metadata

        except Exception as e:
            print(f"❌ Metadata extraction failed: {e}")
            return None

    # ─────────────────────────────────────────────
    # QUALITY PARSING
    # ─────────────────────────────────────────────
    def _parse_available_qualities(self, formats: list) -> list:
        quality_map = {}

        for fmt in formats:
            if fmt.get('vcodec') == 'none' and fmt.get('acodec') == 'none':
                continue

            height  = fmt.get('height') or 0
            fps     = fmt.get('fps') or 0
            vcodec  = fmt.get('vcodec', 'none')
            acodec  = fmt.get('acodec', 'none')
            fmt_id  = fmt.get('format_id', '')

            has_video = vcodec != 'none' and height > 0
            has_audio = acodec != 'none'

            if has_video:
                fps_clean = int(round(fps)) if fps else 30
                label = f"{height}p{fps_clean}" if fps_clean not in (25, 30) else f"{height}p"
                key   = (height, fps_clean)
                tbr   = fmt.get('tbr') or 0

                prev = quality_map.get(key)
                if prev is None or tbr > prev.get('tbr', 0):
                    quality_map[key] = {
                        'label':       label,
                        'height':      height,
                        'fps':         fps_clean,
                        'format_id':   fmt_id,
                        'ext':         'mp4',
                        'has_audio':   has_audio,
                        'tbr':         tbr,
                        'needs_merge': not has_audio,
                    }

        qualities = sorted(
            quality_map.values(),
            key=lambda x: (x['height'], x['fps']),
            reverse=True
        )

        for q in qualities:
            if not q['has_audio']:
                q['format_id'] = f"{q['format_id']}+bestaudio"
                q['has_audio'] = True
            del q['tbr']

        # Audio-only → MP3
        qualities.append({
            'label':       'Audio only (MP3)',
            'height':      0,
            'fps':         0,
            'format_id':   'bestaudio/best',
            'ext':         'mp3',
            'has_audio':   True,
            'needs_merge': False,
        })

        return qualities

    # ─────────────────────────────────────────────
    # DIRECT URL — zero server CPU
    # Best for: 360p / 480p / 720p (needs_merge=False)
    # Browser downloads directly from YouTube CDN
    # Server uses ZERO bandwidth and ZERO CPU
    # ─────────────────────────────────────────────
    def get_direct_url(self, video_url: str, format_id: str) -> dict:
        video_url = normalize_yt_url(video_url)
        try:
            opts = {**self._base_opts(), 'format': format_id}
            with YoutubeDL(opts) as ydl:
                info = ydl.extract_info(video_url, download=False)
                if not info:
                    return {'success': False, 'error': 'Could not extract info',
                            'needs_server_download': True}

                direct_url = info.get('url')
                if direct_url:
                    title      = info.get('title', 'video')
                    safe_title = sanitize_title(title) or 'youtube_video'
                    ext        = info.get('ext', 'mp4')
                    return {
                        'success':  True,
                        'url':      direct_url,
                        'filename': f"{safe_title}.{ext}",
                        'ext':      ext,
                        'title':    title,
                    }

                return {
                    'success':               False,
                    'error':                 'Adaptive format needs server merge',
                    'needs_server_download': True,
                }

        except Exception as e:
            return {'success': False, 'error': str(e), 'needs_server_download': True}

    # ─────────────────────────────────────────────
    # SERVER DOWNLOAD — for 1080p+ and audio only
    #
    # FIX 1: Uses tempfile.gettempdir() — no Downloads/ folder
    # FIX 2: File deleted from server immediately after Flask sends it
    # FIX 3: Audio re-encoded to AAC (-c:a aac) so it plays on
    #         Windows Media Player, iPhone, Android — not just VLC
    # ─────────────────────────────────────────────
    def download_video(self, video_url: str, format_id: str = 'best',
                       is_audio_only: bool = False) -> dict:
        video_url = normalize_yt_url(video_url)

        if not format_id or format_id.strip() == '':
            format_id = 'bestvideo+bestaudio/best'

        for attempt in range(self.max_retries):
            # Prefix with 'grabstayt_' so cleanup only touches our files
            unique_id = f"grabstayt_{str(uuid.uuid4())[:8]}"
            temp_name = f'{unique_id}.%(ext)s'

            try:
                print(f"⬇️  Attempt {attempt + 1}/{self.max_retries} | "
                      f"format: {format_id} | audio_only: {is_audio_only}")

                if is_audio_only:
                    # ── AUDIO → MP3
                    # FFmpegExtractAudio converts to mp3 which plays on
                    # Windows Media Player, iPhone, Android — every device
                    ydl_opts = {
                        **self._base_opts(),
                        'outtmpl':  os.path.join(self.download_folder, temp_name),
                        'format':   'bestaudio/best',
                        'quiet':    False,
                        'postprocessors': [{
                            'key':              'FFmpegExtractAudio',
                            'preferredcodec':   'mp3',
                            'preferredquality': '192',
                        }],
                        'progress_hooks': [self.progress_hook],
                    }
                    final_ext = 'mp3'

                else:
                    # ── VIDEO → MP4 with AAC audio
                    #
                    # KEY FIX for audio issue:
                    # postprocessor_args forces ffmpeg to re-encode audio as AAC
                    # (-c:a aac -b:a 192k) inside the mp4 container.
                    #
                    # Without this, ffmpeg just remuxes opus audio into mp4 which
                    # Windows Media Player and QuickTime cannot decode.
                    # With AAC, every single media player on every platform works.
                    ydl_opts = {
                        **self._base_opts(),
                        'outtmpl':             os.path.join(self.download_folder, temp_name),
                        'format':              format_id,
                        'quiet':               False,
                        'merge_output_format': 'mp4',
                        # Re-encode audio to AAC — this is the audio fix
                        'postprocessor_args': {
                            'ffmpeg': [
                                '-c:v', 'copy',    # copy video stream (no re-encode = fast)
                                '-c:a', 'aac',     # re-encode audio to AAC
                                '-b:a', '192k',    # 192kbps audio quality
                            ]
                        },
                        'progress_hooks': [self.progress_hook],
                    }
                    final_ext = 'mp4'

                with YoutubeDL(ydl_opts) as ydl:
                    print("🔍 Fetching video info...")
                    info = ydl.extract_info(video_url, download=False)

                    if not info:
                        raise Exception("Could not extract video information")

                    availability = info.get('availability', '')
                    if availability in ('private', 'premium_only', 'subscriber_only'):
                        return {'success': False,
                                'error': f'Video not accessible ({availability})'}

                    title      = info.get('title', f'video_{int(time.time())}')
                    safe_title = sanitize_title(title) or f'grabstayt_{int(time.time())}'
                    final_path = self._unique_path(safe_title, final_ext)

                    print("📥 Downloading...")
                    ydl.download([video_url])

                    # Find our temp file
                    downloaded = None
                    for f in os.listdir(self.download_folder):
                        if f.startswith(unique_id):
                            downloaded = os.path.join(self.download_folder, f)
                            break

                    if not downloaded or not os.path.exists(downloaded):
                        raise Exception("Downloaded file not found in temp folder")

                    try:
                        os.rename(downloaded, final_path)
                    except OSError:
                        final_path = downloaded

                    print(f"✅ Ready to stream → {final_path}")
                    # NOTE: Flask's app.py deletes this file immediately after
                    # sending it to the browser — no permanent storage used
                    return {
                        'success':   True,
                        'file_path': final_path,
                        'filename':  os.path.basename(final_path),
                        'ext':       final_ext,
                    }

            except Exception as e:
                msg = str(e).lower()

                if 'private' in msg or 'not accessible' in msg:
                    return {'success': False, 'error': str(e)}
                if 'getaddrinfo' in msg or 'failed to resolve' in msg:
                    print(f"🌐 DNS error on attempt {attempt + 1}")
                elif 'timeout' in msg or 'timed out' in msg:
                    print(f"⏱️  Timeout on attempt {attempt + 1}")
                elif 'ffmpeg' in msg:
                    print(f"🔧 ffmpeg error on attempt {attempt + 1}: {e}")
                else:
                    print(f"❌ Error on attempt {attempt + 1}: {e}")

                if attempt < self.max_retries - 1:
                    wait = self.retry_delay * (attempt + 1) + random.uniform(1, 3)
                    print(f"⏳ Retrying in {wait:.1f}s...")
                    time.sleep(wait)
                else:
                    return {'success': False,
                            'error': f'Failed after {self.max_retries} attempts: {e}'}

        return {'success': False, 'error': 'Unknown error'}

    # ─────────────────────────────────────────────
    # HELPERS
    # ─────────────────────────────────────────────
    def _unique_path(self, safe_title: str, ext: str) -> str:
        """Generate a unique temp file path using our grabstayt_ prefix."""
        path = os.path.join(
            self.download_folder,
            f"grabstayt_{safe_title}.{ext}"
        )
        counter = 1
        while os.path.exists(path):
            path = os.path.join(
                self.download_folder,
                f"grabstayt_{safe_title}_{counter}.{ext}"
            )
            counter += 1
        return path

    def format_number(self, num) -> str:
        if not num:
            return '0'
        try:
            num = int(float(num))
            if num >= 1_000_000_000:
                return f"{num / 1_000_000_000:.1f}B"
            if num >= 1_000_000:
                return f"{num / 1_000_000:.1f}M"
            if num >= 1_000:
                return f"{num / 1_000:.1f}K"
            return f"{num:,}"
        except (ValueError, TypeError):
            return str(num)

    def check_connection(self) -> bool:
        try:
            import requests
            r = requests.get('https://www.youtube.com', timeout=10,
                             headers={'User-Agent': 'Mozilla/5.0'})
            return r.status_code == 200
        except Exception:
            return False

    @staticmethod
    def progress_hook(d):
        if d['status'] == 'downloading':
            total      = d.get('total_bytes') or d.get('total_bytes_estimate')
            downloaded = d.get('downloaded_bytes', 0)
            speed      = d.get('speed', 0)
            speed_str  = f" at {speed/1024:.1f} KB/s" if speed else ""
            if total:
                pct = downloaded / total * 100
                print(f"\r   {pct:.1f}% completed{speed_str}   ", end='', flush=True)
            else:
                print(f"\r   {downloaded/1024:.1f} KB downloaded{speed_str}   ",
                      end='', flush=True)
        elif d['status'] == 'finished':
            print(f"\n✓  Segment done: {d.get('filename', '')}")