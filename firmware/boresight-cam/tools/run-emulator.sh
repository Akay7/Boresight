#!/usr/bin/env bash
# Boot the emulator build in QEMU, inside the same pinned ESP-IDF container.
#
#   tools/idf.sh emulator build
#   tools/run-emulator.sh
#
# The device's serial console is this process's stdin and stdout: type
# `press`, `release` or `click` to operate the trigger. Quit with Ctrl-A X.
#
# The emulated device reaches this machine's loopback as 10.0.2.2, port
# 7391, token `emulator-token` (see sdkconfig.emulator). The container
# shares the host's network namespace so that loopback is the host's; a
# server bound to 127.0.0.1 is reached with nothing exposed beyond it.
set -euo pipefail

IMAGE="${IDF_IMAGE:-espressif/idf:v5.4}"
RUNTIME="${CONTAINER:-docker}"
# The emulator image by default. BORESIGHT_EMULATOR_BUILD=build boots the
# device image instead: it has no emulated Ethernet or fake camera, so it
# only gets as far as its boot checks -- which is what that is for.
BUILD_DIR="${BORESIGHT_EMULATOR_BUILD:-build-emulator}"

firmware_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
repo_dir="$(cd "$firmware_dir/../.." && pwd)"

if [ ! -f "$firmware_dir/$BUILD_DIR/flash_args" ]; then
    echo "No image in $BUILD_DIR. Build one first: tools/idf.sh emulator build" >&2
    exit 1
fi

run_flags=(
    --rm -i --network host
    -v "$repo_dir:/project"
    -w "/project/firmware/boresight-cam/$BUILD_DIR"
    -e HOME=/tmp
)
if [ -t 0 ] && [ -t 1 ]; then
    run_flags+=(-t)
fi
# A known name lets a test harness remove the container whatever happens.
if [ -n "${BORESIGHT_EMULATOR_NAME:-}" ]; then
    run_flags+=(--name "$BORESIGHT_EMULATOR_NAME")
fi
if [ "$RUNTIME" = podman ]; then
    run_flags+=(--userns=keep-id)
elif ! "$RUNTIME" info --format '{{.SecurityOptions}}' 2>/dev/null | grep -q rootless; then
    run_flags+=(--user "$(id -u):$(id -g)")
fi

# -m 4M gives QEMU emulated PSRAM, which the device image needs to boot at
# all (the emulator image does not use it).
# The watchdog property is what `idf.py qemu` sets too: the emulated timer
# group watchdog otherwise fires during boot on a loaded host.
exec "$RUNTIME" run "${run_flags[@]}" "$IMAGE" bash -c '
    python -m esptool --chip esp32 merge_bin --fill-flash-size 4MB \
        -o flash_image.bin @flash_args >/dev/null &&
    exec qemu-system-xtensa -nographic -machine esp32 \
        -m 4M \
        -drive file=flash_image.bin,if=mtd,format=raw \
        -nic user,model=open_eth \
        -global driver=timer.esp32.timg,property=wdt_disable,value=true
'
