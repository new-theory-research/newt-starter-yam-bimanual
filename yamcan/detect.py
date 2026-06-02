"""Find USB-CAN adapters and guess the right python-can backend.

Run it: `python -m yamcan` (or `yamcan-scan`). Plug an adapter in, run it, and
it reports the serial ports and a backend guess so you know whether the Mac path
(slcan / gs_usb) is even on the table.
"""

from __future__ import annotations

import glob
import subprocess
import sys
from typing import Dict, List

# (substring found in USB vendor/product text) -> python-can backend to try.
# Substrings are matched case-insensitively against the OS USB description.
# Order matters: the FIRMWARE string ("gs_usb"/"candlelight"/"slcan") is the real
# signal and must beat generic device-family names — a CANable can run EITHER
# gs_usb or slcan firmware, so "canable2 gs_usb" must classify as gs_usb.
_SIGNATURES = [
    ("gs_usb", "gs_usb"),
    ("candlelight", "gs_usb"),
    ("geschwister", "gs_usb"),       # Geschwister Schneider / candleLight
    ("slcan", "slcan"),
    ("cantact", "slcan"),
    ("canable", "gs_usb"),           # CANable2 ships gs_usb by default; reflashable to slcan
    ("stm32", "slcan"),              # bare STM32 CDC clones usually run slcan
    ("canalyst", "unsupported-on-mac"),   # CANalyst-II: Windows-only driver
    ("usb2can", "unsupported-on-mac"),
]


def classify_backend(usb_text: str) -> str:
    """Map an OS USB description to a python-can backend guess.

    Returns the backend name ("slcan"/"gs_usb"), "unsupported-on-mac" for
    known Windows-only chipsets, or "unknown". Pure + testable.
    """
    text = (usb_text or "").lower()
    for needle, backend in _SIGNATURES:
        if needle in text:
            return backend
    return "unknown"


def serial_ports() -> List[str]:
    """Candidate serial devices for an slcan adapter, per OS."""
    if sys.platform == "darwin":
        return sorted(set(glob.glob("/dev/tty.*") + glob.glob("/dev/cu.*")))
    return sorted(glob.glob("/dev/ttyACM*") + glob.glob("/dev/ttyUSB*"))


def _run(cmd) -> str:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=20).stdout or ""
    except Exception:
        return ""


def _usb_description() -> str:
    """OS USB inventory as text. On macOS `system_profiler` can return nothing in
    sandboxed/headless shells, so prefer `ioreg` (reliable) and fall back."""
    if sys.platform == "darwin":
        out = _run(["ioreg", "-rc", "IOUSBHostDevice"])
        if out.strip():
            return out
        return _run(["system_profiler", "SPUSBDataType"])
    return _run(["lsusb"])


def scan() -> Dict[str, object]:
    """Scan the host for USB-CAN adapters. Returns a structured report."""
    desc = _usb_description()
    interesting = ("can", "stm32", "serial number", "manufacturer", "product", "vendor")
    hints = [ln.strip() for ln in desc.splitlines() if any(k in ln.lower() for k in interesting)]
    return {
        "platform": sys.platform,
        "serial_ports": serial_ports(),
        "backend_guess": classify_backend(desc),
        "usb_hints": hints[:25],
    }


def main() -> None:
    report = scan()
    print(f"platform:      {report['platform']}")
    print(f"backend guess: {report['backend_guess']}")
    ports = report["serial_ports"]
    print(f"serial ports:  {ports if ports else '(none — plug an adapter in)'}")
    if report["usb_hints"]:
        print("usb hints:")
        for line in report["usb_hints"]:
            print(f"  {line}")


if __name__ == "__main__":
    main()
