#!/usr/bin/env bash
# Fetch ESP Web Tools (https://github.com/esphome/esp-web-tools,
# Apache-2.0) for the firmware flashing page into website/vendor/, at a
# pinned version checked against the npm registry's published SHA-512.
#
#   tools/vendor-esp-web-tools.sh            # the pinned version below
#   tools/vendor-esp-web-tools.sh 10.5.2 sha512-...   # another, deliberately
#
# Not committed: the site build (website/hooks.py) runs this when the
# folder is missing, so a checkout needs the network once and keeps the
# copy after that. Served from the site rather than a CDN, so the page runs
# exactly the version pinned here; re-running at the same version
# reproduces the same files byte for byte. To move to another version,
# change both lines below.
set -euo pipefail

VERSION="${1:-10.4.0}"
INTEGRITY="${2:-sha512-3pwkeFFm5Fj7UQo8SJNYK5RXrtNCpq6X9QoI6bMT4GBZWgrJqjn0YvM9ihG74BtMoSFYXfmDtkehuxe50PTMPQ==}"

repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
target="$repo/website/vendor/esp-web-tools"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

curl -fsSL -o "$work/package.tgz" \
    "https://registry.npmjs.org/esp-web-tools/-/esp-web-tools-$VERSION.tgz"
actual="sha512-$(openssl dgst -sha512 -binary "$work/package.tgz" | base64 -w0)"
if [ "$actual" != "$INTEGRITY" ]; then
    echo "esp-web-tools $VERSION does not match the pinned SHA-512:" >&2
    echo "  expected $INTEGRITY" >&2
    echo "  got      $actual" >&2
    exit 1
fi

tar -xzf "$work/package.tgz" -C "$work"
rm -rf "$target"
mkdir -p "$target"
cp -r "$work/package/dist/web/." "$target/"
cp "$work/package/LICENSE" "$target/LICENSE"
echo "$VERSION" > "$target/VERSION"
echo "vendored esp-web-tools $VERSION into ${target#"$repo"/}"
