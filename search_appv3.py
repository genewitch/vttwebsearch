#!/usr/bin/env python3
"""
Simple Flask web app to search captions.db and stream audio segments as MP3.
Uses temporary files to support byte‑range requests for smooth playback.
Includes debug output for FFmpeg conversion and file handling.
"""

import sqlite3
import argparse
import re
import html
import os
import subprocess
import tempfile
import shlex
from flask import Flask, request, render_template_string, abort, send_file, after_this_request

app = Flask(__name__)
DATABASE = 'allcaptions.db'

# ----- CONFIGURATION -----
MEDIA_DIR = "/mnt/syno/music/music/SERVER/"      # <-- change this
MEDIA_EXTENSIONS = ['.mp4', '.mkv', '.webm', '.m4a', '.mp3', '.opus']
# -------------------------

HTML_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head>
    <title>Caption Search</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 2em; }
        input[type="text"] { width: 300px; padding: 8px; font-size: 1em; }
        input[type="submit"] { padding: 8px 16px; font-size: 1em; }
        table { border-collapse: collapse; width: 100%; margin-top: 1em; }
        th, td { border: 1px solid #ccc; padding: 8px; text-align: left; vertical-align: top; }
        th { background-color: #f4f4f4; }
        .highlight { background-color: #ffff99; }
        .timestamp { font-family: monospace; white-space: nowrap; }
        .filename { font-weight: bold; }
        audio { width: 200px; }
    </style>
</head>
<body>
    <h1>Search WebVTT Captions</h1>
    <form method="GET" action="/">
        <input type="text" name="q" placeholder="Enter search term..." value="{{ query }}" required>
        <input type="submit" value="Search">
    </form>

    {% if query %}
        <p>Found {{ results|length }} result(s) for "<strong>{{ query }}</strong>".</p>
        {% if results %}
        <table>
            <thead>
                <tr>
                    <th>File</th>
                    <th>Start Time</th>
                    <th>End Time</th>
                    <th>Caption Text</th>
                    <th>Audio</th>
                </tr>
            </thead>
            <tbody>
            {% for row in results %}
                <tr>
                    <td class="filename">{{ row.filename }}</td>
                    <td class="timestamp">{{ row.start_time }}</td>
                    <td class="timestamp">{{ row.end_time }}</td>
                    <td>{{ row.highlighted_text|safe }}</td>
                    <td>
                        <audio controls preload="none">
                            <source src="{{ url_for('audio_segment', basename=row.basename, start=row.start_time, end=row.end_time) }}" type="audio/mpeg">
                            Your browser does not support the audio element.
                        </audio>
                    </td>
                </tr>
            {% endfor %}
            </tbody>
        </table>
        {% else %}
        <p>No captions found.</p>
        {% endif %}
    {% endif %}
</body>
</html>
'''

def get_db_connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def highlight_text(text, term):
    escaped_text = html.escape(text)
    escaped_term = html.escape(term)
    pattern = re.compile(re.escape(escaped_term), re.IGNORECASE)
    return pattern.sub(f'<span class="highlight">{escaped_term}</span>', escaped_text)

def timestamp_to_seconds(ts):
    """Convert 'HH:MM:SS.mmm' to float seconds."""
    parts = ts.split(':')
    if len(parts) == 3:
        h, m, s = parts
        return int(h) * 3600 + int(m) * 60 + float(s)
    elif len(parts) == 2:
        m, s = parts
        return int(m) * 60 + float(s)
    else:
        return float(ts)

def find_media_file(basename):
    for ext in MEDIA_EXTENSIONS:
        candidate = os.path.join(MEDIA_DIR, basename + ext)
        if os.path.isfile(candidate):
            return candidate
    return None

def generate_audio_clip(media_path, start_sec, end_sec):
    """
    Generate a temporary MP3 file for the requested segment.
    Returns the temporary file path.
    """
    prestart = start_sec - 5
    duration = end_sec - prestart + 5
    fd, temp_path = tempfile.mkstemp(suffix='.mp3')
    os.close(fd)

    # Build the command with -y to overwrite the existing temp file
    cmd_parts = [
        'ffmpeg',
        '-y',                      # Overwrite output without asking
        '-ss', str(prestart),
        '-i', media_path,
        '-t', str(duration),
        '-vn',
        '-c:a', 'libmp3lame',
        '-b:a', '192k',
        '-f', 'mp3',
        temp_path
    ]
    cmd_str = ' '.join(shlex.quote(part) for part in cmd_parts)

    print(f"[DEBUG] Generating MP3 from: {media_path}")
    print(f"[DEBUG] Start: {start_sec}s, Duration: {duration}s")
    print(f"[DEBUG] Running command (shell): {cmd_str}")
    print(f"[DEBUG] Temporary output file: {temp_path}")

    result = subprocess.run(cmd_str, shell=True, capture_output=True, text=True)

    if result.stderr:
        print(f"[DEBUG] FFmpeg stderr:\n{result.stderr}")
    if result.stdout:
        print(f"[DEBUG] FFmpeg stdout:\n{result.stdout}")

    if result.returncode != 0:
        print(f"[ERROR] FFmpeg failed with return code {result.returncode}")
        if os.path.exists(temp_path):
            os.unlink(temp_path)
        raise RuntimeError(f"ffmpeg failed: {result.stderr}")

    if not os.path.exists(temp_path) or os.path.getsize(temp_path) == 0:
        print(f"[ERROR] FFmpeg produced an empty/missing file.")
        if os.path.exists(temp_path):
            os.unlink(temp_path)
        raise RuntimeError(f"ffmpeg produced empty output. stderr:\n{result.stderr}")

    print(f"[DEBUG] FFmpeg succeeded. File size: {os.path.getsize(temp_path)} bytes")
    return temp_path

@app.route('/')
def index():
    query = request.args.get('q', '').strip()
    results = []
    if query:
        conn = get_db_connection()
        cursor = conn.execute(
            "SELECT filename, start_time, end_time, text FROM captions WHERE text LIKE ? ORDER BY filename, cue_index",
            ('%' + query + '%',)
        )
        rows = cursor.fetchall()
        conn.close()
        for row in rows:
            basename = os.path.splitext(row['filename'])[0]
            results.append({
                'filename': row['filename'],
                'basename': basename,
                'start_time': row['start_time'],
                'end_time': row['end_time'],
                'highlighted_text': highlight_text(row['text'], query)
            })
    return render_template_string(HTML_TEMPLATE, query=query, results=results)

@app.route('/audio/<basename>/<start>/<end>')
def audio_segment(basename, start, end):
    print(f"[DEBUG] Received request for basename={basename}, start={start}, end={end}")

    media_path = find_media_file(basename)
    if media_path is None:
        print(f"[ERROR] Media file not found for basename: {basename}")
        abort(404, description="Media file not found")
    else:
        print(f"[DEBUG] Found media file: {media_path}")

    try:
        start_sec = timestamp_to_seconds(start)
        end_sec = timestamp_to_seconds(end)
        if start_sec >= end_sec:
            print(f"[ERROR] Invalid time range: start {start_sec} >= end {end_sec}")
            abort(400, description="Invalid time range")
    except ValueError as e:
        print(f"[ERROR] Timestamp conversion error: {e}")
        abort(400, description="Invalid timestamp format")

    try:
        temp_path = generate_audio_clip(media_path, start_sec, end_sec)
        print(f"[DEBUG] Temporary MP3 created: {temp_path}")
    except RuntimeError as e:
        print(f"[ERROR] Audio generation failed: {e}")
        abort(500, description=str(e))

    # Delete the temporary file after the response is sent
    @after_this_request
    def cleanup(response):
        try:
            os.unlink(temp_path)
            print(f"[DEBUG] Cleaned up temporary file: {temp_path}")
        except Exception as e:
            print(f"[ERROR] Failed to delete temporary file {temp_path}: {e}")
        return response

    print(f"[DEBUG] Serving MP3 file: {temp_path}")
    return send_file(
        temp_path,
        mimetype='audio/mpeg',
        as_attachment=False,
        download_name=f"{basename}_{start}-{end}.mp3"
    )

def main():
    global DATABASE, MEDIA_DIR

    parser = argparse.ArgumentParser()
    parser.add_argument('--db', default='captions.db')
    parser.add_argument('--port', type=int, default=5000)
    parser.add_argument('--host', default='0.0.0.0')
    parser.add_argument('--media-dir', default=MEDIA_DIR, help='Directory containing media files')
    args = parser.parse_args()
    DATABASE = args.db
    MEDIA_DIR = args.media_dir
    app.run(host=args.host, port=args.port, debug=True)

if __name__ == '__main__':
    main()
