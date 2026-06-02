"""CameraRig backed by Intel RealSense cameras, addressed by serial.

The box's 3 cameras (dex-reflex/robot.yaml): a D435 overhead + two D405 wrists.
We stream color (rgb8) from each and resize to the model's 378x378 CHW. Pipelines
are started serially — the dex-reflex rig notes that concurrent RealSense starts
can race ("wait_for_frames timed out").

Requires pyrealsense2 + the uvcvideo kernel module loaded (`sudo modprobe uvcvideo`;
make it persistent in /etc/modules-load.d so it survives reboot). Imports are lazy
so this module loads on a machine without cameras.

Satisfies the CameraRig protocol in cameras.py.
"""

from __future__ import annotations

from typing import Dict, Optional

import numpy as np

from .cameras import CAMERA_NAMES, FRAME_SIZE

# Serials from dex-reflex/robot.yaml (confirmed live via pyrealsense2 on the box).
REALSENSE_SERIALS: Dict[str, str] = {
    "top_cam": "420222071940",   # D435 overhead
    "left_cam": "353322271521",  # D405 left wrist
    "right_cam": "323622270916",  # D405 right wrist
}


class RealSenseCameraRig:
    """Three RealSense color streams → the model's fixed (top, left, right) CHW frames."""

    def __init__(
        self,
        serials: Optional[Dict[str, str]] = None,
        width: int = 640,
        height: int = 480,  # reverted to 640x480 — the config that produced real motion on the can
        fps: int = 15,  # half of 30 to ease USB bandwidth, but a mode the cameras actually support
                        # (6 fps is not a valid 640x480 mode -> "Couldn't resolve requests")
    ) -> None:
        import pyrealsense2 as rs  # lazy: only on the arm host

        serials = serials or REALSENSE_SERIALS
        self._pipes = {}
        for name in CAMERA_NAMES:  # fixed order; start one at a time (avoids the race)
            cfg = rs.config()
            cfg.enable_device(serials[name])
            cfg.enable_stream(rs.stream.color, width, height, rs.format.rgb8, fps)
            pipe = rs.pipeline()
            pipe.start(cfg)
            self._pipes[name] = pipe

    def read(self) -> Dict[str, np.ndarray]:
        out: Dict[str, np.ndarray] = {}
        for name in CAMERA_NAMES:
            frames = None
            for attempt in range(3):  # tolerate transient frame stalls
                try:
                    frames = self._pipes[name].wait_for_frames(timeout_ms=10000)
                    break
                except RuntimeError as exc:
                    if attempt == 2:
                        raise RuntimeError(f"{name} camera stalled: {exc}") from exc
            color = frames.get_color_frame()
            rgb = np.asanyarray(color.get_data())  # (H, W, 3) RGB uint8
            out[name] = _rgb_to_model_frame(rgb)
        return out

    def close(self) -> None:
        for pipe in self._pipes.values():
            try:
                pipe.stop()
            except Exception:
                pass


def _rgb_to_model_frame(rgb: np.ndarray) -> np.ndarray:
    """RGB HWC uint8 (any size) -> RGB CHW uint8 378x378. RealSense is already RGB."""
    import cv2  # lazy

    if rgb.ndim != 3 or rgb.shape[2] != 3:
        raise ValueError(f"expected HWC RGB frame, got {rgb.shape}")
    resized = cv2.resize(rgb, (FRAME_SIZE, FRAME_SIZE), interpolation=cv2.INTER_AREA)
    return np.transpose(resized, (2, 0, 1)).astype(np.uint8)
