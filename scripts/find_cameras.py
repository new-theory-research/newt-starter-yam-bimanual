"""List connected RealSense cameras by name + serial. Non-energizing (no arm).

Reconcile the serials against dex-reflex/robot.yaml (top/left/right) so the
camera rig can address each by serial.
"""

import pyrealsense2 as rs

ctx = rs.context()
devs = ctx.query_devices()
print(f"realsense devices found: {len(devs)}")
for d in devs:
    name = d.get_info(rs.camera_info.name)
    serial = d.get_info(rs.camera_info.serial_number)
    print(f"  {name}  serial={serial}")
