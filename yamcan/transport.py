"""Open i2rt YAM arms over a non-SocketCAN python-can backend.

i2rt's `CanInterface(... bustype="socketcan" ...)` passes `bustype` straight to
`can.interface.Bus`, but `get_yam_robot` doesn't expose it — it always uses the
SocketCAN default. `using_bustype` temporarily makes every CanInterface i2rt
builds internally use a different backend (e.g. "slcan"), so `get_yam_robot`
works unchanged on macOS.

For slcan on macOS, the python-can `channel` is the adapter's serial device,
e.g. "/dev/tty.usbmodem1234".
"""

from __future__ import annotations

import contextlib
from typing import Any, Dict


def inject_bustype(kwargs: Dict[str, Any], bustype: str) -> Dict[str, Any]:
    """Return kwargs with `bustype` set, unless the caller already chose one.

    Pure helper (no side effects) so the override logic is unit-testable without
    i2rt or hardware.
    """
    if "bustype" in kwargs:
        return kwargs
    return {**kwargs, "bustype": bustype}


@contextlib.contextmanager
def using_bustype(bustype: str):
    """Temporarily force i2rt's CanInterface onto `bustype` (e.g. "slcan").

    Wraps CanInterface.__init__ so internal constructions that omit `bustype`
    pick up ours; restores the original on exit. i2rt is imported lazily so this
    module imports fine on a machine without i2rt installed.
    """
    from i2rt.motor_drivers import can_interface as _ci

    original_init = _ci.CanInterface.__init__

    def patched_init(self, *args, **kwargs):
        return original_init(self, *args, **inject_bustype(kwargs, bustype))

    _ci.CanInterface.__init__ = patched_init
    try:
        yield
    finally:
        _ci.CanInterface.__init__ = original_init


def open_yam_arm(channel: str, bustype: str = "slcan", **get_yam_robot_kwargs):
    """Open one i2rt YAM arm over `bustype` and return the i2rt robot.

    Args:
        channel: python-can channel for the chosen backend. For slcan on macOS,
            the serial device path (e.g. "/dev/tty.usbmodem1234").
        bustype: python-can backend ("slcan", "gs_usb", "serial", ...).
        **get_yam_robot_kwargs: forwarded to i2rt.get_yam_robot (e.g.
            zero_gravity_mode). Pass i2rt enums (GripperType/ArmType), not strings.
    """
    from i2rt.robots.get_robot import get_yam_robot

    with using_bustype(bustype):
        return get_yam_robot(channel=channel, **get_yam_robot_kwargs)
