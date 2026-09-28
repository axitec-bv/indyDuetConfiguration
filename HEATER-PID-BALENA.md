# Per-printer heater PID (Balena)

Band (H1) and nozzle (H2) heater models are different on every Indy printer. They must **not** live in shared `config.g`, and they must **not** be stored as a raw RepRapFirmware string in Balena.

Balena device variables cannot safely contain spaces, dots, or colons. Values like `R1.21 K0.589:0.000 D8.87` have caused supervisor restart loops. Use the same digits-only rule as `STEPSX` / `STEPSY`.

## Device variables

| Variable | Heater | Required |
|----------|--------|----------|
| `H1_M307` | Band (barrel) | After that printer’s dual-zone tune |
| `H2_M307` | Nozzle | After that printer’s dual-zone tune |

Leave them unset until the printer is tuned. config-sync then keeps the shared defaults in `sys/config.g`.

## Encoding

Format: `R_K_Kf_D_E_S_B`

- Underscores only — no spaces, dots, or colons
- `R`, `K`, `Kf`, `D`, `E`, `S` use **3 implied decimals** (multiply by 1000)
- `B` is `0` (PID) or `1` (bang-bang), not scaled

Console line:

```
M307 H1 R1.21 K0.589:0.000 D8.87 E1.35 S1.00 B0
```

Balena value:

```
1210_589_0_8870_1350_1000_0
```

| Field | Meaning | Example raw | Encoded |
|-------|---------|-------------|---------|
| `R` | Heating rate (°C/s at full PWM) | 1.21 | `1210` |
| `K` | Cooling rate | 0.589 | `589` |
| `Kf` | Extra cooling rate with fan (the part after `:`) | 0.000 | `0` |
| `D` | Dead time (s) | 8.87 | `8870` |
| `E` | Extra time | 1.35 | `1350` |
| `S` | Max PWM | 1.00 | `1000` |
| `B` | 0 = PID, 1 = bang-bang | 0 | `0` |

Worked example for the current `config.g` defaults:

| Heater | Encoded | Decoded |
|--------|---------|---------|
| H1 band | `1210_589_0_8870_1350_1000_0` | `R1.210 K0.589:0.000 D8.870 E1.350 S1.000 B0` |
| H2 nozzle | `1210_239_0_9060_1350_1000_0` | `R1.210 K0.239:0.000 D9.060 E1.350 S1.000 B0` |

## After a tune

1. Run `macros/Heater tuning/` **1 → 2 → 3** from cold.
2. Copy each Console `M307` line.
3. Set `H1_M307` / `H2_M307` on **that device only**:
   - Dashboard: paste the encoded form
   - Or `set-device-vars.sh` in the Balena reverseProxy repo (it can encode a Console line)
4. Wait for config-sync (or restart the `config_sync` service). It rewrites `M307 H1` / `M307 H2` in `/sys/config.g`.
5. Send `M999` (or reboot) so the Duet loads the new model.

A `balena push IndyPrinters` is required once so the fleet runs a config-sync that understands these variables.

## What stays out of Balena

| Setting | Where |
|---------|--------|
| `M307 H0` (bed) | Shared `config.g` |
| `M143` / `M570` heater limits | Shared `config.g` |
| Print temperatures | Slicer / job |
| `global.waterTemp` | Live water-cooling macros |
| `STEPSX` / `STEPSY` | Already Balena (CoreXY steps) |
