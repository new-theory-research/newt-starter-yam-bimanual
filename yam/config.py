"""Load the YAM rig config from ~/.config/nt/nt.toml, with sane defaults.

The starter ships `conf/nt.toml.example`; `./scripts/setup` writes the real file.
Override the path with NT_CONFIG.
"""

from __future__ import annotations

import os
import tomllib
from pathlib import Path

CONFIG_PATH = Path(os.environ.get("NT_CONFIG", Path.home() / ".config" / "nt" / "nt.toml"))

DEFAULTS: dict = {
    "model": "molmoact2-yam",
    "arms": {
        "left_channel": "can1",   # ground truth varies per rig — ./scripts/setup confirms
        "right_channel": "can0",
        "bitrate": 1_000_000,
        "bustype": "socketcan",   # "slcan"/"gs_usb" to drive off-Linux via yamcan
    },
    "cameras": {"top": "", "left": "", "right": ""},   # RealSense serials (USB-3!)
    "control": {
        "control_hz": 25.0,        # YAM training cadence
        "max_joint_step": 0.10,    # per-step safety clamp (rad); loosen as you trust it
        "max_actions_per_chunk": 0,  # 0 = full 30-step plan; >0 = receding horizon
    },
    "run": {
        "task": "Fold the towel and place it on the side.",  # in-distribution default
        "max_duration": 120.0,
        "force_ipv4": False,       # set true if the host's IPv6->Modal path is broken
    },
}


def _merge(base: dict, over: dict) -> dict:
    out = dict(base)
    for k, v in (over or {}).items():
        out[k] = _merge(base[k], v) if isinstance(v, dict) and isinstance(base.get(k), dict) else v
    return out


def load() -> dict:
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, "rb") as f:
            return _merge(DEFAULTS, tomllib.load(f))
    return DEFAULTS
