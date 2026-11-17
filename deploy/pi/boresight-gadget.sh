#!/bin/sh
# Presents the Pi to its USB host as a mouse, through the kernel's configfs
# gadget interface. `start` is safe to run twice; `stop` undoes it.
#
# The report descriptor comes from the program itself, so the host is told
# exactly the report format the program sends.
set -eu

GADGET=/sys/kernel/config/usb_gadget/boresight
NAME=hid.usb0
BORESIGHT_GUN=${BORESIGHT_GUN:-/opt/boresight/bin/boresight-gun}

# Overridable in /etc/boresight-gadget.conf (shell syntax).
VENDOR_ID=0x1d6b
PRODUCT_ID=0x0104
MANUFACTURER="Boresight"
PRODUCT="Boresight light gun"
SERIAL=$(sed -n 's/^Serial[[:space:]]*:[[:space:]]*//p' /proc/cpuinfo 2>/dev/null || true)
SERIAL=${SERIAL:-0000000000000000}
# shellcheck disable=SC1091
[ -r /etc/boresight-gadget.conf ] && . /etc/boresight-gadget.conf

stop() {
    [ -d "$GADGET" ] || return 0
    echo "" >"$GADGET/UDC" 2>/dev/null || true
    rm -f "$GADGET/configs/c.1/$NAME"
    rmdir "$GADGET/configs/c.1/strings/0x409" 2>/dev/null || true
    rmdir "$GADGET/configs/c.1" 2>/dev/null || true
    rmdir "$GADGET/functions/$NAME" 2>/dev/null || true
    rmdir "$GADGET/strings/0x409" 2>/dev/null || true
    rmdir "$GADGET" 2>/dev/null || true
}

start() {
    modprobe libcomposite
    stop
    udc=
    for path in /sys/class/udc/*; do
        [ -e "$path" ] && { udc=${path##*/}; break; }
    done
    if [ -z "$udc" ]; then
        echo "no USB device controller: is dtoverlay=dwc2,dr_mode=peripheral set" \
            "in config.txt, and has the Pi been rebooted since?" >&2
        exit 1
    fi

    mkdir -p "$GADGET"
    echo "$VENDOR_ID" >"$GADGET/idVendor"
    echo "$PRODUCT_ID" >"$GADGET/idProduct"
    echo 0x0100 >"$GADGET/bcdDevice"
    echo 0x0200 >"$GADGET/bcdUSB"

    mkdir -p "$GADGET/strings/0x409"
    echo "$SERIAL" >"$GADGET/strings/0x409/serialnumber"
    echo "$MANUFACTURER" >"$GADGET/strings/0x409/manufacturer"
    echo "$PRODUCT" >"$GADGET/strings/0x409/product"

    mkdir -p "$GADGET/configs/c.1/strings/0x409"
    echo "Boresight mouse" >"$GADGET/configs/c.1/strings/0x409/configuration"
    # 100 mA: the Pi is powered from this same port, and the host is not
    # asked for more than it needs to enumerate it.
    echo 100 >"$GADGET/configs/c.1/MaxPower"

    mkdir -p "$GADGET/functions/$NAME"
    echo 0 >"$GADGET/functions/$NAME/protocol"
    echo 0 >"$GADGET/functions/$NAME/subclass"
    echo 5 >"$GADGET/functions/$NAME/report_length"
    "$BORESIGHT_GUN" --print-descriptor >"$GADGET/functions/$NAME/report_desc"

    ln -s "$GADGET/functions/$NAME" "$GADGET/configs/c.1/$NAME"
    echo "$udc" >"$GADGET/UDC"
}

case "${1:-}" in
start) start ;;
stop) stop ;;
*)
    echo "usage: $0 start|stop" >&2
    exit 2
    ;;
esac
