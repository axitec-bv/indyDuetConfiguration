#!/usr/bin/env python3
"""
CoreXY diagonal steps/mm tuner (Indy / Duet).

Iterative loop per motor:
  NE diagonal → tunes Y   ·   SE diagonal → tunes X
  draw → measure → adjust M92 → send M92 to printer → redraw → repeat

Usage:
  python3 tools/corexy_calibrate.py --gui
"""

from __future__ import annotations

import argparse
import math
import re
import sys
import threading
import time
from collections.abc import Callable
from pathlib import Path
import urllib.error
import urllib.parse
import urllib.request

DEFAULT_MOVE_XY = 100.0
DEFAULT_HOST = "192.168.10.127"  # bench; production printers use 192.168.100.100
DEFAULT_M92 = "M92 X32.41 Y32.61 Z1600 E420"  # sys/config.g
REPO_ROOT = Path(__file__).resolve().parent.parent
CALIBRATION_CUBE_LOCAL = REPO_ROOT / "gcodes" / "cube_callibration_PP_1h6m.gcode"
CALIBRATION_CUBE_SD = "0:/gcodes/cube_callibration_PP_1h6m.gcode"
M92_LINE = re.compile(
    r"^M92\b.*[Xx](?P<x>[\d.]+).*[Yy](?P<y>[\d.]+)",
    re.IGNORECASE,
)


def fmt(n: float, digits: int = 3) -> str:
    return f"{n:.{digits}f}"


def new_steps(old: float, expected: float, measured: float) -> float:
    if measured <= 0:
        raise ValueError("measured length must be > 0")
    return old * (expected / measured)


def balena_steps(steps_per_mm: float) -> int:
    return int(math.floor(steps_per_mm * 1000 + 0.5))


def extract_xy_from_m92(line: str) -> tuple[float, float]:
    line = line.strip()
    m = M92_LINE.search(line)
    if not m:
        x_m = re.search(r"[Xx]([\d.]+)", line)
        y_m = re.search(r"[Yy]([\d.]+)", line)
        if not x_m or not y_m:
            raise ValueError("Could not find X and Y in M92 line.")
        return float(x_m.group(1)), float(y_m.group(1))
    return float(m.group("x")), float(m.group("y"))


def fetch_m92_from_duet(host: str) -> str:
    base = f"http://{host.rstrip('/')}"
    urllib.request.urlopen(f"{base}/rr_connect?password=", timeout=8)
    with urllib.request.urlopen(f"{base}/rr_download?name=/sys/config.g", timeout=8) as resp:
        text = resp.read().decode("utf-8", errors="replace")
    for line in text.splitlines():
        if line.strip().upper().startswith("M92 "):
            return line.strip()
    raise ValueError("No M92 line in printer config.g")


def send_gcode(host: str, gcode: str, *, wait_seconds: float = 30.0) -> str:
    base = f"http://{host.rstrip('/')}"
    urllib.request.urlopen(f"{base}/rr_connect?password=", timeout=8)
    query = urllib.parse.urlencode({"gcode": gcode})
    urllib.request.urlopen(f"{base}/rr_gcode?{query}", timeout=wait_seconds)
    deadline = time.time() + 5.0
    lines: list[str] = []
    while time.time() < deadline:
        time.sleep(0.25)
        try:
            with urllib.request.urlopen(f"{base}/rr_reply", timeout=8) as resp:
                chunk = resp.read().decode("utf-8", errors="replace").strip()
        except urllib.error.URLError:
            break
        if chunk:
            lines.append(chunk)
        elif lines:
            break
    return "\n".join(lines)


def diagonal_move_gcode(move_xy: float, ne: bool, forward: bool) -> str:
    d = float(move_xy)
    if d <= 0:
        raise ValueError("XY move must be > 0")
    if ne:
        x = d if forward else -d
        y = d if forward else -d
    else:
        x = d if forward else -d
        y = -d if forward else d
    return relative_move_gcode(x=x, y=y)


def relative_move_gcode(*, x: float = 0, y: float = 0, z: float = 0, feed: int = 3000) -> str:
    parts: list[str] = []
    if x:
        parts.append(f"X{x}")
    if y:
        parts.append(f"Y{y}")
    if z:
        parts.append(f"Z{z}")
    if not parts:
        raise ValueError("Need X, Y, and/or Z move")
    return f"G91\nG1 {' '.join(parts)} F{feed}\nM400\nG90"


def format_m92_line(x: float, y: float, template: str = "") -> str:
    line = f"M92 X{fmt(x)} Y{fmt(y)}"
    if template:
        z_m = re.search(r"[Zz]([\d.]+)", template)
        e_m = re.search(r"[Ee]([\d.]+)", template)
        if z_m:
            line += f" Z{z_m.group(1)}"
        if e_m:
            line += f" E{e_m.group(1)}"
    return line


def push_m92_to_duet(host: str, x: float, y: float, template: str = "") -> str:
    gcode = format_m92_line(x, y, template)
    send_gcode(host, gcode)
    return gcode


def upload_file_to_duet(host: str, local_path: Path, sd_name: str) -> None:
    if not local_path.is_file():
        raise FileNotFoundError(f"Local file not found: {local_path}")
    base = f"http://{host.rstrip('/')}"
    urllib.request.urlopen(f"{base}/rr_connect?password=", timeout=8)
    with local_path.open("rb") as handle:
        data = handle.read()
    req = urllib.request.Request(
        f"{base}/rr_upload?name={urllib.parse.quote(sd_name)}",
        data=data,
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=180) as resp:
        resp.read()


def start_sd_print(host: str, sd_path: str) -> None:
    send_gcode(host, f'M32 "{sd_path}"', wait_seconds=15.0)


def ask_float(prompt: str, default: float | None = None) -> float:
    while True:
        suffix = f" [{fmt(default)}]" if default is not None else ""
        raw = input(f"{prompt}{suffix}: ").strip()
        if not raw and default is not None:
            return default
        try:
            return float(raw.replace(",", "."))
        except ValueError:
            print("  Enter a number.")


def ask_yes(prompt: str, *, default: bool = False) -> bool:
    tag = "[Y/n]" if default else "[y/N]"
    raw = input(f"{prompt} {tag} ").strip().lower()
    if not raw:
        return default
    return raw in {"y", "yes", "j", "ja"}


def print_header(title: str) -> None:
    print(f"\n{'─' * 50}\n{title}\n{'─' * 50}")


def print_result(x_steps: float, y_steps: float, *, note: str = "") -> None:
    print("\n=== Result ===")
    print(f"  M92 X{fmt(x_steps)} Y{fmt(y_steps)}")
    print(f"  Balena STEPSX={balena_steps(x_steps)}  STEPSY={balena_steps(y_steps)}")
    print("  Update sys/config.g (M92 line) and Balena env for a permanent sync.")
    print("  M92 on the Duet is live until reboot unless saved in config.g.")
    if note:
        print(f"  {note}")


def tune_axis_iterative_cli(
    axis: str,
    direction: str,
    gcode_hint: str,
    x_steps: float,
    y_steps: float,
    expected: float,
    *,
    host: str | None = None,
    m92_template: str = "",
) -> tuple[float, float]:
    motor = "Y belt" if axis == "Y" else "X belt"
    print_header(f"Tune {axis} — {direction} ({motor} motor only)")
    print(f"  Ideal line: {fmt(expected)} mm")
    print(f"  G91 / {gcode_hint} / M400 / G90")
    if host:
        print(f"  M92 sent to {host} after each round.\n")
    prev_err: float | None = None
    round_n = 0
    undo = "NE −" if axis == "Y" else "SE −"
    redraw = "NE +" if axis == "Y" else "SE +"
    while True:
        round_n += 1
        print(f"\n--- {axis} round {round_n} ---")
        if round_n > 1:
            print(f"  Redraw: {undo} undo, then {redraw} again with updated steps.")
        measured = ask_float(f"Measured {direction} line (mm)")
        if axis == "Y":
            y_steps = new_steps(y_steps, expected, measured)
        else:
            x_steps = new_steps(x_steps, expected, measured)
        err = measured - expected
        m92 = format_m92_line(x_steps, y_steps, m92_template)
        print(f"  Error {err:+.2f} mm  →  {m92}")
        if prev_err is not None:
            delta = abs(prev_err) - abs(err)
            print(f"  |error| change: {delta:+.2f} mm ({'better' if delta > 0 else 'same/worse'})")
        if host:
            try:
                push_m92_to_duet(host, x_steps, y_steps, m92_template)
                print("  M92 applied on printer.")
            except urllib.error.URLError as exc:
                print(f"  Warning: could not send M92: {exc}")
        prev_err = err
        if not ask_yes("Another round?", default=abs(err) > 0.05):
            return x_steps, y_steps


def run_cli(
    *,
    m92_line: str,
    move_xy: float,
    host: str | None,
    skip_y: bool = False,
) -> tuple[float, float]:
    print("CoreXY calibration — iterative NE (Y) then SE (X)\n")

    if host:
        try:
            m92_line = fetch_m92_from_duet(host)
            print(f"Fetched from {host}:\n  {m92_line}\n")
        except (urllib.error.URLError, ValueError) as exc:
            print(f"Could not fetch config from {host}: {exc}\n")

    if not m92_line:
        m92_line = input("Paste current M92 line (X/Y extracted, Z/E ignored):\n> ").strip()
        if not m92_line:
            m92_line = DEFAULT_M92
            print(f"  Using default: {m92_line}")

    x_steps, y_steps = extract_xy_from_m92(m92_line)
    print(f"Baseline: X {fmt(x_steps)}  Y {fmt(y_steps)} steps/mm")

    if move_xy <= 0:
        raise ValueError("move distance must be > 0")
    expected = math.sqrt(2) * move_xy
    print(f"XY move {fmt(move_xy, 0)} mm → ideal diagonal {fmt(expected)} mm\n")

    if skip_y:
        print("Skipping Y (NE) tuning — keeping baseline Y steps/mm.\n")
    else:
        x_steps, y_steps = tune_axis_iterative_cli(
            "Y",
            "NE diagonal",
            f"G1 X{int(move_xy)} Y{int(move_xy)} F3000",
            x_steps,
            y_steps,
            expected,
            host=host,
            m92_template=m92_line,
        )
    x_steps, y_steps = tune_axis_iterative_cli(
        "X",
        "SE diagonal",
        f"G1 X{int(move_xy)} Y-{int(move_xy)} F3000",
        x_steps,
        y_steps,
        expected,
        host=host,
        m92_template=m92_line,
    )

    print_result(x_steps, y_steps)
    return x_steps, y_steps


def run_gui(default_m92: str, move_xy: float, default_host: str) -> None:
    try:
        import tkinter as tk
        from tkinter import ttk
    except ImportError as exc:
        raise SystemExit("tkinter not available; use CLI mode.") from exc

    root = tk.Tk()
    root.title("CoreXY calibration wizard")
    root.resizable(False, False)

    state: dict[str, float] = {
        "x": extract_xy_from_m92(default_m92)[0],
        "y": extract_xy_from_m92(default_m92)[1],
    }
    y_iterations: list[dict[str, float | int | None]] = []
    x_iterations: list[dict[str, float | int | None]] = []
    y_skipped = False
    move_btns: list[ttk.Button] = []
    step_index = tk.IntVar(value=0)

    STEP_TITLES = (
        "Setup — printer & baseline",
        "Tune Y — NE diagonal (iterate)",
        "Tune X — SE diagonal (iterate)",
        "Done — save values",
    )

    host_var = tk.StringVar(value=default_host)
    m92_var = tk.StringVar(value=default_m92)
    move_var = tk.StringVar(value=str(int(move_xy)))
    ne_var = tk.StringVar()
    se_var = tk.StringVar()
    y_out = tk.StringVar()
    x_out = tk.StringVar()
    skip_y_var = tk.BooleanVar(value=False)

    # --- shared logic ---
    def sync_m92_var() -> None:
        m92_var.set(format_m92_line(float(state["x"]), float(state["y"]), m92_var.get()))

    def parse_m92() -> None:
        try:
            state["x"], state["y"] = extract_xy_from_m92(m92_var.get())
            y_out.set(fmt(float(state["y"])))
            x_out.set(fmt(float(state["x"])))
            y_iterations.clear()
            x_iterations.clear()
            refresh_history(y_history_txt, y_iterations, "Y")
            refresh_history(x_history_txt, x_iterations, "X")
            update_baseline_labels()
        except ValueError as exc:
            set_status(str(exc))

    def move_mm() -> float:
        return float(move_var.get().replace(",", "."))

    def ideal_diagonal() -> float:
        return math.sqrt(2) * move_mm()

    def update_baseline_labels() -> None:
        exp = ideal_diagonal()
        baseline_lbl.config(
            text=f"X {fmt(float(state['x']))}  ·  Y {fmt(float(state['y']))} steps/mm  ·  "
            f"ideal diagonal {fmt(exp)} mm"
        )
        ideal_y_lbl.config(text=f"Ideal pencil line length: {fmt(exp)} mm")
        ideal_x_lbl.config(text=f"Ideal pencil line length: {fmt(exp)} mm")

    def set_status(msg: str) -> None:
        status_lbl.config(text=msg)

    def send_printer_move(label: str, gcode: str) -> None:
        host = host_var.get().strip()
        if not host:
            set_status("Enter printer IP first (step 1).")
            return

        def worker() -> None:
            set_status(f"Sending {label} …")
            for btn in move_btns:
                btn.state(["disabled"])
            try:
                reply = send_gcode(host, gcode)
                tail = reply.splitlines()[-1] if reply else "ok"
                set_status(f"{label} done — {tail}")
            except urllib.error.URLError as exc:
                set_status(f"{label} failed: {exc}")
            finally:
                for btn in move_btns:
                    btn.state(["!disabled"])

        threading.Thread(target=worker, daemon=True).start()

    def fetch_from_printer() -> None:
        host = host_var.get().strip()
        if not host:
            set_status("Enter printer IP.")
            return
        try:
            m92_var.set(fetch_m92_from_duet(host))
            parse_m92()
            set_status(f"M92 loaded from {host}")
        except (urllib.error.URLError, ValueError) as exc:
            set_status(f"Fetch failed: {exc}")

    def run_move(label: str, ne: bool, forward: bool) -> None:
        try:
            send_printer_move(label, diagonal_move_gcode(move_mm(), ne, forward))
        except ValueError as exc:
            set_status(str(exc))

    def run_nudge(axis: str, delta: float) -> None:
        sign = "+" if delta > 0 else "−"
        try:
            if axis == "X":
                send_printer_move(f"X {sign}{abs(delta)}", relative_move_gcode(x=delta))
            else:
                send_printer_move(f"Z {sign}{abs(delta)}", relative_move_gcode(z=delta, feed=250))
        except ValueError as exc:
            set_status(str(exc))

    def push_m92_to_printer(on_done: Callable[[], None] | None = None) -> None:
        host = host_var.get().strip()
        if not host:
            set_status("Enter printer IP first.")
            return

        def worker() -> None:
            set_status("Sending M92 …")
            try:
                push_m92_to_duet(host, float(state["x"]), float(state["y"]), m92_var.get())
                root.after(0, sync_m92_var)
                msg = f"M92 applied: X{fmt(float(state['x']))} Y{fmt(float(state['y']))}"
                root.after(0, lambda: set_status(msg))
                if on_done:
                    root.after(0, on_done)
            except urllib.error.URLError as exc:
                root.after(0, lambda: set_status(f"M92 failed: {exc}"))

        threading.Thread(target=worker, daemon=True).start()

    def run_printer_job(label: str, fn: Callable[[], None]) -> None:
        host = host_var.get().strip()
        if not host:
            set_status("Enter printer IP first.")
            return

        def worker() -> None:
            set_status(f"{label} …")
            try:
                fn()
                root.after(0, lambda: set_status(f"{label} done."))
            except (urllib.error.URLError, OSError, FileNotFoundError) as exc:
                root.after(0, lambda: set_status(f"{label} failed: {exc}"))

        threading.Thread(target=worker, daemon=True).start()

    def upload_calibration_cube() -> None:
        host = host_var.get().strip()

        def job() -> None:
            upload_file_to_duet(host, CALIBRATION_CUBE_LOCAL, CALIBRATION_CUBE_SD)

        run_printer_job("Uploading calibration cube to SD", job)

    def print_calibration_cube() -> None:
        host = host_var.get().strip()

        def job() -> None:
            start_sd_print(host, CALIBRATION_CUBE_SD)

        run_printer_job("Starting calibration cube print", job)

    def upload_and_print_calibration_cube() -> None:
        host = host_var.get().strip()

        def job() -> None:
            upload_file_to_duet(host, CALIBRATION_CUBE_LOCAL, CALIBRATION_CUBE_SD)
            start_sd_print(host, CALIBRATION_CUBE_SD)

        run_printer_job("Upload + print calibration cube", job)

    def refresh_history(
        widget: tk.Text,
        rows: list[dict[str, float | int | None]],
        axis: str,
    ) -> None:
        widget.config(state="normal")
        widget.delete("1.0", "end")
        if not rows:
            widget.insert("end", "(no rounds yet)\n")
        else:
            key = "y" if axis == "Y" else "x"
            for row in rows:
                imp = row.get("improvement")
                imp_s = f"  |err| Δ {float(imp):+.2f} mm" if imp is not None else ""
                widget.insert(
                    "end",
                    f"#{int(row['round'])}  {float(row['measured']):.2f} mm  "
                    f"err {float(row['error']):+.2f}  {axis}={float(row[key]):.3f}{imp_s}\n",
                )
        widget.config(state="disabled")

    def apply_round(axis: str) -> bool:
        measure_var = ne_var if axis == "Y" else se_var
        rows = y_iterations if axis == "Y" else x_iterations
        history = y_history_txt if axis == "Y" else x_history_txt
        undo, redraw = ("NE −", "NE +") if axis == "Y" else ("SE −", "SE +")
        try:
            measured = float(measure_var.get().replace(",", "."))
            ideal = ideal_diagonal()
            prev_err = float(rows[-1]["error"]) if rows else None
            err = measured - ideal
            if axis == "Y":
                state["y"] = new_steps(float(state["y"]), ideal, measured)
                y_out.set(fmt(float(state["y"])))
            else:
                state["x"] = new_steps(float(state["x"]), ideal, measured)
                x_out.set(fmt(float(state["x"])))
            improvement = (abs(prev_err) - abs(err)) if prev_err is not None else None
            key = "y" if axis == "Y" else "x"
            rows.append(
                {
                    "round": len(rows) + 1,
                    "measured": measured,
                    "error": err,
                    key: float(state[key]),
                    "improvement": improvement,
                }
            )
            refresh_history(history, rows, axis)
            update_baseline_labels()
            update_final_labels()
            measure_var.set("")

            def after_m92() -> None:
                if improvement is not None:
                    word = "better" if improvement > 0 else ("worse" if improvement < 0 else "same")
                    set_status(
                        f"{axis} round {len(rows)}: err {err:+.2f} mm ({word}, |err| Δ {improvement:+.2f}). "
                        f"Redraw: {undo} then {redraw}."
                    )
                else:
                    set_status(
                        f"{axis} round 1: err {err:+.2f} mm. Redraw with {undo} then {redraw}."
                    )

            push_m92_to_printer(on_done=after_m92)
            return True
        except ValueError as exc:
            label = "NE" if axis == "Y" else "SE"
            set_status(f"Enter measured {label} length: {exc}")
            return False

    def add_move_row(parent: ttk.Frame, buttons: list[tuple[str, callable]]) -> None:
        row = ttk.Frame(parent)
        row.pack(anchor="w", pady=4)
        for text, cmd in buttons:
            btn = ttk.Button(row, text=text, width=9, command=cmd)
            btn.pack(side="left", padx=(0, 6))
            move_btns.append(btn)

    # --- layout shell ---
    shell = ttk.Frame(root, padding=14)
    shell.grid(row=0, column=0, sticky="nsew")

    ttk.Label(shell, text="CoreXY calibration wizard", font=("", 15, "bold")).pack(anchor="w")
    step_title_lbl = ttk.Label(shell, text=STEP_TITLES[0], font=("", 11))
    step_title_lbl.pack(anchor="w", pady=(4, 10))

    content = ttk.Frame(shell)
    content.pack(fill="both", expand=True)

    step_frames: list[ttk.Frame] = []

    # Step 0 — setup
    s0 = ttk.Frame(content)
    step_frames.append(s0)
    ttk.Label(
        s0,
        text=(
            "1. Connect to the printer.\n"
            "2. Fetch or paste your current M92 line.\n"
            "3. On the printer: home X/Y (G28), park if needed.\n"
            "4. Each tuning round sends M92 to the printer automatically."
        ),
        justify="left",
    ).pack(anchor="w", pady=(0, 8))
    r0 = ttk.Frame(s0)
    r0.pack(anchor="w", pady=2)
    ttk.Label(r0, text="Printer IP", width=14).pack(side="left")
    ttk.Entry(r0, textvariable=host_var, width=20).pack(side="left", padx=4)
    ttk.Button(r0, text="Fetch M92", command=fetch_from_printer).pack(side="left")
    r1 = ttk.Frame(s0)
    r1.pack(anchor="w", pady=2)
    ttk.Label(r1, text="M92 line", width=14).pack(side="left")
    ttk.Entry(r1, textvariable=m92_var, width=38).pack(side="left", padx=4)
    ttk.Button(r1, text="Parse X/Y", command=parse_m92).pack(side="left")
    r2 = ttk.Frame(s0)
    r2.pack(anchor="w", pady=2)
    ttk.Label(r2, text="XY move (mm)", width=14).pack(side="left")
    ttk.Entry(r2, textvariable=move_var, width=8).pack(side="left", padx=4)
    move_var.trace_add("write", lambda *_: update_baseline_labels())
    baseline_lbl = ttk.Label(s0, text="")
    baseline_lbl.pack(anchor="w", pady=(8, 0))
    ttk.Checkbutton(
        s0,
        text="Skip Y tuning this session (e.g. linear scale faces the other way)",
        variable=skip_y_var,
    ).pack(anchor="w", pady=(8, 0))

    # Step 1 — tune Y (iterative NE)
    s1 = ttk.Frame(content)
    step_frames.append(s1)
    ideal_y_lbl = ttk.Label(s1, text="", font=("", 10, "bold"))
    ideal_y_lbl.pack(anchor="w", pady=(0, 6))
    ttk.Label(
        s1,
        text=(
            "NE diagonal — Y belt motor only. Repeat until error is small.\n\n"
            "Each round: NE + → Z +100 → measure → Apply round\n"
            "(M92 sent to printer) → NE − → NE + → measure again …\n\n"
            "Can't measure NE? Use  Skip Y →  (bottom right) to tune X only."
        ),
        justify="left",
    ).pack(anchor="w")
    add_move_row(
        s1,
        [
            ("NE +", lambda: run_move("NE +", True, True)),
            ("NE −", lambda: run_move("NE −", True, False)),
            ("Z +100", lambda: run_nudge("Z", 100)),
            ("Z −100", lambda: run_nudge("Z", -100)),
            ("X −10", lambda: run_nudge("X", -10)),
            ("X +10", lambda: run_nudge("X", 10)),
        ],
    )
    r_ne = ttk.Frame(s1)
    r_ne.pack(anchor="w", pady=(10, 0))
    ttk.Label(r_ne, text="Measured NE (mm)", width=16).pack(side="left")
    ttk.Entry(r_ne, textvariable=ne_var, width=10).pack(side="left", padx=4)
    ttk.Button(r_ne, text="Apply round", command=lambda: apply_round("Y")).pack(side="left")
    ttk.Label(r_ne, text="  →  Y =").pack(side="left", padx=(8, 2))
    ttk.Label(r_ne, textvariable=y_out, font=("", 10, "bold")).pack(side="left")
    ttk.Label(s1, text="Y round history:", font=("", 9, "bold")).pack(anchor="w", pady=(10, 2))
    y_history_txt = tk.Text(s1, height=4, width=62, font=("Menlo", 10), state="disabled")
    y_history_txt.pack(anchor="w")

    # Step 2 — tune X (iterative SE)
    s2 = ttk.Frame(content)
    step_frames.append(s2)
    ideal_x_lbl = ttk.Label(s2, text="", font=("", 10, "bold"))
    ideal_x_lbl.pack(anchor="w", pady=(0, 6))
    ttk.Label(
        s2,
        text=(
            "SE diagonal — X belt motor only. Same iterative loop as Y.\n\n"
            "Each round: SE + → measure → Apply round (M92 on printer) → SE − → SE + …"
        ),
        justify="left",
    ).pack(anchor="w")
    add_move_row(
        s2,
        [
            ("SE +", lambda: run_move("SE +", False, True)),
            ("SE −", lambda: run_move("SE −", False, False)),
            ("Z +100", lambda: run_nudge("Z", 100)),
            ("Z −100", lambda: run_nudge("Z", -100)),
            ("X −10", lambda: run_nudge("X", -10)),
            ("X +10", lambda: run_nudge("X", 10)),
        ],
    )
    r_se = ttk.Frame(s2)
    r_se.pack(anchor="w", pady=(10, 0))
    ttk.Label(r_se, text="Measured SE (mm)", width=16).pack(side="left")
    ttk.Entry(r_se, textvariable=se_var, width=10).pack(side="left", padx=4)
    ttk.Button(r_se, text="Apply round", command=lambda: apply_round("X")).pack(side="left")
    ttk.Label(r_se, text="  →  X =").pack(side="left", padx=(8, 2))
    ttk.Label(r_se, textvariable=x_out, font=("", 10, "bold")).pack(side="left")
    ttk.Label(s2, text="X round history:", font=("", 9, "bold")).pack(anchor="w", pady=(10, 2))
    x_history_txt = tk.Text(s2, height=4, width=62, font=("Menlo", 10), state="disabled")
    x_history_txt.pack(anchor="w")

    # Step 3 — done
    s3 = ttk.Frame(content)
    step_frames.append(s3)
    ttk.Label(s3, text="Calibration complete. Copy these values:", font=("", 11, "bold")).pack(
        anchor="w", pady=(0, 8)
    )
    final_m92_lbl = ttk.Label(s3, text="", font=("Menlo", 12))
    final_m92_lbl.pack(anchor="w", pady=2)
    final_balena_lbl = ttk.Label(s3, text="", font=("Menlo", 12))
    final_balena_lbl.pack(anchor="w", pady=2)
    skipped_y_lbl = ttk.Label(s3, text="", foreground="#666")
    skipped_y_lbl.pack(anchor="w", pady=(4, 0))
    ttk.Label(
        s3,
        text=(
            "\n• Update sys/config.g (M92 line)\n"
            "• Set Balena STEPSX / STEPSY\n"
            "• Sanity-check with straight moves (G1 X200, G1 Y200)\n"
            "• Print the calibration cube (~49 mm, ~1h) and measure X/Y/Z"
        ),
        justify="left",
    ).pack(anchor="w", pady=(12, 0))
    cube_row = ttk.Frame(s3)
    cube_row.pack(anchor="w", pady=(10, 0))
    ttk.Button(cube_row, text="Upload cube to SD", command=upload_calibration_cube).pack(
        side="left", padx=(0, 6)
    )
    ttk.Button(cube_row, text="Print cube", command=print_calibration_cube).pack(
        side="left", padx=(0, 6)
    )
    ttk.Button(cube_row, text="Upload + print", command=upload_and_print_calibration_cube).pack(
        side="left"
    )
    ttk.Label(
        s3,
        text=f"SD path: {CALIBRATION_CUBE_SD}  ·  repo: gcodes/cube_callibration_PP_1h6m.gcode",
        foreground="#666",
        font=("", 9),
    ).pack(anchor="w", pady=(6, 0))

    def update_final_labels() -> None:
        final_m92_lbl.config(text=format_m92_line(float(state["x"]), float(state["y"]), m92_var.get()))
        final_balena_lbl.config(
            text=f"STEPSX={balena_steps(float(state['x']))}   STEPSY={balena_steps(float(state['y']))}"
        )
        skipped_y_lbl.config(
            text="Y was not tuned this session — M92 Y unchanged from baseline." if y_skipped else ""
        )

    def skip_y_step() -> None:
        nonlocal y_skipped
        y_skipped = True
        set_status(f"Y tuning skipped — keeping Y={fmt(float(state['y']))} steps/mm.")
        show_step(2)

    def advance_from_setup() -> bool:
        try:
            parse_m92()
            move_mm()
        except ValueError as exc:
            set_status(str(exc))
            return False
        if skip_y_var.get():
            skip_y_step()
        else:
            show_step(1)
        return True

    # --- navigation ---
    nav = ttk.Frame(shell)
    nav.pack(fill="x", pady=(12, 0))
    status_lbl = ttk.Label(shell, text="Ready.", foreground="#444")
    status_lbl.pack(anchor="w", pady=(8, 0))

    def show_step(n: int) -> None:
        n = max(0, min(n, len(step_frames) - 1))
        step_index.set(n)
        for frame in step_frames:
            frame.pack_forget()
        step_frames[n].pack(fill="both", expand=True)
        step_title_lbl.config(text=f"Step {n + 1} of {len(step_frames)} — {STEP_TITLES[n]}")
        back_btn.state(["!disabled"] if n > 0 else ["disabled"])
        next_btn.config(text="Finish" if n == len(step_frames) - 1 else "Next →")
        if n == 1:
            skip_y_btn.pack(side="left", padx=(0, 6))
        else:
            skip_y_btn.pack_forget()
        if n == len(step_frames) - 1:
            update_final_labels()

    def go_back() -> None:
        show_step(step_index.get() - 1)

    def go_next() -> None:
        n = step_index.get()
        if n == 1:
            if ne_var.get().strip():
                if not apply_round("Y"):
                    return
            elif not y_iterations:
                set_status("Complete at least one Y round before Next.")
                return
        if n == 2:
            if se_var.get().strip():
                if not apply_round("X"):
                    return
            elif not x_iterations:
                set_status("Complete at least one X round before Next.")
                return
        if n == 0:
            if not advance_from_setup():
                return
            return
        if n < len(step_frames) - 1:
            show_step(n + 1)
        else:
            root.destroy()

    back_btn = ttk.Button(nav, text="← Back", command=go_back, width=10)
    back_btn.pack(side="left")
    nav_right = ttk.Frame(nav)
    nav_right.pack(side="right")
    skip_y_btn = ttk.Button(nav_right, text="Skip Y →", command=skip_y_step, width=10)
    next_btn = ttk.Button(nav_right, text="Next →", command=go_next, width=10)
    next_btn.pack(side="left")

    parse_m92()
    show_step(0)
    root.mainloop()


def main() -> None:
    parser = argparse.ArgumentParser(description="CoreXY diagonal steps/mm tuner (NE=Y, SE=X).")
    parser.add_argument("--gui", action="store_true", help="Tkinter wizard with move buttons")
    parser.add_argument(
        "--skip-y",
        action="store_true",
        help="Skip NE/Y tuning (CLI only; GUI has Skip Y button)",
    )
    parser.add_argument("--m92", default="", help=f"M92 line (default: prompt or {DEFAULT_M92})")
    parser.add_argument("--move", type=float, default=DEFAULT_MOVE_XY, help="XY move distance (mm)")
    parser.add_argument(
        "--host",
        default=DEFAULT_HOST,
        help=f"Duet IP to fetch M92 from (default: {DEFAULT_HOST})",
    )
    args = parser.parse_args()

    m92 = args.m92 or DEFAULT_M92 if args.gui else args.m92
    host = args.host or DEFAULT_HOST

    if args.gui:
        run_gui(m92, args.move, host)
    else:
        try:
            run_cli(
                m92_line=args.m92,
                move_xy=args.move,
                host=host if host else None,
                skip_y=args.skip_y,
            )
        except KeyboardInterrupt:
            print("\nStopped.", file=sys.stderr)
            sys.exit(130)


if __name__ == "__main__":
    main()
