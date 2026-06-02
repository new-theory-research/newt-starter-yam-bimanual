# Driving YAM from macOS (no SocketCAN)

The deploy target is the Linux box wired to the arms. But you can scaffold and even *drive* the
arms from a Mac, because the bundled **`yamcan`** package routes i2rt's CAN layer onto a
non-SocketCAN python-can backend.

## What works on macOS today
- `python run.py --mock` and `--dry-run` (no hardware, no SocketCAN).
- Live MolmoAct-2 inference (it's just a WebSocket) — the Mac reached the endpoint fine.
- USB-CAN to the arms **if** your adapter has a macOS-capable backend (see below).

## CAN on macOS — `yamcan`
SocketCAN is Linux-only, but i2rt's `CanInterface` takes a `bustype`, so any python-can backend
works. `yamcan` flips it:

```python
import yamcan
print(yamcan.scan())                                  # what adapter / which backend?
arm = yamcan.open_yam_arm("/dev/tty.usbmodemXXXX",     # slcan: serial device as channel
                          bustype="slcan", zero_gravity_mode=False)
```
Then set `bustype = "slcan"` (or `"gs_usb"`) and the per-arm `*_channel` in `~/.config/nt/nt.toml`,
and `RealYamDriver` routes through `yamcan` automatically.

`python -m yamcan` scans for adapters and guesses the backend:
- **CANable / CANtact (slcan firmware)** → `slcan` (a `/dev/tty.usbmodem*` serial device).
- **candleLight / gs_usb** → `gs_usb` (needs `pip install "python-can[gs_usb]"` + `libusb`,
  e.g. `brew install libusb`). Note: gs_usb appears as a raw USB device, **not** a serial port.
- **CANalyst-II / usb2can** → Windows-only chipset, dead end on macOS.

## ⚠️ Caveat
i2rt's control loop wants **≥100 Hz**. SocketCAN on Linux sustains that; slcan-over-USB-serial
through Python on macOS may not, for two arms — jitter on a real-time PD loop is a safety issue,
not just a perf nit. **Verify the achievable loop rate before trusting motion on macOS.** Use the
Mac path for dev/inference; do real motion on the Linux box.

## RealSense on macOS
`pyrealsense2` has no macOS arm64 wheels. `brew install librealsense` gives the C++ SDK with
Apple Silicon support; build the Python bindings from source against it if you need cameras on
the Mac. (For most workflows, run the camera-bearing loop on the Linux box.)
