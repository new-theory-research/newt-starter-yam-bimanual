"""yamcan — drive i2rt YAM arms over USB-CAN on hosts without SocketCAN.

i2rt defaults to SocketCAN (`bustype="socketcan"`, channel `can0`), which is
Linux-only. But its CAN layer is built on python-can and takes `bustype` as a
parameter, so any python-can backend works — including `slcan`/`gs_usb`/`serial`,
which run on macOS and Windows. This package makes that switch ergonomic.

Two pieces:
  - detect: find USB-CAN adapters and guess the right python-can backend.
  - transport: open i2rt YAM arms over a chosen backend (e.g. slcan on macOS).

Deliberately self-contained: depends only on python-can + i2rt + stdlib, and
imports NOTHING from the surrounding project. Lift the whole `yamcan/` directory
into another repo and it works unchanged.

⚠️ Caveat: i2rt's control loop targets >=100 Hz. SocketCAN on Linux sustains
that comfortably; slcan-over-USB-serial through Python on macOS may not, for two
arms. Verify the achievable loop rate before trusting it with real motion.
"""

from .detect import classify_backend, scan
from .transport import inject_bustype, open_yam_arm, using_bustype

__all__ = [
    "scan",
    "classify_backend",
    "open_yam_arm",
    "using_bustype",
    "inject_bustype",
]
