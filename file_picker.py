#!/usr/bin/env python3
"""Native file/directory picker, run as its own process.

macOS uses AppleScript ("choose file"/"choose folder" via osascript)
rather than tkinter: tkinter links against the system Tcl/Tk, which has a
long-standing bug on Big Sur/Monterey (Tcl/Tk 8.5.9) that makes its
windows fail to draw or hang outright. Every other platform still uses
tkinter, which needs to own the main thread of its process (this matters
especially on macOS, where Cocoa refuses to create windows off the main
thread) -- Streamlit runs app scripts on a worker thread, so this dialog
is spawned as a standalone subprocess rather than called in-process from
the GUI: gui.py blocks on this process and reads the chosen path from
stdout.
"""
import subprocess
import sys
from typing import Optional

try:
    import tkinter as tk
    from tkinter import filedialog
except ImportError:
    tk = None
    filedialog = None

PERMISSION_DENIED_MARKER = "AUTOMATION_PERMISSION_DENIED"

# Both scripts take the optional initialdir as argv rather than splicing it
# into the script text, so a path containing quotes can't break out of the
# AppleScript string literal.
_APPLESCRIPT_FILE = """
on run argv
    tell application "Finder"
        activate
        if (count of argv) > 0 then
            set thePath to choose file of type {"iso"} with prompt "Select ISO file" default location (POSIX file (item 1 of argv))
        else
            set thePath to choose file of type {"iso"} with prompt "Select ISO file"
        end if
    end tell
    return POSIX path of thePath
end run
"""

_APPLESCRIPT_DIR = """
on run argv
    tell application "Finder"
        activate
        if (count of argv) > 0 then
            set thePath to choose folder with prompt "Select output directory" default location (POSIX file (item 1 of argv))
        else
            set thePath to choose folder with prompt "Select output directory"
        end if
    end tell
    return POSIX path of thePath
end run
"""


def _pick_macos(mode: str, initialdir: Optional[str]) -> int:
    script = _APPLESCRIPT_FILE if mode == "file" else _APPLESCRIPT_DIR
    cmd = ["osascript", "-e", script]
    if initialdir:
        cmd.append(initialdir)
    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode == 0:
        path = result.stdout.strip()
        if path:
            print(path)
        return 0

    stderr = result.stderr.strip()
    if "(-128)" in stderr:
        # User clicked Cancel -- same as tkinter's empty-string-on-cancel.
        return 0
    if "(-1743)" in stderr:
        # Not authorized to send Apple events to Finder yet.
        print(PERMISSION_DENIED_MARKER, file=sys.stderr)
        return 1
    print(stderr, file=sys.stderr)
    return 1


def _pick_tkinter(mode: str, initialdir: Optional[str]) -> int:
    if tk is None or filedialog is None:
        print("tkinter is not available in this Python install", file=sys.stderr)
        return 1

    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    root.lift()
    root.focus_force()

    kwargs = {"parent": root}
    if initialdir:
        kwargs["initialdir"] = initialdir

    if mode == "file":
        path = filedialog.askopenfilename(
            title="Select ISO file",
            filetypes=[("Disc images", "*.iso *.img *.udf"), ("All files", "*.*")],
            **kwargs,
        )
    else:
        path = filedialog.askdirectory(title="Select output directory", **kwargs)

    root.destroy()

    if path:
        print(path)
    return 0


def main() -> int:
    if len(sys.argv) < 2 or sys.argv[1] not in ("file", "dir"):
        print("Usage: file_picker.py <file|dir> [initialdir]", file=sys.stderr)
        return 2

    mode = sys.argv[1]
    initialdir = sys.argv[2] if len(sys.argv) > 2 else None

    if sys.platform == "darwin":
        return _pick_macos(mode, initialdir)
    return _pick_tkinter(mode, initialdir)


if __name__ == "__main__":
    sys.exit(main())
