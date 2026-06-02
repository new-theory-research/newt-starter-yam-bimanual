"""Software 'replug' of connected Intel RealSense cameras. Needs root.

Finds RealSense by USB VID 0x8086 (PIDs 0x0b07 D435, 0x0b5b D405) and issues
USBDEVFS_RESET — the programmatic equivalent of unplug/replug, to un-wedge
cameras that enumerate but won't bind (no /dev/video, librealsense sees 0).
"""

import fcntl
import glob
import os

USBDEVFS_RESET = ord("U") << 8 | 20  # _IO('U', 20)
REALSENSE_PIDS = {"0b07", "0b5b", "0b3a", "0b64"}  # D435/D405/D435i/D455 family

found = []
for d in glob.glob("/sys/bus/usb/devices/*"):
    try:
        vid = open(os.path.join(d, "idVendor")).read().strip()
        pid = open(os.path.join(d, "idProduct")).read().strip()
    except OSError:
        continue
    if vid == "8086" and pid in REALSENSE_PIDS:
        busnum = int(open(os.path.join(d, "busnum")).read().strip())
        devnum = int(open(os.path.join(d, "devnum")).read().strip())
        found.append((f"/dev/bus/usb/{busnum:03d}/{devnum:03d}", pid))

print(f"RealSense USB nodes found: {found}")
for node, pid in found:
    try:
        fd = os.open(node, os.O_WRONLY)
        fcntl.ioctl(fd, USBDEVFS_RESET, 0)
        os.close(fd)
        print(f"  reset OK: {node} (pid {pid})")
    except Exception as exc:  # noqa: BLE001
        print(f"  reset FAIL: {node}: {exc}")
