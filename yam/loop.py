"""Glue between the `newt` cloud loop and a YAM backend.

`newt.Robot` drives the rig through two callbacks supplied to its constructor:
`read_state()` produces the observation the model conditions on, and
`execute(chunk)` consumes the action plan the model returns. The task prompt is
NOT part of the observation — it is passed to `robot.run(prompt, ...)`, and the
SDK injects it into each frame (verified against newt._client.robot:
`_build_obs_frame` fills `frame["prompt"]` from the run() arg when the obs dict
omits it). So `read_state` returns just state + images.

    read_state() -> {"state": (14,) float32, "images": {3 cams}}
    execute(chunk: (N, 14) float32) -> send each row as a 14D joint target

execute() carries the real-time control logic, all verified against ground truth
(i2rt source + the model contract):

  * Pacing. `command_joint_pos` is non-blocking and a background loop chases the
    target at >=100 Hz, so dumping all N rows at once makes the arm race to the
    final pose. We space setpoints in wall-clock at `control_hz` (~30 Hz, the YAM
    training period) so the *trajectory* actually plays.
  * Per-step clamp. i2rt clips to joint limits but not per-step deltas. We clamp
    each target to within `max_joint_step` of the *measured* current state, so a
    bad chunk can't slam a joint.
  * Receding horizon. `max_actions_per_chunk` caps how many rows play before the
    loop re-observes and replans.

The horizon N is deliberately not hardcoded: the spec's Outputs section says 30
steps while its Notes section still says 10 (doc inconsistency, 2026-06-02), so
execute() just iterates over whatever rows the chunk actually has.
"""

from __future__ import annotations

import time
from typing import Callable, Dict, Optional, Tuple

import numpy as np


def build_callbacks(
    driver,
    camera_rig,
    max_actions_per_chunk: Optional[int] = None,
    control_hz: Optional[float] = None,
    max_joint_step: Optional[float] = None,
    sleep_fn: Callable[[float], None] = time.sleep,
    before_write: Optional[Callable[[], None]] = None,
) -> Tuple[Callable[[], Dict[str, object]], Callable[[np.ndarray], None]]:
    """Build the (read_state, execute) pair `newt.Robot` expects.

    Args:
        driver: satisfies the YamDriver protocol.
        camera_rig: satisfies the CameraRig protocol.
        max_actions_per_chunk: rows to play before replanning (receding horizon).
            None = play the whole chunk.
        control_hz: wall-clock setpoint rate. None = no pacing (mock/dry-run/tests).
            The live path should set this (~30 Hz) so the trajectory plays instead
            of the arm racing to the chunk's final pose.
        max_joint_step: max |target - current| per element per step (radians for
            joints; the gripper rides along in the same vector). None = no clamp.
            A safety governor against a bad chunk; clamps against MEASURED state.
        sleep_fn: injected for testing (pass a fake clock to assert pacing without
            real sleeps).

    The prompt is intentionally absent here — it belongs to `robot.run(prompt)`.
    """
    control_dt = (1.0 / control_hz) if control_hz else 0.0

    def read_state() -> Dict[str, object]:
        return {
            "state": driver.read_joint_state(),
            "images": camera_rig.read(),
        }

    def execute(chunk: np.ndarray) -> None:
        rows = chunk if max_actions_per_chunk is None else chunk[:max_actions_per_chunk]
        n = len(rows)
        for i, row in enumerate(rows):
            if before_write is not None:
                before_write()  # may raise (e.g. estop.check) to abort before any write
            target = np.asarray(row, dtype=np.float32)
            if max_joint_step is not None:
                current = driver.read_joint_state()
                delta = np.clip(target - current, -max_joint_step, max_joint_step)
                target = (current + delta).astype(np.float32)
            driver.send_joint_targets(target)
            if control_dt and i < n - 1:  # no trailing sleep after the last setpoint
                sleep_fn(control_dt)

    return read_state, execute
