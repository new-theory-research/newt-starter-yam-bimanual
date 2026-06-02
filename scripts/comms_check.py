"""Energized comms check: read joint state from YAM arm(s) via i2rt.

READ-ONLY: instantiating i2rt holds the arm at its CURRENT pose (it reads
position and commands that same position). No trajectory, no homing, no jump.
Still, this is the first time the motors engage — run with a human at the e-stop.

Usage:  comms_check.py [channel ...]      (default: can0)

Prints each arm's 7D vector (6 joint angles in radians + 1 gripper), so we can
confirm the per-arm layout against the model contract before driving anything.
"""

import sys

import numpy as np
from i2rt.robots.get_robot import get_yam_robot

channels = sys.argv[1:] or ["can0"]

for ch in channels:
    print(f"== {ch} ==", flush=True)
    try:
        robot = get_yam_robot(channel=ch, zero_gravity_mode=False)
    except Exception as exc:  # noqa: BLE001
        print(f"  FAILED to open {ch}: {type(exc).__name__}: {exc}", flush=True)
        continue
    try:
        q = np.asarray(robot.get_joint_pos(), dtype=float)
        print(f"  raw {q.shape}: {np.round(q, 4)}", flush=True)
        if q.shape == (7,):
            print(f"  6 joints (rad): {np.round(q[:6], 4)}   gripper: {round(float(q[6]), 4)}", flush=True)
    finally:
        close = getattr(robot, "close", None)
        if callable(close):
            close()
print("comms check done", flush=True)
