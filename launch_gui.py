"""PyInstaller entry point for the frozen kodiso-gui app.

Not run directly in normal development -- use `streamlit run gui.py` for
that. This is the target PyInstaller freezes, and it dispatches to one of
two things a plain `streamlit run` invocation can't do on its own:

- `--file-picker <file|dir> [initialdir]`: run file_picker.py's tkinter
  dialog and exit. gui.py spawns this as a subprocess (tkinter needs to
  own its process's main thread), but a frozen app has no separate
  Python interpreter for it to hand file_picker.py to via sys.executable
  the way the unfrozen app does -- so it re-invokes this same frozen
  binary instead, and this dispatches based on the flag.
- otherwise: boot the Streamlit server pointed at the bundled gui.py.
"""
from __future__ import annotations

import sys
from pathlib import Path


def main() -> int:
    if len(sys.argv) > 1 and sys.argv[1] == "--file-picker":
        import file_picker
        sys.argv = [sys.argv[0], *sys.argv[2:]]
        return file_picker.main()

    import streamlit.web.cli as stcli

    app_root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    sys.argv = [
        "streamlit", "run", str(app_root / "gui.py"),
        "--global.developmentMode=false",
    ]
    return stcli.main()


if __name__ == "__main__":
    sys.exit(main())
