"""The vision-facing contract for a bimanual YAM rig.

Cameras are deliberately split from the joint driver (see driver.py) so the
backend can be swapped (mock <-> real <-> Tailscale) without touching how we
read pixels. A CameraRig only has to produce the three model cameras in the
fixed order the contract demands.

The model contract is fixed by Molmo-Act-2 (see docs/INTEGRATION-SPEC.md):

    images : dict with exactly 3 keys, FIXED order
             top_cam, left_cam, right_cam
    each   : uint8 (3, 378, 378)   RGB, channels-first (CHW), 378x378

OpenCV is an optional dependency (the `newt[hardware]` extra). Its import is
kept lazy so the SyntheticCameraRig — and therefore the whole mock pipeline —
runs on a machine with zero cameras and no opencv installed.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

import numpy as np

# Fixed camera order required by the model contract. read() must return a dict
# whose keys are exactly these, in this order.
CAMERA_NAMES: tuple[str, ...] = ("top_cam", "left_cam", "right_cam")

FRAME_SIZE = 378  # square frame edge, per /docs/models/molmoact2/yam
# Per-camera frame shape: RGB, channels-first (CHW).
FRAME_SHAPE: tuple[int, int, int] = (3, FRAME_SIZE, FRAME_SIZE)


@runtime_checkable
class CameraRig(Protocol):
    """Minimal contract a camera backend must satisfy to feed the cloud loop."""

    def read(self) -> dict[str, np.ndarray]:
        """Return one frame per camera as uint8 (3, 378, 378), RGB CHW.

        The returned dict has exactly the keys in CAMERA_NAMES, in that order.
        """
        ...

    def close(self) -> None:
        """Release camera resources (capture handles, etc.)."""
        ...


def to_model_frame(frame: np.ndarray) -> np.ndarray:
    """Convert one OpenCV-style frame to the model's per-camera format.

    Input is what cv2 hands back: HWC, BGR, uint8, any size. Output is the
    contract frame: uint8 (3, 378, 378), RGB, channels-first. Resizing uses
    cv2.resize with INTER_AREA (the right choice for downscaling).
    """
    import cv2  # lazy: only OpenCVCameraRig needs opencv

    if frame.ndim != 3 or frame.shape[2] != 3:
        raise ValueError(f"expected HWC frame with 3 channels, got {frame.shape}")
    resized = cv2.resize(frame, (FRAME_SIZE, FRAME_SIZE), interpolation=cv2.INTER_AREA)
    rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
    chw = np.transpose(rgb, (2, 0, 1))  # HWC -> CHW
    return np.ascontiguousarray(chw, dtype=np.uint8)


def validate_frame(frame: np.ndarray) -> np.ndarray:
    """Coerce/validate a single camera frame to the contract: uint8 (3,378,378)."""
    arr = np.asarray(frame, dtype=np.uint8)
    if arr.shape != FRAME_SHAPE:
        raise ValueError(f"frame must be shape {FRAME_SHAPE}, got {arr.shape}")
    return arr


class OpenCVCameraRig:
    """Capture the three model cameras from OpenCV device indices.

    `indices` maps each model camera to a cv2.VideoCapture device index, e.g.
    {"top_cam": 0, "left_cam": 1, "right_cam": 2}. Requires opencv (the
    `newt[hardware]` extra); cv2 is imported lazily at construction.
    """

    def __init__(self, indices: dict[str, int]) -> None:
        missing = set(CAMERA_NAMES) - set(indices)
        if missing:
            raise ValueError(f"missing camera indices for: {sorted(missing)}")

        import cv2  # lazy: hardware-only path

        # Keep capture order fixed to CAMERA_NAMES regardless of dict order.
        self._caps: dict[str, "cv2.VideoCapture"] = {}
        for name in CAMERA_NAMES:
            cap = cv2.VideoCapture(indices[name])
            if not cap.isOpened():
                # Release whatever we already opened before bailing out.
                for opened in self._caps.values():
                    opened.release()
                raise RuntimeError(f"could not open camera {name} (index {indices[name]})")
            self._caps[name] = cap

    def read(self) -> dict[str, np.ndarray]:
        frames: dict[str, np.ndarray] = {}
        for name in CAMERA_NAMES:
            ok, frame = self._caps[name].read()
            if not ok:
                raise RuntimeError(f"failed to read frame from camera {name}")
            frames[name] = to_model_frame(frame)
        return frames

    def close(self) -> None:
        for cap in self._caps.values():
            cap.release()
        self._caps.clear()


class SyntheticCameraRig:
    """Deterministic synthetic cameras for the hardware-free mock pipeline.

    Produces seeded, per-camera frames (a fixed gradient base plus seeded
    noise) so the full cloud loop can run with zero cameras and no opencv.
    Frames change each read() but the sequence is reproducible for a given seed.
    """

    def __init__(self, seed: int = 0) -> None:
        self._rng = np.random.default_rng(seed)
        # A static gradient gives each camera a distinct, recognizable base so
        # frames are not pure noise; noise on top keeps successive reads moving.
        self._bases = {
            name: self._gradient(i) for i, name in enumerate(CAMERA_NAMES)
        }

    @staticmethod
    def _gradient(channel_offset: int) -> np.ndarray:
        """A fixed RGB CHW gradient, shifted per camera so each looks different."""
        ramp = np.linspace(0, 255, FRAME_SIZE, dtype=np.float32)
        row = np.broadcast_to(ramp, (FRAME_SIZE, FRAME_SIZE))  # H x W, varies along W
        col = row.T  # varies along H
        base = np.stack(
            [
                (row + channel_offset * 40) % 256,
                (col + channel_offset * 40) % 256,
                ((row + col) / 2 + channel_offset * 40) % 256,
            ]
        )
        return base.astype(np.float32)  # CHW

    def read(self) -> dict[str, np.ndarray]:
        frames: dict[str, np.ndarray] = {}
        for name in CAMERA_NAMES:
            noise = self._rng.integers(-20, 21, size=FRAME_SHAPE)
            frame = np.clip(self._bases[name] + noise, 0, 255).astype(np.uint8)
            frames[name] = frame
        return frames

    def close(self) -> None:
        # Nothing to release; defined to satisfy the CameraRig protocol.
        pass
