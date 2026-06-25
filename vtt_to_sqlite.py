#!/usr/bin/env python3
"""
WebVTT to SQLite Importer

Usage:
    python vtt_to_sqlite.py /path/to/vtt/directory [--db database.db]

Scans all .vtt files in the given directory, parses each caption cue,
and inserts the filename, cue index, start/end timestamps, and text into
an SQLite database.

The table schema is:
    captions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        filename TEXT NOT NULL,
        cue_index INTEGER,
        start_time TEXT,
        end_time TEXT,
        text TEXT
    )

Before importing a file, all existing rows with that filename are removed,
so re‑running the script on the same directory is safe.
"""

import os
import sys
import sqlite3
import argparse
import re

# Regular expression to match a WebVTT timestamp line (start --> end)
TIMING_LINE_RE = re.compile(r'^(\d{2}:\d{2}:\d{2}\.\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2}\.\d{3})')


def parse_vtt(file_path):
    """
    Parse a WebVTT file and yield cue dictionaries.

    Each cue dict has keys:
        - start_time (str)
        - end_time   (str)
        - text       (str)   -- may contain newlines
    """
    with open(file_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    cues = []
    i = 0
    # Skip any leading lines until we find a timing line (skip header)
    while i < len(lines) and not TIMING_LINE_RE.match(lines[i].strip()):
        i += 1

    while i < len(lines):
        # Skip empty lines
        if not lines[i].strip():
            i += 1
            continue

        # Check if current line is a timing line
        match = TIMING_LINE_RE.match(lines[i].strip())
        if match:
            start, end = match.groups()
            i += 1
            # Collect text lines until next blank line or EOF
            text_lines = []
            while i < len(lines) and lines[i].strip() != '':
                text_lines.append(lines[i].rstrip('\n'))
                i += 1
            # Join text lines with newline (preserve original formatting)
            text = '\n'.join(text_lines)
            cues.append({
                'start_time': start,
                'end_time': end,
                'text': text
            })
        else:
            # Not a timing line – might be an identifier, skip it
            i += 1

    return cues


def import_directory(vtt_dir, db_path):
    """Scan vtt_dir for .vtt files and insert their cues into the database."""
    if not os.path.isdir(vtt_dir):
        print(f"Error: '{vtt_dir}' is not a valid directory.")
        sys.exit(1)

    # Collect all .vtt files
    vtt_files = [f for f in os.listdir(vtt_dir) if f.lower().endswith('.vtt')]
    if not vtt_files:
        print(f"No .vtt files found in '{vtt_dir}'.")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Create table if it doesn't exist
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS captions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT NOT NULL,
            cue_index INTEGER,
            start_time TEXT,
            end_time TEXT,
            text TEXT
        )
    ''')
    # Create an index on filename for faster lookups
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_filename ON captions(filename)')

    # Process each file
    for filename in vtt_files:
        full_path = os.path.join(vtt_dir, filename)
        print(f"Processing: {filename}")

        # Remove any existing entries for this file (avoid duplicates)
        cursor.execute("DELETE FROM captions WHERE filename = ?", (filename,))

        cues = parse_vtt(full_path)
        if not cues:
            print(f"  No cues found in {filename}")
            continue

        # Insert cues
        for idx, cue in enumerate(cues):
            cursor.execute('''
                INSERT INTO captions (filename, cue_index, start_time, end_time, text)
                VALUES (?, ?, ?, ?, ?)
            ''', (filename, idx, cue['start_time'], cue['end_time'], cue['text']))

        print(f"  Inserted {len(cues)} cues")

    conn.commit()
    conn.close()
    print(f"All data imported into '{db_path}'.")


def main():
    parser = argparse.ArgumentParser(
        description="Import WebVTT files from a directory into an SQLite database."
    )
    parser.add_argument(
        'directory',
        help="Path to the directory containing .vtt files"
    )
    parser.add_argument(
        '--db',
        default='allcaptions.db',
        help="Path to the SQLite database file (default: captions.db)"
    )
    args = parser.parse_args()

    import_directory(args.directory, args.db)


if __name__ == '__main__':
    main()
