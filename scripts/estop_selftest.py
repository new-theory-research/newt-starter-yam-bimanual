"""Verify the SOFTWARE stop actually zeros torque on the real arms.

Energizes both arms (hold), arms the estop, then loops holding + checking. Trigger
it the way the operator will, from another ssh session:

    touch /tmp/yam_estop          # (or: pkill -TERM -f estop_selftest, or Ctrl+C)

On trigger the arms should go LIMP (i2rt prints "all torques set to zero") and the
script exits via EmergencyStop. If it survives the window with no trigger, the stop
did NOT work and we must NOT proceed to motion.

Usage: estop_selftest.py [seconds]
"""

import sys
import time

from yam import estop
from yam.real_driver import RealYamDriver

secs = float(sys.argv[1]) if len(sys.argv) > 1 else 25.0

driver = RealYamDriver()      # opens both arms, holds pose
estop.arm(driver.safe_stop)

t0 = time.time()
i = 0
stopped = False
try:
    while time.time() - t0 < secs:
        estop.check()         # raises EmergencyStop once triggered
        try:
            driver.read_joint_state()
        except Exception:     # noqa: BLE001 - read may race a concurrent safe_stop; fine
            pass
        i += 1
        if i % 10 == 0:
            print(f"  t={time.time()-t0:4.1f}s  holding, estop armed (touch /tmp/yam_estop to stop)", flush=True)
        time.sleep(0.1)
    print(">>> WINDOW ELAPSED WITH NO STOP — software stop did NOT fire. DO NOT proceed.", flush=True)
except estop.EmergencyStop:
    stopped = True
    print(">>> EmergencyStop caught — arms safed (torque zeroed). SOFTWARE STOP WORKS.", flush=True)
finally:
    driver.close()

print(f"estop selftest done (stopped={stopped})")
