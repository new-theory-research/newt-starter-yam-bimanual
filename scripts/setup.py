#!/usr/bin/env python3
"""Scaffold ~/.config/nt/nt.toml and check the rig: cameras (serials + USB-3),
CAN interfaces, uvcvideo. Reports what it autofilled and what still needs you.

    ./scripts/setup                 # interactive
    ./scripts/setup --force         # overwrite the config
    ./scripts/setup --report-only   # detect + report, write nothing
    ./scripts/setup --json          # structured output for agents
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TEMPLATE = REPO / "conf" / "nt.toml.example"
DEST = Path.home() / ".config" / "nt" / "nt.toml"


def _run(cmd):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=20).stdout or ""
    except Exception:
        return ""


def detect_cameras():
    """Return [{name, serial}] for connected RealSense (via pyrealsense2)."""
    try:
        import pyrealsense2 as rs
    except Exception:
        return []
    out = []
    for d in rs.context().query_devices():
        out.append({"name": d.get_info(rs.camera_info.name),
                    "serial": d.get_info(rs.camera_info.serial_number)})
    return out


def usb2_realsense_present():
    """True if any RealSense is on a 480M (USB-2) link — they won't stream there."""
    tree = _run(["lsusb", "-t"])
    # crude: any Video-class interface line negotiated at 480M
    return any("Class=Video" in ln and "480M" in ln for ln in tree.splitlines())


def can_status():
    br = _run(["ip", "-br", "link"])
    return {c: ("UP" if any(c in ln and "UP" in ln for ln in br.splitlines()) else "down/absent")
            for c in ("can0", "can1")}


def uvcvideo_loaded():
    return "uvcvideo" in _run(["lsmod"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--report-only", action="store_true")
    ap.add_argument("--non-interactive", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    cams = detect_cameras()
    report = {
        "config_path": str(DEST),
        "config_exists": DEST.exists(),
        "cameras": cams,
        "usb2_warning": usb2_realsense_present(),
        "uvcvideo_loaded": uvcvideo_loaded(),
        "can": can_status(),
    }

    if args.json:
        print(json.dumps(report, indent=2))
        return

    print(f"cameras detected: {len(cams)}")
    for c in cams:
        print(f"  {c['name']}  {c['serial']}")
    if report["usb2_warning"]:
        print("  ⚠️  a RealSense is on a USB-2 (480M) link — move it to USB-3 or it won't stream.")
    if not report["uvcvideo_loaded"]:
        print("  ⚠️  uvcvideo not loaded — cameras won't appear. Run: sudo modprobe uvcvideo")
    for c, st in report["can"].items():
        print(f"  {c}: {st}" + ("" if st == "UP" else "   (bring up: sudo ip link set "
              f"{c} up type can bitrate 1000000)"))

    if args.report_only:
        return

    if DEST.exists() and not args.force:
        print(f"\n{DEST} already exists — re-run with --force to overwrite. Edit it directly to "
              "set camera serials / CAN channels.")
        return

    DEST.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(TEMPLATE, DEST)
    print(f"\nwrote {DEST} from template.")
    print("Next: edit it to set [cameras] serials (top/left/right) and confirm [arms] channels, "
          "then `export NT_API_KEY=...` and walk the bring-up ladder in the README.")
    # TODO: interactive camera->position mapping + writing serials into the toml.


if __name__ == "__main__":
    main()
