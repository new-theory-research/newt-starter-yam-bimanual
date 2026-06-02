# Bring-up ladder

Bring a bimanual YAM rig up in safe stages. Each step is safe on its own; don't skip to motion.
Keep a hand on the stop (`touch /tmp/yam_estop` from another ssh session) for every energized step.

### 0. Host prep
```bash
sudo ip link set can0 up type can bitrate 1000000   # confirm your channel names
sudo ip link set can1 up type can bitrate 1000000
sudo modprobe uvcvideo                               # if cameras don't enumerate
./scripts/setup --report-only                        # cameras on USB-3? CAN up? uvcvideo loaded?
```

### 1. Comms check — no motion
```bash
python scripts/comms_check.py can0 can1
```
Reads each arm's 7-D state (6 joints rad + gripper [0,1]). Instantiating i2rt energizes the arm
to *hold* its current pose (no commanded motion). Confirms both arms talk + the layout is sane.

### 2. Verify the stop — before you trust it
```bash
python scripts/estop_selftest.py 60      # then, from another ssh tab: touch /tmp/yam_estop
```
The arm should go limp and the script print `SOFTWARE STOP WORKS`. The software stop **zeros
torque** (limp) — it does not cut power, so motor lights stay on. Judge success by the arm going
slack, not by the lights. **There is no substitute for a real power-cut; keep one reachable.**

### 3. Home — gentle reset
```bash
python scripts/yam_home.py --capture     # arms go compliant; hand-set a rest pose; it saves it
python run.py --reset                     # later: gently interpolate back to that home
```

### 4. Cloud path with software arms
```bash
python run.py --mock
```
Real MolmoAct-2 inference, software arms — proves auth, routing, cameras-shape, and the loop
without moving anything.

### 5. Model in the loop — real arms
```bash
python run.py
```
Starts conservative (per-step clamp from nt.toml). Loosen `max_joint_step` (→ ~0.5) and execute
the full 30-step plan (`max_actions_per_chunk = 0`) once you trust the motion. Tasks take
minutes — inference is ~1–2 s/cycle warm, and the arm only re-plans that often.

## Reliability notes
- **CAN:** transient "motor loss communication" on init is normal (i2rt retries, recovers). A
  hard fail needs an **arm power-cycle**. Don't power arms off to hand-move them (leaves motors
  un-init); use the limp state from the stop instead.
- **Cameras:** must be USB-3; a wedged one → `sudo python scripts/usb_reset_realsense.py` or a
  physical replug.
- **Cold start:** `run.py` warms the model first; expect ~30–60 s on the first run.
