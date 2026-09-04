#!/usr/bin/env python3
"""Native file/directory picker, run as its own process.

tkinter needs to own the main thread of its process (this matters
especially on macOS, where Cocoa refuses to create windows off the main
thread). Streamlit runs app scripts on a worker thread, so this dialog is
spawned as a standalone subprocess rather than called in-process from the
GUI: gui.py blocks on this process and reads the chosen path from stdout.
"""
import sys


def main() -> int:
    if len(sys.argv) < 2 or sys.argv[1] not in ("file", "dir"):
        print("Usage: file_picker.py <file|dir> [initialdir]", file=sys.stderr)
        return 2

    mode = sys.argv[1]
    initialdir = sys.argv[2] if len(sys.argv) > 2 else None

    try:
        import tkinter as tk
        from tkinter import filedialog
    except ImportError:
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


if __name__ == "__main__":
    sys.exit(main())
