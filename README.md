# kodiso
extract ISO streams into multiple MKV streams to watch on Kodi

## Requirements

`encode.sh` works unmodified on both Linux and macOS. It requires
`HandBrakeCLI` and `ffprobe` (from ffmpeg) on your `PATH`; the script checks
for both on startup and exits with an error if either is missing.

If you're ripping from a physical DVD rather than an existing ISO, you'll
also need a tool to create the ISO first — this is a manual pre-step and
isn't invoked by the script itself.

### Linux

```
apt install handbrake-cli ffmpeg genisoimage
```

Create an ISO from a mounted DVD with:

```
genisoimage -dvd-video -udf -o movie.iso /path/to/mounted/dvd
```

### macOS

```
brew install handbrake ffmpeg
```

ISO creation is handled by `hdiutil`, which ships with macOS — no install
needed:

```
hdiutil makehybrid -udf -o movie.iso /Volumes/DVD_NAME
```

## CLI Usage

```
./encode.sh -i <iso_file_or_mounted_dvd_path> -o <output_path> -y <release_year>
```

- `-i` — an ISO/UDF disc image file, or the path to a mounted DVD device. Required.
- `-o` — destination path for the ripped movie. Its leaf directory name is the
  movie title; the rest of the path may be relative or absolute, but must
  already exist. Required.
- `-y` — the movie's release year (4 digits). Required.

Output follows the Kodi-friendly `Movie Name (Year)` convention: the main
feature (longest title) is written to
`<output_path> (<year>)/<leaf> (<year>).mkv`; all other titles are written to
`<output_path> (<year>)/extras/`.

If the resulting output directory already exists and contains visible files,
you'll be prompted to overwrite before anything is ripped.

## GUI Usage

A Streamlit GUI (`gui.py`) supports batch processing: queue up multiple
rips, each with its own input, output directory, name, and year, and it
rips them one at a time in the background while you keep adding more.

On macOS, the easiest way to run it is to download the prebuilt
`kodiso-gui` app from the
[latest release](../../releases/latest) — pick the `arm64` zip for
Apple Silicon Macs or `x86_64` for Intel Macs, unzip it, and double-click
`kodiso-gui.app`. It's ad-hoc signed rather than notarized, so the first
launch will need a right-click → Open (or `xattr -d com.apple.quarantine
kodiso-gui.app`) to get past Gatekeeper. It still needs `HandBrakeCLI`
and `ffprobe` on your `PATH` (see Requirements above) — only the GUI
itself is bundled, not those tools.

Otherwise, install the GUI's dependencies and launch it directly:

```
pip install .
streamlit run gui.py
```

This is a single-user tool meant to be run locally on your own machine —
it opens native file/folder picker dialogs (via `tkinter`, which ships with
most Python installs; on Linux you may need e.g. `apt install python3-tk`)
and detects any mounted CD/DVD drive automatically.

For each row:
- **Input** — pick a detected CD/DVD drive from the dropdown, or click
  "Browse ISO…" to pick an ISO/UDF file.
- **Output dir** — click "Browse output dir…" to choose where the ripped
  movie is written (same semantics as `encode.sh -o`'s parent directory).
- **Name** — defaults to the ISO's filename or the disc's volume name;
  editable.
- **Year** — the movie's release year.

Click ▶️ to queue the row — it appends to a FIFO encode queue (processed
one at a time in a background process so the UI stays responsive), and a
new empty row appears below it. A queued row's fields stay editable until
it starts encoding; once it's the row actively encoding, its fields lock
and ▶️ becomes 🛑. Clicking 🛑 on a queued row just removes it from the
queue; clicking it on the running row kills the encode and lets
`encode.sh`'s own cleanup remove its temp files. The sidebar shows a live
progress bar for the row currently encoding and a log of completed rips.
