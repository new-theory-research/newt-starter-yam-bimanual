# newt-starter-yam

A starter kit for running **MolmoAct-2** (`molmoact2-yam`) on **bimanual Ai2/I2RT YAM
arms** with three Intel RealSense cameras, via the New Theory `newt` SDK. Clone, configure,
run — the arms move.

> Naming: "YAM" is the arm (the WidowX-equivalent); this kit targets the **bimanual** config
> that MolmoAct-2's `BimanualYAM` checkpoint was trained on. (Single-arm YAM would be a
> separate kit.)

## What this drives

- **Model:** `molmoact2-yam` — bimanual, joint-space. Observation = 14D joint state (per-arm
  7-D: 6 joints in radians + 1 gripper in [0,1]) + 3 RGB cameras (378×378, CHW). Action =
  `(30, 14)` absolute joint-target chunks. **No IK** — targets go straight to the controller.
- **Arms:** two YAM arms over CAN (`i2rt`), 6-DoF + gripper each.
- **Cameras:** three Intel RealSense — `top` (overhead) + `left`/`right` (wrist).

## Prerequisites

- **Two YAM arms** powered and wired to CAN adapters on this host.
- **3 Intel RealSense cameras** on **USB-3** (a D405 on USB-2 enumerates but won't stream).
- **NT API key** — `export NT_API_KEY=...`.
- **GitHub access to `new-theory-research`** (for `newt`) — HTTPS via `gh`'s credential helper works.
- **Linux** (SocketCAN), **Python 3.11+**, and [uv](https://docs.astral.sh/uv/).

This kit targets the Linux box that drives the arms — typically reached over SSH/Tailscale.
To scaffold/drive from macOS (no SocketCAN), see [`docs/macos.md`](docs/macos.md) (the bundled
`yamcan` shim drives YAM over `gs_usb`/`slcan`).

## Setup

```bash
gh repo clone new-theory-research/newt-starter-yam
cd newt-starter-yam
uv sync
./scripts/setup            # writes ~/.config/nt/nt.toml; detects cameras + CAN
export NT_API_KEY=your_key_here
```

`./scripts/setup` creates `~/.config/nt/nt.toml` from the template and auto-detects what it can:
- **Cameras** — enumerates connected RealSense, **checks each is on USB-3**, and maps serials to
  `top`/`left`/`right` (interactive, or `--json` for agents).
- **CAN** — checks `can0`/`can1` are up at 1 Mbit; if down, prints the bring-up command.
- **uvcvideo** — warns + offers to load it if the kernel module isn't loaded (no module ⇒ no cameras).

Flags: `--force` (overwrite config), `--report-only` (dry-run), `--non-interactive`, `--json`.

## Bring-up ladder (do this in order the first time)

A bimanual arm with no guaranteed hardware e-stop deserves a staged bring-up. Each step is safe
on its own; don't skip to the last.

```bash
python scripts/comms_check.py can0 can1   # 1. read joint state from both arms — NO motion
python scripts/estop_selftest.py 60        # 2. verify the software stop zeros torque (trigger it)
python run.py --reset                      # 3. gently home the arms (yam_home)
python run.py --mock                        # 4. real inference, software arms — proves the cloud path
python run.py                               # 5. model in the loop on the real arms
```

## Run

```bash
python run.py                          # runs the configured task on the real arms
python run.py --task "Fold the towel and place it on the side."
python run.py --mock                   # software arms + synthetic cameras
python run.py --dry-run                # no SDK / no network — exercises the loop only
```

On the first call expect a warm-up: MolmoAct-2 cold-starts on Modal (~30–60 s). `run.py` warms
the model until inference is hot, then drives the arms (you'll see `[warm] HOT` first). Warm
inference runs ~1–2 s/cycle; the arm re-plans that often, so **tasks take minutes — let it run.**

## Stopping the arms

**From any SSH session** (this is the one that matters for a headless box):
```bash
touch /tmp/yam_estop      # zeros motor torque immediately
```
Also: **Ctrl+C** (or `pkill -TERM -f run.py`), and **Ctrl+H** when running in a real TTY.

This is a **software** stop (it zeros torque — arms go limp; motors stay powered). It is **not**
a hardware kill — keep a real power-cut within reach for true emergencies.

## Tasks

The model only does what it was trained on. The default task — **"Fold the towel and place it on
the side."** — is MolmoAct-2's own YAM eval task. Out-of-distribution prompts (e.g. "pick up the
can") produce near-zero motion. Match both the **task string and the scene** to the training
distribution. See [`docs/tasks.md`](docs/tasks.md).

## Config

Everything lives in `~/.config/nt/nt.toml` (see [`conf/nt.toml.example`](conf/nt.toml.example)):
arm CAN channels, camera serials, control rate / clamp / horizon, default task. Control params
can also be overridden per-run via flags (`--task`, `--seconds`, `--max-joint-step`, `--ipv4`).

## Tools

| Script | Purpose |
|---|---|
| `scripts/comms_check.py` | Read both arms' joint state (no motion). |
| `scripts/estop_selftest.py` | Verify the software stop zeros torque before you trust it. |
| `scripts/yam_home.py` | `--capture` a hand-set home, then gently return to it. |
| `scripts/find_cameras.py` | List RealSense serials + link speed. |
| `scripts/usb_reset_realsense.py` | Software "replug" if a camera wedges (`sudo`). |

## Known gotchas (learned the hard way — see your own DX log)

- **`NT_INFERENCE_URL`** silently overrides discovery for *all* models → misrouting. `run.py` warns if set.
- **IPv6 → Modal** blackholes on some hosts → set `force_ipv4 = true` (or `--ipv4`).
- **CAN** transient "motor loss communication" on init is normal (i2rt recovers); a hard fail needs an
  **arm power-cycle**. Don't power arms *off* to hand-move them — use the limp state instead.
- **Cameras** must be USB-3; a wedged one → `scripts/usb_reset_realsense.py` or a physical replug.
