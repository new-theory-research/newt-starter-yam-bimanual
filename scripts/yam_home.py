"""Safely reset the YAM arms to a home/rest pose.

Two modes:

  yam_home.py --capture [--seconds 12]
      Arms go COMPLIANT (gravity-comp / back-drivable). Position them by hand to a
      good rest pose; after the countdown it reads and saves that pose as home.
      No commanded motion to a guessed target — the home is whatever YOU set.

  yam_home.py
      Gently interpolates the current pose -> saved home (or the reference home if
      none captured), in small clamped steps with the e-stop armed.

Both energize the motors — run with a hand on the e-stop (touch /tmp/yam_estop).
"""

import argparse
import json
import os
import time

import numpy as np

from yam import estop
from yam.real_driver import HOME_STATE, RealYamDriver

HOME_FILE = os.path.expanduser("~/yam_home.json")
STEP = 0.03        # rad per step toward home (gentle)
HZ = 25.0
MAX_HOMING_S = 40.0


def load_home() -> np.ndarray:
    if os.path.exists(HOME_FILE):
        return np.array(json.load(open(HOME_FILE)), dtype=np.float32)
    print(f"[home] no captured home; using reference {HOME_FILE} absent -> eval-harness pose")
    return HOME_STATE.copy()


def capture(seconds: int) -> None:
    driver = RealYamDriver(hold_position=False)  # gravity-comp: back-drivable
    estop.arm(driver.safe_stop)
    try:
        print("[capture] arms are COMPLIANT — position them by hand now.", flush=True)
        for s in range(seconds, 0, -1):
            estop.check()
            print(f"  capturing in {s:>2}s ...", flush=True)
            time.sleep(1)
        q = driver.read_joint_state()
        json.dump([float(x) for x in q], open(HOME_FILE, "w"))
        print(f"[capture] saved home -> {HOME_FILE}\n          {np.round(q, 3)}", flush=True)
    except estop.EmergencyStop:
        print("[capture] stopped by e-stop; nothing saved.", flush=True)
    finally:
        driver.close()


def home() -> None:
    target = load_home()
    driver = RealYamDriver(hold_position=True)
    estop.arm(driver.safe_stop)
    print(f"[home] interpolating to {np.round(target, 3)} (gentle, e-stop armed)", flush=True)
    dt = 1.0 / HZ
    t0 = time.time()
    try:
        while time.time() - t0 < MAX_HOMING_S:
            estop.check()
            cur = driver.read_joint_state()
            err = target - cur
            if float(np.abs(err).max()) < 0.01:
                print("[home] reached.", flush=True)
                break
            driver.send_joint_targets((cur + np.clip(err, -STEP, STEP)).astype(np.float32))
            time.sleep(dt)
        else:
            print("[home] timed out before reaching target.", flush=True)
    except estop.EmergencyStop:
        print("[home] stopped by e-stop.", flush=True)
    finally:
        driver.close()


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--capture", action="store_true", help="record the current hand-set pose as home")
    p.add_argument("--seconds", type=int, default=12, help="capture countdown (time to hand-position)")
    args = p.parse_args()
    if args.capture:
        capture(args.seconds)
    else:
        home()
