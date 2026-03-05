"""
GrabstaYT - Flask API
=====================
Endpoints:
  POST /api/metadata          → extract video info + available qualities
  POST /api/get-direct-url    → return YouTube CDN URL (360p/480p/720p) — zero server CPU
  POST /api/download          → server-side download (1080p+ / audio-only)
  GET  /api/file/<filename>   → serve the downloaded file to browser
  GET  /api/health            → health check
  DELETE /api/cleanup         → manual cleanup trigger
"""

import os
import threading
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS

from updater import auto_update_ytdlp
from youtube_video_downloader import YouTubeVideoDownloader
from utils import is_valid_youtube_url, normalize_yt_url

# ── Auto-update yt-dlp on startup ──────────────────────────────────────────────
auto_update_ytdlp()

# ── Flask app setup ────────────────────────────────────────────────────────────
app = Flask(__name__)

# Allow requests from ANY origin (your frontend domain)
# When you go live, replace "*" with your actual frontend URL e.g.:
# CORS(app, origins=["https://grabstayt.netlify.app"])
CORS(app, origins="*")

# ── Single shared downloader instance ─────────────────────────────────────────
# One instance handles all requests — cleanup runs on startup automatically
downloader = YouTubeVideoDownloader()


# ══════════════════════════════════════════════════════════════════════════════
# HELPER
# ══════════════════════════════════════════════════════════════════════════════

def error_response(message: str, status: int = 400):
    return jsonify({'success': False, 'error': message}), status


# ══════════════════════════════════════════════════════════════════════════════
# HEALTH CHECK
# ══════════════════════════════════════════════════════════════════════════════

@app.route('/api/health', methods=['GET'])
def health():
    """Simple health check — frontend can ping this to wake up the server."""
    return jsonify({
        'success': True,
        'status':  'running',
        'message': 'GrabstaYT API is live 🚀'
    })


# ══════════════════════════════════════════════════════════════════════════════
# STEP 1 — METADATA  (frontend calls this when user pastes URL)
# ══════════════════════════════════════════════════════════════════════════════

@app.route('/api/metadata', methods=['POST'])
def get_metadata():
    """
    Request body:  { "url": "https://youtube.com/watch?v=..." }

    Response:
    {
      "success": true,
      "title": "...",
      "thumbnail": "...",
      "duration_formatted": "03:45",
      "view_count_formatted": "1.2M",
      "uploader": "...",
      "available_qualities": [
        { "label": "1080p60", "format_id": "137+251", "needs_merge": true,  "ext": "mp4" },
        { "label": "720p",    "format_id": "22",       "needs_merge": false, "ext": "mp4" },
        { "label": "360p",    "format_id": "18",       "needs_merge": false, "ext": "mp4" },
        { "label": "Audio only (MP3)", "format_id": "bestaudio/best", ... }
      ]
    }
    """
    data = request.get_json(silent=True)
    if not data or not data.get('url'):
        return error_response('No URL provided')

    url = data['url'].strip()

    if not is_valid_youtube_url(url):
        return error_response('Invalid YouTube URL. Supported: youtube.com/watch, youtu.be, /shorts, /live')

    url = normalize_yt_url(url)

    metadata = downloader.extract_video_metadata(url)

    if not metadata:
        return error_response('Could not fetch video info. The video may be private, age-restricted, or unavailable.', 422)

    # Return only what the frontend needs (keep response lean)
    return jsonify({
        'success':               True,
        'id':                    metadata['id'],
        'title':                 metadata['title'],
        'thumbnail':             metadata['thumbnail'],
        'uploader':              metadata['uploader'],
        'duration_formatted':    metadata['duration_formatted'],
        'view_count_formatted':  metadata['view_count_formatted'],
        'like_count_formatted':  metadata['like_count_formatted'],
        'upload_date_formatted': metadata['upload_date_formatted'],
        'is_live':               metadata['is_live'],
        'availability':          metadata['availability'],
        'available_qualities':   metadata['available_qualities'],
    })


# ══════════════════════════════════════════════════════════════════════════════
# STEP 2a — DIRECT URL  (zero server CPU — for 360p / 480p / 720p)
# ══════════════════════════════════════════════════════════════════════════════

@app.route('/api/get-direct-url', methods=['POST'])
def get_direct_url():
    """
    Use this for qualities where needs_merge = false.
    Returns YouTube's own CDN URL → browser downloads directly.
    Your server uses ZERO bandwidth. Perfect for free hosting.

    Request body:
    {
      "url":       "https://youtube.com/watch?v=...",
      "format_id": "18"
    }

    Response:
    {
      "success":  true,
      "url":      "https://...googlevideo.com/...",
      "filename": "video_title.mp4",
      "ext":      "mp4"
    }
    """
    data = request.get_json(silent=True)
    if not data or not data.get('url') or not data.get('format_id'):
        return error_response('url and format_id are required')

    url       = normalize_yt_url(data['url'].strip())
    format_id = data['format_id'].strip()

    if not is_valid_youtube_url(url):
        return error_response('Invalid YouTube URL')

    result = downloader.get_direct_url(url, format_id)

    if not result['success']:
        # If direct URL fails (e.g. needs merge), tell frontend to use /api/download instead
        return jsonify({
            'success':               False,
            'error':                 result.get('error', 'Could not get direct URL'),
            'needs_server_download': result.get('needs_server_download', True),
        }), 422

    return jsonify(result)


# ══════════════════════════════════════════════════════════════════════════════
# STEP 2b — SERVER DOWNLOAD  (for 1080p+ and audio-only)
# ══════════════════════════════════════════════════════════════════════════════

@app.route('/api/download', methods=['POST'])
def download_video():
    """
    Use this when needs_merge = true (1080p / 1080p60 / 4K)
    or for audio-only downloads.
    Server downloads + merges with ffmpeg → sends file to browser.

    Request body:
    {
      "url":          "https://youtube.com/watch?v=...",
      "format_id":    "137+251",
      "is_audio_only": false
    }

    Response: the actual file (video/mp4 or audio/mpeg)
    """
    data = request.get_json(silent=True)
    if not data or not data.get('url'):
        return error_response('url is required')

    url           = normalize_yt_url(data['url'].strip())
    format_id     = data.get('format_id', 'bestvideo+bestaudio/best').strip()
    is_audio_only = bool(data.get('is_audio_only', False))

    if not is_valid_youtube_url(url):
        return error_response('Invalid YouTube URL')

    result = downloader.download_video(url, format_id=format_id, is_audio_only=is_audio_only)

    if not result['success']:
        return error_response(result.get('error', 'Download failed'), 500)

    file_path = result['file_path']
    filename  = result['filename']
    ext       = result.get('ext', 'mp4')

    if not os.path.exists(file_path):
        return error_response('File not found after download', 500)

    # Determine MIME type
    mime_type = 'audio/mpeg' if ext == 'mp3' else 'video/mp4'

    # Stream file to browser then delete from server (saves disk space)
    def stream_and_delete():
        try:
            os.remove(file_path)
            print(f"🗑️  Deleted after serving: {filename}")
        except Exception as e:
            print(f"⚠️  Could not delete {filename}: {e}")

    response = send_file(
        file_path,
        mimetype=mime_type,
        as_attachment=True,
        download_name=filename,
    )

    # Schedule file deletion after response is sent
    threading.Timer(2.0, stream_and_delete).start()

    return response


# ══════════════════════════════════════════════════════════════════════════════
# MANUAL CLEANUP
# ══════════════════════════════════════════════════════════════════════════════

@app.route('/api/cleanup', methods=['DELETE'])
def cleanup():
    """Manually trigger cleanup of old files. Call this from a cron job."""
    try:
        downloader.cleanup_old_files()
        return jsonify({'success': True, 'message': 'Cleanup completed'})
    except Exception as e:
        return error_response(str(e), 500)


# ══════════════════════════════════════════════════════════════════════════════
# ERROR HANDLERS
# ══════════════════════════════════════════════════════════════════════════════

@app.errorhandler(404)
def not_found(e):
    return jsonify({'success': False, 'error': 'Endpoint not found'}), 404

@app.errorhandler(405)
def method_not_allowed(e):
    return jsonify({'success': False, 'error': 'Method not allowed'}), 405

@app.errorhandler(500)
def internal_error(e):
    return jsonify({'success': False, 'error': 'Internal server error'}), 500


# ══════════════════════════════════════════════════════════════════════════════
# RUN
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    print("=" * 55)
    print("🚀 GrabstaYT Flask API starting...")
    print("=" * 55)
    print("Endpoints:")
    print("  GET  /api/health")
    print("  POST /api/metadata")
    print("  POST /api/get-direct-url")
    print("  POST /api/download")
    print("  DELETE /api/cleanup")
    print("=" * 55)
    # debug=False in production, debug=True for local testing
    app.run(host='0.0.0.0', port=5000, debug=True)