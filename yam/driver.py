"""The hardware-facing contract for a bimanual YAM rig.

Everything above this line talks to the cloud (`newt`); everything below it
talks to metal. The model contract is fixed by Molmo-Act-2 (see
docs/INTEGRATION-SPEC.md):

    state  : float32 (14,)        14D bimanual joint state
    action : float32 (14,) rows   14D joint targets, joint-space (no IK)

A concrete driver only has to (a) report the current 14D joint state and
(b) accept 14D joint targets. Cameras are handled separately by CameraRig so a
driver can be swapped (mock ↔ real ↔ Tailscale) without touching vision.

NOTE: the per-index joint layout of the 14-vector is NOT specified by the NT
docs (see DX-FRICTION.md). It is captured here as JOINT_LAYOUT so that the day
we confirm it against the real YAM SDK, there is exactly one place to fix.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

import numpy as np

STATE_DIM = 14  # 14D bimanual joint state, per /docs/models/molmoact2/yam
ACTION_HORIZON = 30  # rows per action chunk (Outputs section, refreshed 2026-06-02).
# NOTE: the page's Notes section still says 10 — doc inconsistency. We treat the
# Outputs section (30) as authoritative, but execute() never relies on this: it
# iterates over whatever rows the chunk actually contains.

# Layout CONFIRMED from three sources: the HF sample state
# (allenai/MolmoAct2-BimanualYAM, grippers near ~0.99 at idx 6/13), the i2rt/gello
# YAM stack (BimanualRobot concatenates left-first, splits joints[:7]/joints[7:]),
# and the allenai docs ("per-arm 7-D x 2 arms, absolute joint-pose control").
# So: left arm idx 0-6, right arm idx 7-13; each = 6 joint angles (radians) + 1
# gripper (normalized [0,1], 0=closed/1=open) at the last index of its block.
# Remaining hardware caveat: gripper polarity varies by build (some invert), so a
# RealYamDriver should expose polarity as a config knob — see docs/INTEGRATION-SPEC.md.
JOINT_LAYOUT: tuple[str, ...] = (
    "left/joint_0", "left/joint_1", "left/joint_2",
    "left/joint_3", "left/joint_4", "left/joint_5", "left/gripper",
    "right/joint_0", "right/joint_1", "right/joint_2",
    "right/joint_3", "right/joint_4", "right/joint_5", "right/gripper",
)
assert len(JOINT_LAYOUT) == STATE_DIM


@runtime_checkable
class YamDriver(Protocol):
    """Minimal contract a YAM backend must satisfy to be driven by the cloud loop."""

    def read_joint_state(self) -> np.ndarray:
        """Return the current joint state as float32 shape (14,).

        Order must match JOINT_LAYOUT. Units are whatever the model was trained
        on (radians for revolute joints assumed; gripper representation TBD).
        """
        ...

    def send_joint_targets(self, targets: np.ndarray) -> None:
        """Command a single 14D joint-target vector (float32, shape (14,)).

        Called once per step within an action chunk. Implementations should be
        non-blocking enough to keep up with the control clock; clamping to safe
        joint limits is the driver's responsibility.
        """
        ...

    def close(self) -> None:
        """Release hardware resources (sockets, serial handles, etc.)."""
        ...


def validate_state(state: np.ndarray) -> np.ndarray:
    """Coerce/validate a state vector to the model contract: float32 (14,)."""
    arr = np.asarray(state, dtype=np.float32)
    if arr.shape != (STATE_DIM,):
        raise ValueError(f"state must be shape ({STATE_DIM},), got {arr.shape}")
    return arr


def validate_targets(targets: np.ndarray) -> np.ndarray:
    """Coerce/validate a single action row to float32 (14,)."""
    arr = np.asarray(targets, dtype=np.float32)
    if arr.shape != (STATE_DIM,):
        raise ValueError(f"joint targets must be shape ({STATE_DIM},), got {arr.shape}")
    return arr
