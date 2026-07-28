#!/usr/bin/env python3
"""
Interactive guide for Indy M23CL closed-loop motor CAN addressing.

Talks to a Duet 3 in standalone mode (rr_gcode / rr_reply). Default host matches
a printer on the bench network; production printers use 192.168.100.100 after SD bring-up.

Workflow (factory address 123 on every motor):
  1. Update the MB6HC motherboard firmware first (see Duet release notes / internal Update Duet doc).
  2. Disconnect power to ALL M23CL motors (same factory CAN address).
  3. Connect one motor at a time, left-front first, following MOTOR_SEQUENCE.
  4. For each motor: M115 → M997 → M952 → M999 → verify M115 on the new address.

Usage:
  python3 tools/motor_bringup.py bringup
  python3 tools/motor_bringup.py replace --target 74
  python3 tools/motor_bringup.py verify
  python3 tools/motor_bringup.py scan
"""

from __future__ import annotations

import argparse
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

DEFAULT_HOST = "192.168.10.127"
FACTORY_ADDRESS = 123

# Factory bring-up order: links vooraan (72), then around the bed, then CoreXY pair.
# Layout on machine (see repo diagram):
#   72 front left   73 front right
#   74 back left    75 back right
#   70 / 71 CoreXY (config.g: Y=70, X=71)
MOTOR_SEQUENCE: list[tuple[int, str]] = [
    (72, "Z front left"),
    (73, "Z front right"),
    (74, "Z back left"),
    (75, "Z back right"),
    (70, "CoreXY (Y in config.g)"),
    (71, "CoreXY (X in config.g)"),
]

MOTOR_BY_ADDRESS: dict[int, str] = {addr: label for addr, label in MOTOR_SEQUENCE}

ALL_MOTOR_ADDRESSES = [addr for addr, _ in MOTOR_SEQUENCE]
SCAN_ADDRESSES = list(range(70, 76))


class DuetClient:
    def __init__(self, host: str, password: str = "", timeout: float = 8.0) -> None:
        self.base = f"http://{host.rstrip('/')}"
        self.timeout = timeout
        self._open_session(password)

    def _open_session(self, password: str) -> None:
        url = f"{self.base}/rr_connect?password={urllib.parse.quote(password)}"
        try:
            urllib.request.urlopen(url, timeout=self.timeout)
        except urllib.error.URLError as exc:
            raise SystemExit(f"Cannot reach Duet at {self.base}: {exc}") from exc

    def _get_text(self, path: str) -> str:
        url = f"{self.base}{path}"
        with urllib.request.urlopen(url, timeout=self.timeout) as resp:
            return resp.read().decode("utf-8", errors="replace")

    def send_gcode(self, gcode: str) -> None:
        query = urllib.parse.urlencode({"gcode": gcode})
        self._get_text(f"/rr_gcode?{query}")

    def drain_replies(self, idle_rounds: int = 2, poll_interval: float = 0.25) -> list[str]:
        lines: list[str] = []
        empty_streak = 0
        while empty_streak < idle_rounds:
            chunk = self._get_text("/rr_reply").strip()
            if chunk:
                lines.extend(part.strip() for part in chunk.splitlines() if part.strip())
                empty_streak = 0
            else:
                empty_streak += 1
            time.sleep(poll_interval)
        return lines

    def run_gcode(
        self,
        gcode: str,
        *,
        wait_seconds: float = 15.0,
        expect: re.Pattern[str] | None = None,
    ) -> str:
        self.send_gcode(gcode)
        deadline = time.time() + wait_seconds
        collected: list[str] = []
        while time.time() < deadline:
            for line in self.drain_replies(idle_rounds=1, poll_interval=0.15):
                collected.append(line)
                text = "\n".join(collected)
                if expect and expect.search(text):
                    return text
                if m115_ok(text):
                    return text
                if "CAN response timeout" in text:
                    return text
                if "Error" in text and gcode.upper().startswith("M952"):
                    return text
        return "\n".join(collected)

    def run_gcode_short(self, gcode: str, *, wait_seconds: float = 4.0) -> str:
        """Send G-code and collect replies briefly (M952/M999 — no long poll)."""
        self.send_gcode(gcode)
        deadline = time.time() + wait_seconds
        collected: list[str] = []
        while time.time() < deadline:
            for line in self.drain_replies(idle_rounds=1, poll_interval=0.15):
                collected.append(line)
            if collected and time.time() > deadline - 1.0:
                break
            time.sleep(0.2)
        return "\n".join(collected)


def prompt(msg: str, *, default_yes: bool = False) -> bool:
    suffix = "[Y/n]" if default_yes else "[y/N]"
    answer = input(f"{msg} {suffix} ").strip().lower()
    if not answer:
        return default_yes
    return answer in {"y", "yes", "j", "ja"}


def wait_for_user(step: str) -> None:
    input(f"\n>>> {step}\n    Druk Enter als je klaar bent...")


def print_header(title: str) -> None:
    print("\n" + "=" * 60)
    print(title)
    print("=" * 60)


def check_mainboard(duet: DuetClient) -> None:
    print_header("Moederbord (MB6HC)")
    print(
        "LET OP: werk eerst het moederbord bij vóór de M23CL motoren "
        "(interne doc: Update Duet / Duet3Firmware_MB6HC.bin op de SD)."
    )
    reply = duet.run_gcode("M115", wait_seconds=10.0)
    print(reply or "(geen reply)")
    if not m115_ok(reply):
        print("Kon moederbordversie niet lezen — controleer netwerk en printer.")
    else:
        match = re.search(r"FIRMWARE_VERSION:\s*(\S+)", reply, re.I)
        version = match.group(1) if match else "?"
        print(f"Moederbord OK — firmware {version}.")


def m115_ok(reply: str) -> bool:
    if not reply.strip() or "CAN response timeout" in reply:
        return False
    return re.search(r"firmware[_\s]version", reply, re.I) is not None


def m115_board_ok(reply: str, address: int) -> bool:
    """M115 for a specific CAN board — ignore stale firmware lines if this board timed out."""
    if not m115_ok(reply):
        return False
    if re.search(rf"timeout:\s*board\s+{address}\b", reply, re.I):
        return False
    return True


def firmware_ok(reply: str) -> bool:
    """True when M115 returned board firmware info (mainboard or M23CL)."""
    return m115_ok(reply)


def m115_board(duet: DuetClient, address: int, *, wait_seconds: float = 20.0) -> str:
    duet.drain_replies()
    return duet.run_gcode(f"M115 B{address}", wait_seconds=wait_seconds)


def m115_factory(duet: DuetClient) -> str:
    return m115_board(duet, FACTORY_ADDRESS)


def m115_address(duet: DuetClient, address: int) -> str:
    return m115_board(duet, address)


def update_firmware(duet: DuetClient, *, from_address: int = FACTORY_ADDRESS) -> None:
    print(f"  M997 B{from_address} — firmware update (kan enkele minuten duren)...")
    duet.send_gcode(f"M997 B{from_address}")
    deadline = time.time() + 300.0
    while time.time() < deadline:
        time.sleep(5.0)
        reply = m115_factory(duet) if from_address == FACTORY_ADDRESS else m115_address(duet, from_address)
        if m115_board_ok(reply, from_address):
            print(f"  Motor reageert weer: {reply.splitlines()[0]}")
            return
        print("  ... nog bezig, wachten ...")
    print("  Timeout: geen M115 antwoord na M997. Controleer handmatig in DWC.")


def readdress_motor(duet: DuetClient, new_address: int, *, from_address: int = FACTORY_ADDRESS) -> None:
    cmd = f"M952 B{from_address} A{new_address}"
    print(f"  {cmd}")
    print("  (adres wordt opgeslagen; het nieuwe CAN-adres is pas actief na reset.)")
    reply = duet.run_gcode_short(cmd, wait_seconds=3.0)
    if reply.strip():
        print(f"  {reply}")

    reset_cmd = f"M999 B{from_address}"
    print(f"  {reset_cmd} — reset motor (start op B{new_address})...")
    duet.run_gcode_short(reset_cmd, wait_seconds=2.0)
    duet.drain_replies()

    print(f"  Controleren M115 B{new_address} (motor kan ~10–30 s nodig hebben)...")
    deadline = time.time() + 60.0
    while time.time() < deadline:
        verify = m115_address(duet, new_address)
        if m115_board_ok(verify, new_address):
            print(f"  B{new_address} OK: {verify.splitlines()[0]}")
            old = m115_board(duet, from_address, wait_seconds=12.0)
            if m115_board_ok(old, from_address):
                print(
                    f"  WAARSCHUWING: B{from_address} reageert nog ook — "
                    "staat er nog een motor op het fabrieksadres?"
                )
            else:
                print(f"  B{from_address} reageert niet meer (verwacht na reset).")
            return
        if verify.strip():
            print(f"  ... {verify.splitlines()[0]}")
        time.sleep(4.0)

    verify = m115_address(duet, new_address)
    print(f"  {verify}")
    if not m115_board_ok(verify, new_address):
        print(
            f"  WAARSCHUWING: geen firmware-antwoord op B{new_address}. "
            f"Probeer handmatig: M999 B{new_address}, daarna M115 B{new_address}."
        )


def configure_one_motor(
    duet: DuetClient,
    target: int,
    label: str,
    *,
    from_address: int = FACTORY_ADDRESS,
    skip_firmware_update: bool = False,
) -> None:
    print_header(f"Motor CAN {target} — {label}")
    if from_address == FACTORY_ADDRESS:
        wait_for_user(
            "Zet stroom op ALLE andere M23CL motoren UIT. "
            "Sluit alleen DEZE motor aan op CAN + voeding."
        )
    else:
        wait_for_user("Alleen deze motor is aangesloten (vervang-modus).")

    print(f"Stap 1/4 — firmware check (M115 B{from_address})")
    if from_address == FACTORY_ADDRESS and m115_board_ok(m115_address(duet, target), target):
        print(
            f"  WAARSCHUWING: er reageert al iets op B{target} — "
            "deze motor is misschien al geconfigureerd."
        )
    reply = m115_factory(duet) if from_address == FACTORY_ADDRESS else m115_address(duet, from_address)
    print(reply or "(geen reply)")
    if not m115_board_ok(reply, from_address):
        print("Geen geldige M115 reply. Controleer bedrading en of precies één motor online is.")
        if not prompt("Toch doorgaan?", default_yes=False):
            return

    if not skip_firmware_update:
        if prompt(f"Stap 2/4 — firmware flashen met M997 B{from_address}?", default_yes=True):
            update_firmware(duet, from_address=from_address)
        else:
            print("  M997 overgeslagen.")
    else:
        print("Stap 2/4 — M997 overgeslagen (--skip-firmware-update).")

    print(f"Stap 3/4 — adres wijzigen naar {target}")
    readdress_motor(duet, target, from_address=from_address)

    print("Stap 4/4 — klaar voor deze motor.")
    wait_for_user("Zet deze motor uit of laat hem staan; ga door naar de volgende fysieke motor.")


def cmd_bringup(duet: DuetClient, args: argparse.Namespace) -> None:
    check_mainboard(duet)
    if not prompt("Moederbord is bijgewerkt — start motor bring-up?", default_yes=False):
        print("Gestopt. Werk eerst het moederbord bij.")
        return

    print_header("Motor bring-up — één voor één")
    print("Volgorde (start front left / links vooraan, dan rond het bed, dan CoreXY):")
    for idx, (addr, name) in enumerate(MOTOR_SEQUENCE, start=1):
        print(f"  {idx}. CAN {addr} — {name}")

    wait_for_user(
        "Zet stroom/ CAN op ALLE M23CL motoren UIT. "
        "We beginnen met motor 1; sluit alleen die ene aan."
    )

    for idx, (addr, name) in enumerate(MOTOR_SEQUENCE, start=1):
        print(f"\n--- Motor {idx}/{len(MOTOR_SEQUENCE)} ---")
        configure_one_motor(
            duet,
            addr,
            name,
            skip_firmware_update=args.skip_firmware_update,
        )

    print_header("Alle motoren aangesloten?")
    wait_for_user("Sluit ALLE zes M23CL motoren weer aan (plus toolboard indien van toepassing).")
    cmd_verify(duet, argparse.Namespace(addresses=ALL_MOTOR_ADDRESSES))


def cmd_replace(duet: DuetClient, args: argparse.Namespace) -> None:
    target = args.target
    if target not in SCAN_ADDRESSES:
        raise SystemExit(f"--target must be one of {SCAN_ADDRESSES}")

    name = next((n for a, n in MOTOR_SEQUENCE if a == target), f"CAN {target}")
    print_header(f"Motor vervangen → CAN {target} ({name})")

    if args.known_factory:
        configure_one_motor(
            duet,
            target,
            name,
            from_address=FACTORY_ADDRESS,
            skip_firmware_update=args.skip_firmware_update,
        )
        return

    wait_for_user("Maak alle motoren los behalve de nieuwe motor.")
    print("Zoeken welk CAN-adres reageert (M115 B70 … B75)...")
    found: int | None = None
    for addr in SCAN_ADDRESSES:
        reply = m115_address(duet, addr)
        if m115_board_ok(reply, addr):
            print(f"  Gevonden op B{addr}: {reply.splitlines()[0]}")
            found = addr
            break
        if reply:
            print(f"  B{addr}: {reply.splitlines()[0]}")

    if found is None:
        print("Geen motor gevonden op 70–75. Probeer fabrieksadres 123 (--known-factory).")
        reply = m115_factory(duet)
        if m115_board_ok(reply, FACTORY_ADDRESS):
            print(f"  Wel antwoord op B{FACTORY_ADDRESS}: {reply.splitlines()[0]}")
            if prompt("Motor op fabrieksadres 123 gebruiken?", default_yes=True):
                found = FACTORY_ADDRESS
        if found is None:
            return

    if found == target:
        print(f"Motor staat al op CAN {target}. Alleen verificatie:")
        print(m115_address(duet, target))
        return

    configure_one_motor(
        duet,
        target,
        name,
        from_address=found,
        skip_firmware_update=args.skip_firmware_update,
    )


def cmd_scan(duet: DuetClient, args: argparse.Namespace) -> None:
    addresses = args.addresses or (SCAN_ADDRESSES + [FACTORY_ADDRESS])
    print_header("CAN scan (M115)")
    for addr in addresses:
        reply = m115_address(duet, addr) if addr != FACTORY_ADDRESS else m115_factory(duet)
        status = "OK" if m115_board_ok(reply, addr) else "—"
        first = reply.splitlines()[0] if reply else "(geen reply)"
        print(f"  B{addr:3d}  [{status}]  {first}")


def cmd_verify(duet: DuetClient, args: argparse.Namespace) -> None:
    addresses = args.addresses or ALL_MOTOR_ADDRESSES
    print_header("Verificatie alle motoren")
    ok = True
    for addr in addresses:
        reply = m115_address(duet, addr)
        good = m115_board_ok(reply, addr)
        ok = ok and good
        tag = "OK" if good else "FAIL"
        first = reply.splitlines()[0] if reply else "(geen reply)"
        name = MOTOR_BY_ADDRESS.get(addr, "")
        print(f"  B{addr} [{tag}] {name} — {first}")
    if ok:
        print("\nAlle geconfigureerde motoren reageren.")
    else:
        print("\nNiet alle motoren OK — controleer CAN/voeding/adressen.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Begeleide M23CL motor CAN-adressering via Duet HTTP API.",
    )
    parser.add_argument(
        "--host",
        default=DEFAULT_HOST,
        help=f"Duet IP/hostname (default: {DEFAULT_HOST})",
    )
    parser.add_argument("--password", default="", help="Duet password if configured")

    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("mainboard", help="Check MB6HC firmware (M115) and show reminder")

    p_bringup = sub.add_parser("bringup", help="Full guided bring-up for all six motors")
    p_bringup.add_argument(
        "--skip-firmware-update",
        action="store_true",
        help="Skip M997 on each motor (only re-address)",
    )

    p_replace = sub.add_parser("replace", help="Replace a single motor")
    p_replace.add_argument(
        "--target",
        type=int,
        required=True,
        help="New CAN address (70–75)",
    )
    p_replace.add_argument(
        "--known-factory",
        action="store_true",
        help="New motor still on factory address 123",
    )
    p_replace.add_argument("--skip-firmware-update", action="store_true")

    p_scan = sub.add_parser("scan", help="M115 scan addresses")
    p_scan.add_argument(
        "addresses",
        type=int,
        nargs="*",
        help="Optional list of B addresses (default 70–75 and 123)",
    )

    p_verify = sub.add_parser("verify", help="M115 all configured motors")
    p_verify.add_argument(
        "addresses",
        type=int,
        nargs="*",
        help="Optional subset of addresses",
    )

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    duet = DuetClient(args.host, password=args.password)

    if args.command == "mainboard":
        check_mainboard(duet)
    elif args.command == "bringup":
        cmd_bringup(duet, args)
    elif args.command == "replace":
        cmd_replace(duet, args)
    elif args.command == "scan":
        cmd_scan(duet, args)
    elif args.command == "verify":
        cmd_verify(duet, args)
    else:
        parser.error(f"unknown command {args.command}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nAfgebroken.", file=sys.stderr)
        sys.exit(130)
