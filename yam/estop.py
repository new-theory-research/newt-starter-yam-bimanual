"""SSH-controllable software stop for the YAM rig.

No hardware e-stop is wired to these arms yet (the physical one is for a
different arm — verified 2026-06-02), so this is the kill mechanism. Unlike the
trossen Ctrl+H listener (TTY-only), this is triggerable from ANY ssh session.

Three trigger paths, all set the same STOP event and run the safe-stop callback
(zero motor torque), once:
  1. Sentinel file  — `touch $YAM_ESTOP_FILE` (default /tmp/yam_estop) from any
     ssh session. Polled every 50 ms. THE cross-session SSH control.
  2. SIGINT/SIGTERM — Ctrl+C, or `pkill -TERM -f run.py` from elsewhere
     (a signal interrupts even a busy loop).
  3. Ctrl+H (\\x08) — when running in an interactive TTY (trossen convention).

The control loop calls check() before each driver write; on trigger it raises
EmergencyStop and the safe-stop callback zeros torque. Stdlib-only.
"""

from __future__ import annotations

import os
import select
import signal
import sys
import threading
import time
from typing import Callable, Optional

SENTINEL = os.environ.get("YAM_ESTOP_FILE", "/tmp/yam_estop")

_STOP = threading.Event()
_SAFED = threading.Event()  # safe_stop runs at most once
_safe_stop_fn: Optional[Callable[[], None]] = None


class EmergencyStop(Exception):
    """Raised by check() once a stop has been triggered."""


def triggered() -> bool:
    return _STOP.is_set()


def check() -> None:
    """Raise EmergencyStop if a stop fired. Call between driver writes."""
    if _STOP.is_set():
        raise EmergencyStop()


def trigger(reason: str = "manual") -> None:
    """Set the stop and run the safe-stop callback once."""
    _STOP.set()
    if not _SAFED.is_set():
        _SAFED.set()
        print(f"\r\n[estop] STOP ({reason}) — zeroing motor torque.", flush=True)
        if _safe_stop_fn is not None:
            try:
                _safe_stop_fn()
            except Exception as exc:  # noqa: BLE001
                print(f"[estop] safe_stop error: {exc}", flush=True)


def _sentinel_watcher() -> None:
    while not _STOP.is_set():
        if os.path.exists(SENTINEL):
            trigger(f"sentinel {SENTINEL}")
            return
        time.sleep(0.05)


def _tty_watcher() -> None:
    import termios
    import tty

    try:
        saved = termios.tcgetattr(sys.stdin)
        tty.setcbreak(sys.stdin.fileno())
    except Exception:  # noqa: BLE001
        return
    try:
        while not _STOP.is_set():
            ready, _, _ = select.select([sys.stdin], [], [], 0.05)
            if ready and sys.stdin.read(1) == "\x08":  # Ctrl+H
                trigger("Ctrl+H")
                return
    finally:
        try:
            termios.tcsetattr(sys.stdin, termios.TCSADRAIN, saved)
        except Exception:  # noqa: BLE001
            pass


def _sig_handler(signum, _frame) -> None:
    trigger(f"signal {signum}")
    raise EmergencyStop()


def arm(safe_stop_fn: Callable[[], None]) -> None:
    """Arm the stop. Must be called from the main thread (installs signal handlers).

    `safe_stop_fn` should zero motor torque (e.g. driver.safe_stop). Clears any
    stale sentinel so a leftover file doesn't trip an instant stop.
    """
    global _safe_stop_fn
    _safe_stop_fn = safe_stop_fn
    _STOP.clear()
    _SAFED.clear()
    try:
        if os.path.exists(SENTINEL):
            os.remove(SENTINEL)
    except OSError:
        pass

    threading.Thread(target=_sentinel_watcher, name="estop-sentinel", daemon=True).start()
    signal.signal(signal.SIGINT, _sig_handler)
    signal.signal(signal.SIGTERM, _sig_handler)
    # SIGHUP: if the launching ssh session drops, safe the arm instead of orphaning it.
    if hasattr(signal, "SIGHUP"):
        signal.signal(signal.SIGHUP, _sig_handler)
    if sys.stdin.isatty():
        threading.Thread(target=_tty_watcher, name="estop-ctrlh", daemon=True).start()

    print(
        f"[estop] ARMED. Stop from any ssh session:  touch {SENTINEL}\n"
        f"        (also: pkill -TERM -f run.py, Ctrl+C, or Ctrl+H in a TTY)",
        flush=True,
    )
