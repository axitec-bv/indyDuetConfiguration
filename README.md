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