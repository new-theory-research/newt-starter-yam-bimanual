"""A software stand-in for a real YAM rig.

`MockYamDriver` satisfies the `YamDriver` Protocol (driver.py) without any
hardware. It holds a 14D joint state in memory, reports it on
`read_joint_state()`, and on `send_joint_targets()` eases that state toward the
commanded target with a first-order step. Feeding it a chunk of targets thus
produces visibly converging motion, which is enough to exercise the full cloud
loop today and prove out the contract before the real driver lands.
"""

from __future__ import annotations

import numpy as np

from .driver import STATE_DIM, validate_state, validate_targets


class MockYamDriver:
    """In-memory YamDriver: eases toward each commanded target instead of moving metal."""

    def __init__(self, alpha: float = 0.5) -> None:
        # alpha sets how aggressively state chases the target each step
        # (1.0 = snap, smaller = slower approach). Home is all zeros.
        self.alpha = alpha
        self._state = np.zeros(STATE_DIM, dtype=np.float32)

    def read_joint_state(self) -> np.ndarray:
        """Return a validated copy of the current 14D joint state."""
        return validate_state(self._state).copy()

    def send_joint_targets(self, targets: np.ndarray) -> None:
        """Step the internal state toward `targets` (first-order: s += alpha*(t-s))."""
        target = validate_targets(targets)
        self._state = self._state + self.alpha * (target - self._state)

    def close(self) -> None:
        """No hardware to release."""
