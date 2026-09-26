#!/usr/bin/env bash
# Run idf.py for one build profile inside the pinned ESP-IDF container, so
# nothing has to be installed on the host but a container runtime.
#
#   tools/idf.sh device build        # the image for a real ESP32-CAM
#   tools/idf.sh emulator build      # the QEMU image (fake camera, Ethernet)
#   tools/idf.sh device menuconfig
#
# Profiles build into separate directories from separate configuration:
# the emulator's sdkconfig lives inside build-emulator/, so building it can
# never touch the device's sdkconfig, which holds the Wi-Fi password and
# token.
#
# Runs as the invoking user, so build output stays deletable. Set
# CONTAINER=podman to use Podman, IDF_IMAGE to pin a different image.
set -euo pipefail

IMAGE="${IDF_IMAGE:-espressif/idf:v5.4}"
RUNTIME="${CONTAINER:-docker}"

profile="${1:-}"
if [ $# -gt 0 ]; then shift; fi

case "$profile" in
device)
    profile_args=(-B build)
    ;;
emulator)
    profile_args=(
        -B build-emulator
        -D SDKCONFIG=build-emulator/sdkconfig
        -D "SDKCONFIG_DEFAULTS=sdkconfig.defaults;sdkconfig.emulator"
    )
    ;;
*)
    echo "usage: tools/idf.sh <device|emulator> <idf.py arguments...>" >&2
    exit 2
    ;;
esac

firmware_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# The whole repository, not just the firmware: the emulator build embeds
# frames from tests/fixtures/.
repo_dir="$(cd "$firmware_dir/../.." && pwd)"

run_flags=(--rm -v "$repo_dir:/project" -w /project/firmware/boresight-cam -e HOME=/tmp)
if [ -t 0 ] && [ -t 1 ]; then
    run_flags+=(-it)
fi
if [ "$RUNTIME" = podman ]; then
    # Rootless Podman maps the invoking user in with this instead.
    run_flags+=(--userns=keep-id)
elif "$RUNTIME" info --format '{{.SecurityOptions}}' 2>/dev/null | grep -q rootless; then
    # Rootless Docker: the container's root already is the invoking user
    # on the host, and any other UID maps to one that cannot write here.
    :
else
    run_flags+=(--user "$(id -u):$(id -g)")
fi

exec "$RUNTIME" run "${run_flags[@]}" "$IMAGE" idf.py "${profile_args[@]}" "$@"
