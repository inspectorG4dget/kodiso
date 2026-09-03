# kodiso
extract ISO streams into multiple MKV streams to watch on Kodi

## Usage

```
./stitch.sh -i <iso_file_or_mounted_dvd_path> -o <output_path>
```

- `-i` — an ISO/UDF disc image file, or the path to a mounted DVD device. Required.
- `-o` — destination path for the ripped movie. Its leaf directory name becomes
  the movie title (used to name the main feature `.mkv`); the rest of the path
  may be relative or absolute, but must already exist. Required.

The main feature (longest title) is written to `<output_path>/<leaf>.mkv`;
all other titles are written to `<output_path>/extras/`.

If `<output_path>` already exists and contains visible files, you'll be
prompted to overwrite before anything is ripped.
