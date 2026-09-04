# kodiso
extract ISO streams into multiple MKV streams to watch on Kodi

## Usage

```
./stitch.sh -i <iso_file_or_mounted_dvd_path> -o <output_path> -y <release_year>
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
