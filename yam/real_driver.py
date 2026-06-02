"""RealYamDriver — drives physical bimanual YAM arms via the i2rt stack.

This is the hardware backend behind the YamDriver Protocol. It is written to run
*on the arm host* (the machine with the CAN adapters wired to the arms), which
may be this machine directly or a box reachable over Tailscale. `i2rt` is a
local-CAN library with no network transport, so the remote story is: run this
driver on the host beside the arms; reach that host over Tailscale.

Grounded in the i2rt / gello / allenai YAM stack (see docs/INTEGRATION-SPEC.md
"Real hardware path"). Until we can run it against real arms, treat every value
marked CONFIRM as provisional — especially gripper polarity and home poses.

    per arm:  i2rt get_yam_robot(channel=...).get_joint_pos()      -> (7,) = 6 rad + 1 gripper
              i2rt get_yam_robot(channel=...).command_joint_pos(q) <- (7,)
    bimanual: concat LEFT first -> (14,);  split joints[:7] / joints[7:]

Matches the model's 14D contract: state[0:7]=left, state[7:14]=right, gripper at
per-arm index 6 (normalized [0,1]).
"""

from __future__ import annotations

from typing import Optional, Sequence

import numpy as np

from .driver import STATE_DIM, validate_state, validate_targets

_ARM_DIM = 7  # 6 joint angles + 1 gripper, per arm


class RealYamDriver:
    """Bimanual YAM backend: two i2rt YAM arms, left-first concatenation.

    Args:
        left_channel/right_channel: python-can channel per arm. For SocketCAN
            (Linux) these are interface names like "can0" (bring up with
            `sudo ip link set <chan> up type can bitrate 1000000`). For slcan
            (macOS) they are serial devices like "/dev/tty.usbmodem1234".
        bustype: python-can backend. "socketcan" (default, Linux) uses i2rt's
            get_yam_robot directly; anything else (e.g. "slcan") is opened via
            the standalone `yamcan` package so it works off-Linux.
        gripper_bounds_rad: per-arm (closed_rad, open_rad) — the i2rt gripper
            position (in RADIANS) corresponding to model values 0.0 and 1.0. The
            model speaks normalized [0,1]; i2rt speaks radians, so we MUST convert.
            ⚠️ These bounds are per-rig and UNKNOWN until calibrated on hardware
            (read get_joint_pos()[6]/[13] at fully-closed and fully-open). Default
            None = identity pass-through (WRONG on real hardware — calibrate first).
        hold_position: pass zero_gravity_mode=False so the arms hold pose instead
            of going limp (i2rt defaults to zero-gravity).
    """

    def __init__(
        self,
        left_channel: str = "can1",   # ground truth from the box's robot.yaml:
        right_channel: str = "can0",  # left=can1, right=can0 (NOT the intuitive order!)
        bustype: str = "socketcan",
        gripper_bounds_rad: Optional[Sequence[Sequence[float]]] = None,
        hold_position: bool = True,
    ) -> None:
        # zero_gravity_mode is a confirmed get_yam_robot kwarg; hold pose by
        # default so the arms don't go limp under policy. gripper_type is left at
        # i2rt's default (GripperType.LINEAR_4310 enum — NOT a string); override
        # by extending _open_arm if a rig differs.
        zero_gravity = not hold_position
        self._left = self._open_arm(left_channel, bustype, zero_gravity)
        self._right = self._open_arm(right_channel, bustype, zero_gravity)
        # (closed_rad, open_rad) per arm; None = identity (must calibrate on hw).
        self._grip_bounds = gripper_bounds_rad

    @staticmethod
    def _open_arm(channel: str, bustype: str, zero_gravity: bool):
        """Open one i2rt YAM arm on the chosen backend. Imports are lazy so this
        module loads on a box without i2rt; failures surface here, not at import."""
        if bustype == "socketcan":
            try:
                from i2rt.robots.get_robot import get_yam_robot
            except ImportError as exc:  # pragma: no cover - depends on host
                raise RuntimeError(
                    "i2rt is not installed — RealYamDriver only runs on the YAM arm "
                    "host. Install i2rt there, or use --mock off-host."
                ) from exc
            # CAN motor-on is flaky (intermittent "fail to communicate"); retry a few times.
            import time as _t
            last = None
            for attempt in range(1, 4):
                try:
                    return get_yam_robot(channel=channel, zero_gravity_mode=zero_gravity)
                except Exception as exc:  # noqa: BLE001 - i2rt raises AssertionError on CAN timeout
                    last = exc
                    print(f"[driver] {channel} motor init failed "
                          f"(attempt {attempt}/3): {exc}", flush=True)
                    _t.sleep(1.5)
            raise RuntimeError(f"{channel}: motor init failed after 3 attempts: {last}")
        # Non-SocketCAN (e.g. slcan on macOS) goes through the standalone shim.
        from yamcan import open_yam_arm
        return open_yam_arm(channel, bustype=bustype, zero_gravity_mode=zero_gravity)

    def read_joint_state(self) -> np.ndarray:
        left = np.asarray(self._left.get_joint_pos(), dtype=np.float32)
        right = np.asarray(self._right.get_joint_pos(), dtype=np.float32)
        if left.shape != (_ARM_DIM,) or right.shape != (_ARM_DIM,):
            raise ValueError(
                f"expected ({_ARM_DIM},) per arm, got left={left.shape} right={right.shape}"
            )
        state = np.concatenate([left, right]).astype(np.float32)  # LEFT first
        # i2rt gripper is in radians; the model wants normalized [0,1].
        state[6] = self._rad_to_model(state[6], arm=0)
        state[13] = self._rad_to_model(state[13], arm=1)
        return validate_state(state)

    def send_joint_targets(self, targets: np.ndarray) -> None:
        targets = validate_targets(targets)
        left = targets[:_ARM_DIM].copy()
        right = targets[_ARM_DIM:].copy()
        # model [0,1] gripper -> i2rt radians before commanding.
        left[6] = self._model_to_rad(left[6], arm=0)
        right[6] = self._model_to_rad(right[6], arm=1)
        # ⚠️ Watchdog: YAM faults to damping if not commanded > ~2.5 Hz. The caller
        # (newt receding-horizon loop) must keep this fed; don't add blocking work here.
        self._left.command_joint_pos(left)
        self._right.command_joint_pos(right)

    def _rad_to_model(self, rad: float, arm: int) -> float:
        if self._grip_bounds is None:
            return float(rad)  # uncalibrated: identity (WRONG on hw — calibrate)
        closed, opn = self._grip_bounds[arm]
        return float((rad - closed) / (opn - closed)) if opn != closed else float(rad)

    def _model_to_rad(self, value: float, arm: int) -> float:
        if self._grip_bounds is None:
            return float(value)  # uncalibrated: identity (WRONG on hw — calibrate)
        closed, opn = self._grip_bounds[arm]
        return float(closed + value * (opn - closed))

    def safe_stop(self) -> None:
        """Emergency safe-stop: zero motor torque on both arms (arms go limp).

        i2rt's close() sets all torques to zero ("Robot closed with all torques
        set to zero"), which is our failsafe. Idempotent — safe to call from the
        estop callback and again from the loop's finally.
        """
        self.close()

    def close(self) -> None:
        if getattr(self, "_closed", False):
            return
        self._closed = True
        for arm in (getattr(self, "_left", None), getattr(self, "_right", None)):
            closer = getattr(arm, "close", None)
            if callable(closer):
                try:
                    closer()
                except Exception:  # noqa: BLE001 - best-effort torque-zero
                    pass


# Provisional safe home poses (radians + gripper), from the MolmoAct YAM eval
# harness. CONFIRM on hardware before commanding — wrong home can slam the arms.
HOME_LEFT = np.array([0, -np.pi / 2, -np.pi / 2, -np.pi / 2, np.pi / 2, 0, 1.0], dtype=np.float32)
HOME_RIGHT = np.array([0, -np.pi / 2, np.pi / 2, -np.pi / 2, -np.pi / 2, 0, 1.0], dtype=np.float32)
HOME_STATE = np.concatenate([HOME_LEFT, HOME_RIGHT]).astype(np.float32)
assert HOME_STATE.shape == (STATE_DIM,)
