# vttwebsearch
vtt to sqlite3 fts5 to webapp in two files. Now cross-platform (works on windows!)

requires ffmpeg and whatever is in the imports. ffmpeg must be compiled with mp3 lame support
for this script to work as-is.
`python -m venv vttsearch`
`cd vttsearch`
`#your activate command, on windows it's Scripts\activate.ps1`
`pip install flask`
copy ffmpeg.exe into your vttsearch directory (unless it's installed, 
then it should just work)
then `python vtt_to_sqlite.py path\to\transcriptions`
then `python search_appv3.py`
The mime type can be changed at the same time as the ffmpeg output module;
for instance to opus, in theory.

This wastes bandwidth and is impossible to cache
unless it is recent show transcriptions
and catch phrases.

run `python3 vtt_to_sqlite.py --db captions.db /vtt/directory`
then set the correct directory to your MP3 files (or whatever)
inside search_appv3.py, and python3 search_appv3.py

localhost:5000 will be running a "web server" to handle your requests.

it makes sense if you understand all the parts, but this is mostly
for posterity.

