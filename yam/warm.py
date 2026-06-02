"""Cold-start handling for MolmoAct-2 on Modal.

Two problems this kit hit in the field, both handled here:

  * force_ipv4 — some hosts' IPv6 route to Modal blackholes (connect hangs ~15s
    then fails); dual-stack picks IPv6. Filtering getaddrinfo to AF_INET fixes it.
  * warm_until_hot — BOTH the registry app and the molmoact2-yam model server
    cold-start on Modal (~30-60s), and a cold start silently eats a run. Warm with
    mock inference until cycle latency drops, then drive the arms.
"""

from __future__ import annotations

import socket
import time

import numpy as np

_BLANK = {
    "state": np.zeros(14, dtype=np.float32),
    "images": {k: np.zeros((3, 378, 378), dtype=np.uint8) for k in ("top_cam", "left_cam", "right_cam")},
}


def force_ipv4() -> None:
    """Route all name resolution to IPv4 (for hosts with a broken IPv6 path to Modal)."""
    _orig = socket.getaddrinfo

    def _v4(host, port, family=0, type=0, proto=0, flags=0):
        return _orig(host, port, socket.AF_INET, type, proto, flags)

    socket.getaddrinfo = _v4


def warm_until_hot(api_key: str, model: str = "molmoact2-yam",
                   cap_s: float = 90.0, hot_s: float = 2.5, log=print) -> None:
    """Drive mock inference until cycle latency drops below hot_s (warm), or cap_s."""
    import newt

    cycles: list[float] = []
    last = [time.time()]

    def rs():
        return _BLANK

    def ex(_chunk):
        now = time.time()
        cycles.append(now - last[0])
        last[0] = now

    log("[warm] warming molmoact2 server with mock obs ...")
    t0 = time.time()
    while time.time() - t0 < cap_s:
        last[0] = time.time()
        try:
            newt.Robot(api_key=api_key, read_state=rs, execute=ex, model=model).run("warmup", max_duration=8.0)
        except Exception as exc:  # noqa: BLE001
            log(f"[warm] {type(exc).__name__}: {exc}")
        recent = cycles[-3:]
        if recent and min(recent) < hot_s:
            log(f"[warm] HOT — cycle {min(recent):.2f}s after {time.time() - t0:.0f}s")
            return
        if cycles:
            log(f"[warm] still warming (last cycle {cycles[-1]:.1f}s)")
    log("[warm] cap reached — proceeding (may still be coldish)")
