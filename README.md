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

## Usage

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
