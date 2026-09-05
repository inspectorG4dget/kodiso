"""Streamlit GUI for batch kodiso encoding.

Rows of (input, output dir, name, year) are queued and ripped one at a
time via encode.sh, in a single background worker process so the queue
keeps draining while the UI stays responsive. encode.sh itself is never
modified -- the GUI treats it as an opaque CLI tool.
"""
from __future__ import annotations

import atexit
import os
import plistlib
import signal
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Optional

import streamlit as st
from multiprocessing import Manager, Process

from file_picker import PERMISSION_DENIED_MARKER

FROZEN = getattr(sys, "frozen", False)
REPO_ROOT = Path(getattr(sys, "_MEIPASS", "")) if FROZEN else Path(__file__).resolve().parent
ENCODE_SCRIPT = REPO_ROOT / "encode.sh"
FILE_PICKER_SCRIPT = REPO_ROOT / "file_picker.py"

RIPPING_MARKER = "=== Ripping all titles ==="
FOUND_TITLES_PREFIX = "Found titles:"
ENCODE_DONE_MARKER = "Encode done!"

TERMINAL_STATUSES = {"done", "stopped", "error"}


# --------------------------------------------------------------------------
# Worker process: pulls queued jobs and rips them one at a time via encode.sh
# --------------------------------------------------------------------------

def _update_job(jobs, job_id: str, **changes):
    for i, j in enumerate(jobs):
        if j["id"] == job_id:
            merged = dict(j)
            merged.update(changes)
            jobs[i] = merged
            return merged
    return None


def _run_job(job, jobs, log) -> None:
    job_id = job["id"]
    out_path = str(Path(job["output_dir"]) / job["name"])
    cmd = [
        str(ENCODE_SCRIPT),
        "-i", job["input_path"],
        "-o", out_path,
        "-y", str(job["year"]),
    ]

    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            start_new_session=True,  # own process group, so Stop can kill it + HandBrakeCLI together
        )
    except OSError as exc:
        _update_job(jobs, job_id, status="error", error=str(exc))
        log.append({"name": job["name"], "year": job["year"], "status": "error"})
        return

    _update_job(
        jobs, job_id,
        status="running",
        pgid=os.getpgid(proc.pid),
        titles_total=0,
        titles_done=0,
    )

    titles_total = 0
    titles_done = 0
    collecting_titles = False
    tail_lines: list[str] = []

    assert proc.stdout is not None
    for raw_line in proc.stdout:
        line = raw_line.rstrip("\n")
        tail_lines.append(line)
        tail_lines = tail_lines[-25:]

        if line.startswith(FOUND_TITLES_PREFIX):
            collecting_titles = True
            rest = line[len(FOUND_TITLES_PREFIX):].strip()
            if rest:
                titles_total += len(rest.split())
            continue

        if collecting_titles:
            if line.strip() == RIPPING_MARKER:
                collecting_titles = False
                _update_job(jobs, job_id, titles_total=titles_total)
            elif line.strip():
                titles_total += len(line.strip().split())
            continue

        if ENCODE_DONE_MARKER in line:
            titles_done += 1
            _update_job(jobs, job_id, titles_done=titles_done)

    returncode = proc.wait()

    current = next((j for j in jobs if j["id"] == job_id), None)
    if current is not None and current.get("status") == "stopped":
        final_status = "stopped"
    elif returncode == 0:
        final_status = "done"
        titles_done = titles_total
    else:
        final_status = "error"

    _update_job(
        jobs, job_id,
        status=final_status,
        titles_done=titles_done,
        error="\n".join(tail_lines) if final_status == "error" else None,
    )
    log.append({"name": job["name"], "year": job["year"], "status": final_status})


def _worker_loop(jobs, log) -> None:
    while True:
        job = next((dict(j) for j in jobs if j["status"] == "queued"), None)
        if job is None:
            time.sleep(0.5)
            continue
        _run_job(job, jobs, log)


@st.cache_resource
def get_worker():
    manager = Manager()
    jobs = manager.list()
    log = manager.list()
    proc = Process(target=_worker_loop, args=(jobs, log), daemon=True)
    proc.start()

    def _cleanup():
        for j in list(jobs):
            pgid = j.get("pgid")
            if j.get("status") == "running" and pgid:
                try:
                    os.killpg(pgid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
        proc.terminate()
        proc.join(timeout=5)

    atexit.register(_cleanup)
    return jobs, log


def stop_job(jobs, job_id: str) -> None:
    """Stop a queued job (just dequeue) or a running one (kill its process group)."""
    for i, j in enumerate(jobs):
        if j["id"] != job_id:
            continue
        merged = dict(j)
        merged["status"] = "stopped"
        jobs[i] = merged
        pgid = j.get("pgid")
        if j.get("status") == "running" and pgid:
            try:
                os.killpg(pgid, signal.SIGTERM)
            except ProcessLookupError:
                pass
        return


# --------------------------------------------------------------------------
# Optical drive detection (cached briefly so every rerun doesn't re-scan)
# --------------------------------------------------------------------------

@st.cache_data(ttl=5)
def detect_optical_drives() -> list[str]:
    if sys.platform == "darwin":
        return _detect_optical_drives_macos()
    if sys.platform.startswith("linux"):
        return _detect_optical_drives_linux()
    return []


def _detect_optical_drives_macos() -> list[str]:
    drives = []
    volumes = Path("/Volumes")
    if not volumes.is_dir():
        return drives
    for entry in volumes.iterdir():
        try:
            out = subprocess.run(
                ["diskutil", "info", "-plist", str(entry)],
                capture_output=True, timeout=5,
            ).stdout
            info = plistlib.loads(out)
        except Exception:
            continue
        if info.get("FilesystemName") in ("ISO9660", "UDF", "CDDAFS", "CD9660"):
            drives.append(str(entry))
    return drives


def _detect_optical_drives_linux() -> list[str]:
    drives = []
    try:
        with open("/proc/mounts") as f:
            lines = f.read().splitlines()
    except OSError:
        return drives
    for line in lines:
        parts = line.split()
        if len(parts) < 3:
            continue
        device, mountpoint, fstype = parts[0], parts[1], parts[2]
        mountpoint = mountpoint.replace("\\040", " ")
        if fstype in ("iso9660", "udf") or device.startswith("/dev/sr"):
            drives.append(mountpoint)
    return drives


# --------------------------------------------------------------------------
# Native dialog helper
# --------------------------------------------------------------------------

def run_native_picker(mode: str, initialdir: Optional[str] = None) -> Optional[str]:
    if FROZEN:
        # No separate Python interpreter to hand file_picker.py to --
        # re-invoke this same frozen binary, which dispatches on the flag.
        cmd = [sys.executable, "--file-picker", mode]
    else:
        cmd = [sys.executable, str(FILE_PICKER_SCRIPT), mode]
    if initialdir:
        cmd.append(initialdir)
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    except subprocess.TimeoutExpired:
        st.error("File picker timed out.")
        return None
    if result.returncode != 0:
        if PERMISSION_DENIED_MARKER in result.stderr:
            st.error(
                "kodiso needs permission to control Finder to show the file "
                "picker. Grant it in System Settings → Privacy & Security → "
                "Automation, then try again."
            )
        else:
            st.error(f"Could not open native file picker: {result.stderr.strip()}")
        return None
    path = result.stdout.strip()
    return path or None


# --------------------------------------------------------------------------
# Row state
# --------------------------------------------------------------------------

def blank_row() -> dict:
    return {
        "id": str(uuid.uuid4()),
        "input_path": "",
        "output_dir": "",
        "name": "",
        "year": None,
    }


def default_name_for(input_path: str) -> str:
    if not input_path:
        return ""
    p = Path(input_path)
    return p.stem if p.is_file() else p.name


def row_is_valid(row: dict) -> bool:
    return bool(row["input_path"] and row["output_dir"] and row["name"] and row["year"])


# --------------------------------------------------------------------------
# UI
# --------------------------------------------------------------------------

def render_row(row: dict, jobs, editable: bool, on_submit=None, on_stop=None, on_change=None) -> None:
    cols = st.columns([3, 3, 2, 1, 1])

    with cols[0]:
        drives = detect_optical_drives()
        if drives and editable:
            choice = st.selectbox(
                "Drive", ["—"] + drives, key=f"drive_{row['id']}", label_visibility="collapsed",
            )
            if choice != "—" and choice != row["input_path"]:
                row["input_path"] = choice
                if not row["name"]:
                    row["name"] = default_name_for(choice)
                if on_change:
                    on_change(row)
        if editable and st.button("📁 Browse ISO…", key=f"browse_iso_{row['id']}"):
            picked = run_native_picker("file")
            if picked:
                row["input_path"] = picked
                if not row["name"]:
                    row["name"] = default_name_for(picked)
                if on_change:
                    on_change(row)
                st.rerun()
        st.caption(row["input_path"] or "No input selected")

    with cols[1]:
        if editable and st.button("📁 Browse output dir…", key=f"browse_out_{row['id']}"):
            picked = run_native_picker("dir")
            if picked:
                row["output_dir"] = picked
                if on_change:
                    on_change(row)
                st.rerun()
        st.caption(row["output_dir"] or "No output directory selected")

    with cols[2]:
        name = st.text_input(
            "Name", value=row["name"], key=f"name_{row['id']}",
            disabled=not editable, label_visibility="collapsed",
        )
        if editable and name != row["name"]:
            row["name"] = name
            if on_change:
                on_change(row)

    with cols[3]:
        year = st.number_input(
            "Year", value=row["year"], key=f"year_{row['id']}",
            step=1, format="%d", min_value=1888, max_value=2100,
            disabled=not editable, label_visibility="collapsed",
        )
        if editable and year != row["year"]:
            row["year"] = year
            if on_change:
                on_change(row)

    with cols[4]:
        status = row.get("status", "idle")
        if status == "done":
            st.info("Done")
        elif status == "stopped":
            st.warning("Stopped")
        elif status == "error":
            st.error("Error")
            if row.get("error"):
                with st.expander("Details"):
                    st.code(row["error"])
        elif status == "running":
            if st.button("🛑", key=f"stop_{row['id']}", help="Stop"):
                on_stop(row["id"])
                st.rerun()
        elif status == "queued":
            if st.button("🛑", key=f"stop_{row['id']}", help="Stop"):
                on_stop(row["id"])
                st.rerun()
        else:  # idle
            valid = row_is_valid(row)
            if st.button("▶️", key=f"play_{row['id']}", help="Start", disabled=not valid):
                on_submit(row)
                st.rerun()

    if status == "running":
        total = row.get("titles_total") or 0
        done = row.get("titles_done") or 0
        if total > 0:
            st.progress(min(done / total, 1.0), text=f"Title {min(done, total)} of {total}")
        else:
            st.progress(0.0, text="Scanning titles…")


def main() -> None:
    st.set_page_config(page_title="kodiso", layout="wide")
    st.title("kodiso")

    jobs, log = get_worker()

    if "idle_row" not in st.session_state:
        st.session_state.idle_row = blank_row()

    def on_change(row: dict) -> None:
        # only meaningful for queued jobs (idle row lives purely in session_state);
        # only push the user-editable fields, never status/pgid/progress -- those
        # are worker-owned and a stale snapshot here must not clobber them.
        if row.get("status") == "queued":
            _update_job(
                jobs, row["id"],
                input_path=row["input_path"],
                output_dir=row["output_dir"],
                name=row["name"],
                year=row["year"],
            )

    def on_submit(row: dict) -> None:
        job = dict(row)
        job["status"] = "queued"
        jobs.append(job)
        st.session_state.idle_row = blank_row()

    def on_stop(job_id: str) -> None:
        stop_job(jobs, job_id)

    header = st.columns([3, 3, 2, 1, 1])
    for col, label in zip(header, ["Input", "Output dir", "Name", "Year", ""]):
        col.markdown(f"**{label}**")

    for job in list(jobs):
        editable = job["status"] == "queued"
        st.divider()
        render_row(
            dict(job), jobs,
            editable=editable,
            on_submit=on_submit,
            on_stop=on_stop,
            on_change=on_change,
        )

    st.divider()
    render_row(st.session_state.idle_row, jobs, editable=True, on_submit=on_submit, on_stop=on_stop)

    with st.sidebar:
        st.header("Progress")
        running = next((j for j in jobs if j["status"] == "running"), None)
        if running:
            total = running.get("titles_total") or 0
            done = running.get("titles_done") or 0
            st.write(f"**Encoding:** {running['name']} ({running['year']})")
            if total > 0:
                st.progress(min(done / total, 1.0), text=f"Title {min(done, total)} of {total}")
            else:
                st.progress(0.0, text="Scanning titles…")
        else:
            st.caption("Nothing encoding right now.")

        st.subheader("Completed")
        entries = list(log)
        if not entries:
            st.caption("No jobs finished yet.")
        for entry in reversed(entries):
            label = f"{entry['name']} ({entry['year']})"
            if entry["status"] == "done":
                st.info(f"✅ {label}")
            elif entry["status"] == "stopped":
                st.warning(f"🛑 {label}")
            else:
                st.error(f"❌ {label}")

    # Keep the UI live while anything is queued/running, without polling once idle.
    if any(j["status"] in ("queued", "running") for j in jobs):
        time.sleep(1)
        st.rerun()


if __name__ == "__main__":
    main()
