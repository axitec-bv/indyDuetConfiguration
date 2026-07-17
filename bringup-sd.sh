#!/usr/bin/env bash
# Overlay Indy Duet config onto a factory SD card for first bring-up.
#
# Usage:
#   ./bringup-sd.sh --name Indyprinter01
#   ./bringup-sd.sh --name Indyprinter02 --eject
#   ./bringup-sd.sh --name Indyprinter03 --old-machine --eject

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VOLUME=""
HOSTNAME=""
# Each printer sits behind its own router, so the LAN address is identical.
IP="192.168.100.100"
SUBNET="255.255.255.0"
OLD_MACHINE=0
EJECT=0
DRY_RUN=0

usage() {
  cat <<'EOF'
Bring up a factory Duet SD card with Indy configuration.

Required:
  --name NAME          Printer hostname (M550), e.g. Indyprinter01

Optional:
  --volume PATH        SD mount point (default: auto-detect /Volumes/* with Duet layout)
  --ip ADDRESS         Override static IPv4 (default: 192.168.100.100; same on every printer)
  --subnet MASK        Subnet mask for M553 (default: 255.255.255.0)
  --old-machine        Use sys/config_old_machine.g as config.g
  --eject              Eject the volume after a successful write
  --dry-run            Show what would be done without writing
  -h, --help           Show this help

Keeps factory firmware/ and www/. Replaces sys/ and macros/ from this repo,
then patches hostname (and IP/subnet) in config.g.
EOF
}

die() {
  echo "error: $*" >&2
  exit 1
}

is_duet_volume() {
  local root="$1"
  [[ -d "$root/firmware" && -d "$root/www" && -d "$root/sys" ]]
}

detect_volume() {
  local candidate
  for candidate in /Volumes/*; do
    [[ -d "$candidate" ]] || continue
    if is_duet_volume "$candidate"; then
      echo "$candidate"
      return 0
    fi
  done
  return 1
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --name)
      HOSTNAME="${2:-}"
      shift 2
      ;;
    --ip)
      IP="${2:-}"
      shift 2
      ;;
    --volume)
      VOLUME="${2:-}"
      shift 2
      ;;
    --subnet)
      SUBNET="${2:-}"
      shift 2
      ;;
    --old-machine)
      OLD_MACHINE=1
      shift
      ;;
    --eject)
      EJECT=1
      shift
      ;;
    --dry-run)
      DRY_RUN=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      die "unknown argument: $1"
      ;;
  esac
done

[[ -n "$HOSTNAME" ]] || die "missing --name"

if [[ ! "$HOSTNAME" =~ ^[A-Za-z0-9][A-Za-z0-9_-]*$ ]]; then
  die "hostname must be alphanumeric (plus _ or -): $HOSTNAME"
fi

if [[ ! "$IP" =~ ^([0-9]{1,3}\.){3}[0-9]{1,3}$ ]]; then
  die "invalid IPv4 address: $IP"
fi

if [[ ! "$SUBNET" =~ ^([0-9]{1,3}\.){3}[0-9]{1,3}$ ]]; then
  die "invalid subnet mask: $SUBNET"
fi

CONFIG_SRC="$REPO_ROOT/sys/config.g"
if [[ "$OLD_MACHINE" -eq 1 ]]; then
  CONFIG_SRC="$REPO_ROOT/sys/config_old_machine.g"
fi
[[ -f "$CONFIG_SRC" ]] || die "config source not found: $CONFIG_SRC"
[[ -d "$REPO_ROOT/sys" && -d "$REPO_ROOT/macros" ]] || die "repo missing sys/ or macros/"

if [[ -z "$VOLUME" ]]; then
  VOLUME="$(detect_volume)" || die "no Duet SD found under /Volumes; pass --volume"
fi

[[ -d "$VOLUME" ]] || die "volume not found: $VOLUME"
is_duet_volume "$VOLUME" || die "not a factory Duet SD (need firmware/, www/, sys/): $VOLUME"

CONFIG_DST="$VOLUME/sys/config.g"
PROFILE="current"
[[ "$OLD_MACHINE" -eq 1 ]] && PROFILE="old-machine"

echo "Bring-up plan"
echo "  volume:   $VOLUME"
echo "  hostname: $HOSTNAME"
echo "  ip:       $IP"
echo "  subnet:   $SUBNET"
echo "  profile:  $PROFILE"
echo "  source:   $CONFIG_SRC"
echo "  dwc:      English (sys/dwc-defaults.json)"
[[ "$DRY_RUN" -eq 1 ]] && echo "  mode:     dry-run"

if [[ "$DRY_RUN" -eq 1 ]]; then
  echo "dry-run: would sync sys/ and macros/, then patch config.g"
  exit 0
fi

# Preserve factory firmware/www; refresh machine config + macros.
rsync -a --delete \
  --exclude '.DS_Store' \
  --exclude 'config_old_machine.g' \
  "$REPO_ROOT/sys/" "$VOLUME/sys/"

# Install chosen machine profile as the live config.g
cp "$CONFIG_SRC" "$CONFIG_DST"

rsync -a --delete \
  --exclude '.DS_Store' \
  "$REPO_ROOT/macros/" "$VOLUME/macros/"

# Patch identity settings in the live config (portable for macOS/BSD sed).
tmp="$(mktemp)"
sed -E \
  -e "s/^M550 P\".*\"/M550 P\"${HOSTNAME}\"/" \
  -e "s/^M552 S1 P[0-9.]+/M552 S1 P${IP}/" \
  -e "s/^M553 P[0-9.]+/M553 P${SUBNET}/" \
  "$CONFIG_DST" >"$tmp"
mv "$tmp" "$CONFIG_DST"

# Ensure M553 exists for the current profile (old-machine template may omit it).
if ! grep -qE '^M553 P' "$CONFIG_DST"; then
  tmp="$(mktemp)"
  awk -v subnet="$SUBNET" '
    { print }
    /^M552 S1 P/ && !done {
      print "M553 P" subnet "  ; Subnet mask"
      done=1
    }
  ' "$CONFIG_DST" >"$tmp"
  mv "$tmp" "$CONFIG_DST"
fi

echo
echo "Patched config.g identity:"
grep -E '^M550 |^M552 |^M553 ' "$CONFIG_DST" || true

# Drop macOS clutter if the volume got any.
find "$VOLUME" -name '.DS_Store' -delete 2>/dev/null || true

sync

echo
echo "Done. Insert the card, power on, then open http://${IP}/"
echo "Note: first daemon.g hot-swap deploy still needs one reboot after first boot."

if [[ "$EJECT" -eq 1 ]]; then
  echo "Ejecting $VOLUME ..."
  diskutil eject "$VOLUME"
fi
