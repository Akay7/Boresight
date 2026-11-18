#!/bin/sh
# Root setup for the gun's USB output on a Raspberry Pi Zero 2 W: USB
# device mode, the HID mouse gadget, and a service that starts the gun at
# power-up with no login. It installs no packages. Install the gun first,
# as on any system, from this checkout:
#
#     uv sync --extra gun
#
# then run this as root from the same checkout. Safe to run again.
set -eu

[ "$(id -u)" -eq 0 ] || { echo "run as root: sudo $0" >&2; exit 1; }

HERE=$(cd "$(dirname "$0")" && pwd)
REPO=$(cd "$HERE/../.." && pwd)
GUN="$REPO/.venv/bin/boresight-gun"
CONFIG_TXT=/boot/firmware/config.txt
[ -f "$CONFIG_TXT" ] || CONFIG_TXT=/boot/config.txt

if [ ! -x "$GUN" ]; then
    echo "$GUN is missing: install the gun first, in $REPO:" >&2
    echo "    uv sync --extra gun" >&2
    echo "(see deploy/pi/README.md for the system dependencies)" >&2
    exit 1
fi

echo "== configuration"
install -d /etc/boresight
[ -e /etc/boresight/markers.toml ] ||
    install -m 644 "$REPO/src/boresight/config/markers.toml" /etc/boresight/markers.toml
[ -e /etc/boresight-gun.toml ] ||
    install -m 644 "$HERE/boresight-gun.example.toml" /etc/boresight-gun.toml

echo "== USB device mode"
if ! grep -q '^dtoverlay=dwc2' "$CONFIG_TXT"; then
    printf '\n[all]\ndtoverlay=dwc2,dr_mode=peripheral\n' >>"$CONFIG_TXT"
    NEED_REBOOT=1
fi
install -m 755 "$HERE/boresight-gadget.sh" /usr/local/sbin/boresight-gadget

echo "== services"
install -m 644 "$HERE/boresight-gadget.service" /etc/systemd/system/
# The unit names the gun program in this checkout's venv.
sed "s|@GUN@|$GUN|" "$HERE/boresight-gun.service" >/etc/systemd/system/boresight-gun.service
chmod 644 /etc/systemd/system/boresight-gun.service
systemctl daemon-reload
systemctl enable boresight-gadget.service boresight-gun.service

if [ "${NEED_REBOOT:-0}" -eq 1 ]; then
    echo "Done. USB device mode was just enabled: reboot once, then connect"
    echo "the Pi's USB data port (the one nearer the middle) to the host."
else
    systemctl restart boresight-gadget.service boresight-gun.service
    echo "Done. The gun is running."
fi
