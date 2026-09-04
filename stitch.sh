#!/bin/bash
set -e

usage() {
  echo "Usage: $0 -i <iso_file_or_mounted_dvd_path> -o <output_path> -y <release_year>" >&2
  echo "  -i  ISO file or mounted DVD device path to rip" >&2
  echo "  -o  destination path; its leaf directory name is the movie title" >&2
  echo "  -y  the movie's release year (4 digits)" >&2
  echo "      output is written as '<output_path> (<year>)/<leaf> (<year>).mkv'" >&2
  exit 1
}

# ---- Check prerequisites are installed before doing anything else ----
missing=""
for cmd in HandBrakeCLI ffprobe; do
  command -v "$cmd" >/dev/null 2>&1 || missing="$missing $cmd"
done
if [ -n "$missing" ]; then
  echo "Error: missing required tool(s):$missing" >&2
  echo "See the Requirements section in README.md for install instructions." >&2
  exit 1
fi

INPUT=""
OUTDIR=""
YEAR=""

while getopts ":i:o:y:" opt; do
  case "$opt" in
    i) INPUT="$OPTARG" ;;
    o) OUTDIR="$OPTARG" ;;
    y) YEAR="$OPTARG" ;;
    :) echo "Error: -$OPTARG requires an argument" >&2; usage ;;
    \?) echo "Error: invalid option -$OPTARG" >&2; usage ;;
  esac
done

[ -z "$INPUT" ] && usage
[ -z "$OUTDIR" ] && usage
[ -z "$YEAR" ] && usage

if ! [[ "$YEAR" =~ ^[0-9]{4}$ ]]; then
  echo "Error: -y must be a 4-digit year (got '$YEAR')" >&2
  exit 1
fi

# ---- Validate -i: must be a mounted DVD directory, or an ISO/UDF disc image file ----
if [ -d "$INPUT" ]; then
  : # mounted DVD path, accepted as-is
elif [ -f "$INPUT" ]; then
  if ! file -b "$INPUT" | grep -qiE 'ISO 9660|UDF filesystem'; then
    echo "Error: '$INPUT' does not appear to be an ISO/UDF disc image" >&2
    exit 1
  fi
else
  echo "Error: input '$INPUT' does not exist" >&2
  exit 1
fi

# ---- Validate -o: parent directory must already exist ----
PARENT_DIR=$(dirname "$OUTDIR")
if [ ! -d "$PARENT_DIR" ]; then
  echo "Error: parent directory '$PARENT_DIR' does not exist" >&2
  exit 1
fi

MOVIE_NAME=$(basename "$OUTDIR")
FULL_NAME="${MOVIE_NAME} (${YEAR})"
FINAL_DIR="${PARENT_DIR}/${FULL_NAME}"

# ---- Warn before touching a non-empty output directory (dotfiles don't count) ----
if [ -d "$FINAL_DIR" ]; then
  visible_entries=$(find "$FINAL_DIR" -mindepth 1 -maxdepth 1 ! -name '.*')
  if [ -n "$visible_entries" ]; then
    echo "Warning: output directory '$FINAL_DIR' already exists and is not empty."
    read -r -p "Overwrite? [y/N] " reply
    case "$reply" in
      [yY]|[yY][eE][sS]) ;;
      *) echo "Aborting."; exit 0 ;;
    esac
  fi
fi

mkdir -p "$FINAL_DIR/extras"

# ---- Rip into a scratch temp dir; always clean it up on exit ----
TMPDIR=$(mktemp -d)
cleanup() {
  rm -rf "$TMPDIR"
}
trap cleanup EXIT

echo "=== Scanning titles ==="
titles=$(HandBrakeCLI -i "$INPUT" -t 0 2>&1 | grep "+ title" | sed -E 's/\+ title ([0-9]+).*/\1/')
echo "Found titles: $titles"

echo "=== Ripping all titles ==="
for i in $titles; do
  HandBrakeCLI -i "$INPUT" -o "$TMPDIR/title${i}.mkv" \
    -t "${i}" \
    -m \
    -e x264 -q 20 \
    --all-audio --all-subtitles
done

echo "=== Measuring durations to find main feature (longest) ==="
main_title=""
main_dur=0
for i in $titles; do
  dur=$(ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "$TMPDIR/title${i}.mkv")
  dur_int=${dur%.*}
  echo "title${i}.mkv: ${dur_int}s"
  if [ "$dur_int" -gt "$main_dur" ]; then
    main_dur=$dur_int
    main_title=$i
  fi
done
echo "Main feature: title${main_title}.mkv (${main_dur}s)"

echo "=== Organizing into Kodi structure ==="
mv "$TMPDIR/title${main_title}.mkv" "$FINAL_DIR/${FULL_NAME}.mkv"

extra_n=1
for i in $titles; do
  if [ "$i" != "$main_title" ]; then
    mv "$TMPDIR/title${i}.mkv" "$FINAL_DIR/extras/Extra ${extra_n} (title${i}).mkv"
    extra_n=$((extra_n+1))
  fi
done

echo "=== Done ==="
echo "Main feature: $FINAL_DIR/${FULL_NAME}.mkv"
echo "Extras:"
ls "$FINAL_DIR/extras"
