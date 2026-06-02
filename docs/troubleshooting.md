# Hardware troubleshooting (YAM CAN + RealSense)

The YAM rig is brittle, and it's not just you: the i2rt repo has open, **maintainer-unanswered**
issues matching these errors verbatim (#27 "Motor loss communication", #17 "fail to communicate
with the motor …"). Root causes below are well-sourced from the Damiao motor manual, the i2rt
driver source, Intel's RealSense docs, and CAN engineering — but i2rt has published no official
fix, so treat the YAM-side causes as strong inference. Sources at the bottom.

## The single most important insight: cameras can *cause* the CAN dropouts

The Damiao motors fault to damping if they don't get a command within **400 ms**. The i2rt control
loop runs at **250 Hz (4 ms)** and warns when a cycle exceeds 7 ms. On one box also pushing **3
RealSense cameras**, a slow `wait_for_frames()`, GC pause, or GIL contention can stall the motor
loop past 400 ms → the motor raises **"loss communication"** → looks like a CAN fault but is
actually starvation. This matches our "transient, different-motor-each-run, recovers on retry."

**Mitigation:** isolate camera I/O from the motor loop (separate thread/process), and **test it**
— run the arms alone vs. arms + 3 cameras and watch for the difference. Highest-value experiment.

## CAN / YAM — "loss communication" / motor-on failure

`loss communication` = Damiao motor fault code **D**. It's either the host not getting a CAN
response (bus/adapter) or the motor's own watchdog firing (starvation, above). Fix checklist,
high-confidence first:

1. **Check termination.** Power off, measure CAN-H↔CAN-L per arm = **~60 Ω** (two 120 Ω, one at
   each end). Missing/extra termination "works temporarily, fails intermittently" — exactly our
   pattern. i2rt doesn't document the scheme; verify it physically.
2. **Reflash USB-CAN adapters to candlelight firmware** (native SocketCAN, stable). slcan/slcand
   is widely reported unreliable on Linux and can drop with no bus fault. Confirm which firmware
   your CANable-class adapters run.
3. **Power: independent 24 V per arm**, sized for stall current, short/thick leads. Damiao motors
   carry 24 V + CAN in one daisy-chained XT30 connector; a brownout on a shared rail shows up as
   undervoltage/comm-loss faults and bus glitches → "different motor each run," "power-cycle fixed it."
4. **Keep the control loop hot (>2.5 Hz, ideally 250 Hz).** See the camera-starvation point above.
5. **Recovery:** i2rt has *no* transport auto-reconnect (retries motor-on 15×, clean-error 3×, then
   hard-fails). For a stuck bus: `scripts/reset_all_can.sh`, then **power-cycle the arm**.

### NEVER hand-move powered-off arms
DM4310/4340 have **single-turn absolute encoders with no multi-turn battery backup**; the *host*
tracks the revolution count and only while powered. Hand-moving a powered-off joint (esp. grippers,
which travel >2π) desyncs the tracked position → enable throws an error / needs re-init. **Fix:
power-cycle the arm and re-run `python i2rt/motor_config_tool/set_zero.py --channel canX --motor_id N`
per motor**, and recalibrate grippers (start fully closed). To reposition a live arm, use the
**limp/torque-zero state** (the e-stop) instead — motors stay initialized.

## RealSense — stalls, disconnects, USB-2 fallback

- **Kernel 6.17 is unsupported by `librealsense2-dkms`** (HWE 5.15/5.19/6.5 only). On new kernels,
  build from source with **`-DFORCE_RSUSB_BACKEND=true`** (user-space backend, no kernel patch) —
  Intel notes it's "less stable," which contributes to intermittent stalls. Or run cameras under a
  supported kernel. Ensure `uvcvideo` is loaded (`sudo modprobe uvcvideo`; persist it).
- **`Couldn't resolve requests`** = invalid stream profile. **6 fps is not a valid mode** — use
  5/15/30. Enumerate real profiles with `rs-enumerate-devices`.
- **USB-2 (480M) fallback** (`lsusb -t` shows 480M not 5000M): a D405 won't stream on USB-2. Usually
  a USB-2/marginal cable (D405 wants a USB-3 micro-B→USB-A cable; dislikes micro-B→USB-C), or a
  connector-seating defect on some units. Use a known-good short USB-3 cable; replug; verify 5000M.
- **`Frame didn't arrive`** — usually multi-camera USB bandwidth. **Put the 3 cameras on separate
  USB-3 host controllers** (not one hub); add a PCIe USB-3 card if needed. If hubbing, use a
  **mains-powered** USB-3 hub. Also: disable USB autosuspend (`usbcore.autosuspend=-1`); use
  `try_wait_for_frames()` + a longer timeout + `dev.hardware_reset()` on stall; lower fps/res.
- **One camera intermittently dead** (works, then times out, even alone): firmware/cable/thermal/
  unit defect. `rs-fw-update -l` then update all 3 to matching firmware; swap cable; check `dmesg`
  for `-71/-110` USB errors at the drop; if it fails across cables/ports, suspect the unit.
- **Permissions:** install `config/99-realsense-libusb.rules` and add the user to `plugdev`.

## Prioritized rig setup (do these once)
CAN: verify 60 Ω termination · candlelight firmware · independent 24 V/arm · separate CAN channel/arm.
Cameras: separate USB-3 controllers · powered hub if hubbing · known-good USB-3 cables · matching
firmware · udev rules + plugdev · valid profiles (5/15/30 fps).
Software: isolate camera I/O from the 250 Hz motor loop · `try_wait_for_frames` + `hardware_reset` ·
never hand-move powered-off arms.

## Sources
i2rt issues #27/#17/#18 (unanswered) · i2rt README & `dm_driver.py` (250 Hz/7 ms loop, 400 ms
watchdog, no auto-reconnect, set_zero/reset_all_can) · Damiao DM-J4310 manual (24 V, XT30 power+CAN
daisy-chain, fault codes, single-turn absolute encoder) · doc.i2rt.com/products/yam-cell · canable.io
(candlelight vs slcan) · librealsense distribution_linux.md (DKMS kernel support; RSUSB backend) ·
librealsense issues #14033, #9452, #13495, #14030, #10398, #7626, #5828, #1086 · Intel multi-camera
stability guidance · librealsense Troubleshooting-Q&A wiki.
