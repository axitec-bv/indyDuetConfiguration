# indyDuetConfiguration

Duet 3 configuration, macros, and SD bring-up for Indy printers.

## M23CL motor CAN addressing (interactive)

Motors ship on factory CAN address **123**. Address them one at a time (power off the rest), then verify.

```bash
chmod +x tools/motor_bringup.py
python3 tools/motor_bringup.py --host 192.168.10.127 mainboard
python3 tools/motor_bringup.py --host 192.168.10.127 bringup
python3 tools/motor_bringup.py --host 192.168.10.127 verify
python3 tools/motor_bringup.py --host 192.168.10.127 replace --target 74
```

Uses the Duet standalone HTTP API (`rr_gcode` / `rr_reply`). After SD bring-up the printer is usually at `http://192.168.100.100/`.

Physical layout (CAN address → corner):

| Address | Position |
|---------|----------|
| 72 | Z front left |
| 73 | Z front right |
| 74 | Z back left |
| 75 | Z back right |
| 70 | CoreXY (Y in `config.g`) |
| 71 | CoreXY (X in `config.g`) |

`bringup` order: **72 → 73 → 74 → 75 → 70 → 71** (front left first).

## CoreXY steps calibration

**Workflow:** tune M92 with NE/SE diagonal moves (this tool or `macros/Calibration/`), then print the validation cube.

| Step | What |
|------|------|
| 1 | NE/SE pencil lines → iterative M92 X/Y (GUI sends M92 each round) |
| 2 | Save M92 in `sys/config.g` + Balena STEPSX/STEPSY |
| 3 | Print `gcodes/cube_callibration_PP_1h6m.gcode` (~49 mm cube, ~1h) and measure |

```bash
python3 tools/corexy_calibrate.py --gui
python3 tools/corexy_calibrate.py --host 192.168.10.127
```

Upload cube to printer SD (once):

```bash
curl -s --data-binary @gcodes/cube_callibration_PP_1h6m.gcode \
  "http://192.168.10.127/rr_upload?name=0:/gcodes/cube_callibration_PP_1h6m.gcode"
```