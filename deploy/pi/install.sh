#!/bin/sh
# Sets a Raspberry Pi Zero 2 W up as a Boresight gun: the program, the USB
# gadget, and a service that starts both at power-up. Run as root from a
# checkout, on Raspberry Pi OS Lite (Trixie or later: the package needs
# Python 3.12). Safe to run again.
set -eu

[ "$(id -u)" -eq 0 ] || { echo "run as root: sudo $0" >&2; exit 1; }

HERE=$(cd "$(dirname "$0")" && pwd)
REPO=$(cd "$HERE/../.." && pwd)
PREFIX=/opt/boresight
CONFIG_TXT=/boot/firmware/config.txt
[ -f "$CONFIG_TXT" ] || CONFIG_TXT=/boot/config.txt

echo "== packages"
# The camera stack and OpenCV come from apt: the wheels for them on a Pi
# are slow to build or missing. The venv sees them.
apt-get update
apt-get install -y python3-venv python3-picamera2 python3-gpiozero \
    python3-lgpio python3-opencv python3-numpy

echo "== program"
python3 -m venv --system-site-packages "$PREFIX"
# --no-deps: OpenCV and NumPy are the system's.
"$PREFIX/bin/pip" install --no-deps --upgrade "$REPO"
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
install -m 644 "$HERE/boresight-gun.service" /etc/systemd/system/
systemctl daemon-reload
systemctl enable boresight-gadget.service boresight-gun.service

if [ "${NEED_REBOOT:-0}" -eq 1 ]; then
    echo "Done. USB device mode was just enabled: reboot once, then connect"
    echo "the Pi's USB data port (the one nearer the middle) to the host."
else
    systemctl restart boresight-gadget.service boresight-gun.service
    echo "Done. The gun is running."
fi
