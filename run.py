#!/usr/bin/env python3
"""Drive bimanual YAM arms with MolmoAct-2 via the newt SDK.

    python run.py                 # run the configured task on the real arms
    python run.py --task "..."    # override the task
    python run.py --mock          # software arms + synthetic cameras (no hardware)
    python run.py --dry-run       # pump synthetic obs through the loop (no SDK, no network)
    python run.py --reset         # gently home the arms (no inference)

Config lives in ~/.config/nt/nt.toml (see conf/nt.toml.example; run ./scripts/setup).
Stop at any time: `touch /tmp/yam_estop` from any ssh session | Ctrl+C | Ctrl+H (TTY).
This is a SOFTWARE stop (zeros torque). Keep a real power-cut within reach too.
"""

from __future__ import annotations

import argparse
import os
import sys
import time

from yam import config


def _build_backend(cfg, mock: bool):
    if mock:
        from yam.cameras import SyntheticCameraRig
        from yam.mock_driver import MockYamDriver
        return MockYamDriver(), SyntheticCameraRig()
    from yam.real_driver import RealYamDriver
    from yam.realsense_rig import RealSenseCameraRig
    a, c = cfg["arms"], cfg["cameras"]
    driver = RealYamDriver(left_channel=a["left_channel"], right_channel=a["right_channel"],
                           bustype=a["bustype"])
    serials = ({"top_cam": c["top"], "left_cam": c["left"], "right_cam": c["right"]}
               if c.get("top") else None)
    return driver, RealSenseCameraRig(serials=serials)


def main() -> None:
    cfg = config.load()
    ap = argparse.ArgumentParser(description="Drive bimanual YAM arms with MolmoAct-2.")
    ap.add_argument("--task", default=cfg["run"]["task"])
    ap.add_argument("--seconds", type=float, default=cfg["run"]["max_duration"])
    ap.add_argument("--mock", action="store_true", help="software arms + synthetic cameras")
    ap.add_argument("--dry-run", action="store_true", help="no SDK/network; pump synthetic obs")
    ap.add_argument("--reset", action="store_true", help="gently home the arms, no inference")
    ap.add_argument("--ipv4", action="store_true", default=cfg["run"]["force_ipv4"])
    ap.add_argument("--max-joint-step", type=float, default=cfg["control"]["max_joint_step"])
    args = ap.parse_args()

    if args.reset:
        import runpy
        sys.argv = ["yam_home.py"]
        runpy.run_path(os.path.join(os.path.dirname(__file__), "scripts", "yam_home.py"),
                       run_name="__main__")
        return

    if args.ipv4 or os.environ.get("NT_FORCE_IPV4"):
        from yam.warm import force_ipv4
        force_ipv4()

    from yam.loop import build_callbacks
    driver, rig = _build_backend(cfg, mock=args.mock or args.dry_run)  # dry-run never touches hardware

    # --- dry run: exercise the loop with no SDK, no network, no inference ---
    if args.dry_run:
        import numpy as np
        read_state, execute = build_callbacks(driver, rig)
        obs = read_state()
        print("state:", obs["state"].shape, "images:", {k: v.shape for k, v in obs["images"].items()})
        chunk = np.full((30, 14), 0.5, dtype=np.float32)
        for _ in range(20):
            read_state()
            execute(chunk)
        print("dry run OK")
        driver.close()
        rig.close()
        return

    # --- live inference ---
    api_key = os.environ.get("NT_API_KEY")
    if not api_key:
        sys.exit("NT_API_KEY is not set (export it).")
    if os.environ.get("NT_INFERENCE_URL"):
        print(f"⚠️  NT_INFERENCE_URL is set ({os.environ['NT_INFERENCE_URL']}). The SDK routes "
              f"ALL models there, bypassing discovery — unset it for normal routing.")

    import newt
    from yam import estop, warm

    warm.warm_until_hot(api_key, cfg["model"])

    on_real = not args.mock
    step_guard = None
    if on_real:
        estop.arm(driver.safe_stop)
        step_guard = estop.check

    read_state, execute = build_callbacks(
        driver, rig,
        control_hz=cfg["control"]["control_hz"],
        max_joint_step=args.max_joint_step,
        max_actions_per_chunk=(cfg["control"]["max_actions_per_chunk"] or None),
        before_write=step_guard,
    )

    # Registry/model cold-start retry (a cold Modal app can time out the first fetch).
    robot = None
    for attempt in range(1, 7):
        try:
            robot = newt.Robot(api_key=api_key, read_state=read_state, execute=execute,
                               model=cfg["model"])
            break
        except Exception as exc:  # noqa: BLE001
            print(f"[run] registry not ready (attempt {attempt}/6: {type(exc).__name__}); retry 4s")
            time.sleep(4)
    if robot is None:
        sys.exit("[run] NT registry unreachable after retries")

    print(f"[run] task={args.task!r}  model={cfg['model']}  dur={args.seconds}s")
    try:
        result = robot.run(args.task, max_duration=args.seconds)
        print("stop_reason:", getattr(result, "stop_reason", result))
    except BaseException as exc:  # estop / Ctrl+C / error -> safe the arms
        print(f"[run] stopping ({type(exc).__name__}) — safing arms.")
        if hasattr(driver, "safe_stop"):
            driver.safe_stop()
        if not isinstance(exc, getattr(estop, "EmergencyStop", ())):
            raise
    finally:
        driver.close()
        rig.close()


if __name__ == "__main__":
    main()
