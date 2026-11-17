"""MkDocs hook: assemble the site from the READMEs before every build.

The READMEs are written for GitHub, where a link is a path in the
repository. On the site most of those paths do not exist, so each README
is copied into `website/docs/` as a page with its links rewritten:

- a link to another of the site's READMEs goes to that page;
- an image is copied under `assets/` and shown from there;
- a link to any other file or directory in the repository goes to it on
  GitHub, since the site does not carry the source;
- anything else is left as written, and `mkdocs build --strict` fails on
  it, so a broken link is never published.

It also copies in the flashing page and ESP Web Tools -- fetched first
by `tools/vendor-esp-web-tools.sh`, at its pinned version and hash, if
this checkout does not have it yet -- and puts a
firmware bundle beside the page: from `BORESIGHT_FIRMWARE` (a build
directory, or a ready bundle such as a release's), else this checkout's
`firmware/boresight-cam/build` if it has been built, else none -- which
the page explains.

Files are written only when their content changed: `mkdocs serve`
rebuilds when `website/docs/` changes, and rewriting everything each time
would rebuild forever.
"""

from __future__ import annotations

import os
import posixpath
import re
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
WEBSITE = REPO / "website"
GITHUB = "https://github.com/Akay7/Boresight"

# Repository README -> page, in the order the navigation lists them.
PAGES = {
    "README.md": "index.md",
    "firmware/boresight-cam/README.md": "firmware.md",
    "hardware/case/README.md": "case.md",
    "deploy/pi/README.md": "pi-gun.md",
}
IMAGE_SUFFIXES = {".svg", ".png", ".jpg", ".jpeg", ".gif", ".webp"}
DEFAULT_FIRMWARE = REPO / "firmware" / "boresight-cam" / "build"
VENDOR = WEBSITE / "vendor"
VENDOR_SCRIPT = REPO / "tools" / "vendor-esp-web-tools.sh"

# [text](target) and ![alt](target), with an optional "title".
_LINK = re.compile(r"(!?\[[^\]]*\])\(\s*<?([^)\s>]+)>?(\s+\"[^\"]*\")?\s*\)")
_FENCE = re.compile(r"^\s*(```|~~~)")

sys.path.insert(0, str(WEBSITE))
import flasher  # noqa: E402 - a sibling script, not a package


def write_if_changed(path: Path, data: bytes) -> None:
    if path.is_file() and path.read_bytes() == data:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def rewrite_target(target: str, source: str, docs: Path) -> str:
    """What `target`, written in the README at repository path `source`,
    should be on the site."""
    if re.match(r"^[a-z][a-z0-9+.-]*:", target) or target.startswith(("#", "/")):
        return target  # a URL, an anchor on the same page, or site-absolute
    path, _, anchor = target.partition("#")
    suffix = f"#{anchor}" if anchor else ""
    resolved = posixpath.normpath(posixpath.join(posixpath.dirname(source), path))
    if resolved.startswith("../") or resolved == "..":
        return target  # outside the repository: left for --strict to judge
    if resolved in PAGES:
        return PAGES[resolved] + suffix
    on_disk = REPO / resolved
    if on_disk.is_file() and on_disk.suffix.lower() in IMAGE_SUFFIXES:
        write_if_changed(docs / "assets" / resolved, on_disk.read_bytes())
        return f"assets/{resolved}"
    if on_disk.is_file():
        return f"{GITHUB}/blob/main/{resolved}{suffix}"
    if on_disk.is_dir():
        return f"{GITHUB}/tree/main/{resolved}{suffix}"
    return target


def rewrite_page(text: str, source: str, docs: Path) -> str:
    """The README's text with its links rewritten, leaving code alone."""
    lines = []
    in_fence = False
    for line in text.splitlines(keepends=True):
        if _FENCE.match(line):
            in_fence = not in_fence
        elif not in_fence and not line.startswith(("    ", "\t")):
            line = _LINK.sub(
                lambda m: (
                    f"{m.group(1)}({rewrite_target(m.group(2), source, docs)}"
                    f"{m.group(3) or ''})"
                ),
                line,
            )
        lines.append(line)
    return "".join(lines)


def copy_tree(source: Path, target: Path) -> None:
    for path in source.rglob("*"):
        if path.is_file():
            write_if_changed(target / path.relative_to(source), path.read_bytes())


def fetch_vendor() -> None:
    """Run the vendoring script; it checks the download's hash itself."""
    result = subprocess.run([str(VENDOR_SCRIPT)], capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(
            "could not fetch ESP Web Tools for the flashing page "
            f"({VENDOR_SCRIPT.relative_to(REPO)}):\n{result.stderr.strip()}"
        )
    print(result.stdout.strip(), file=sys.stderr)


def ensure_vendor(vendor: Path, fetch=fetch_vendor) -> None:
    """ESP Web Tools in `vendor`, fetched once if this checkout lacks it."""
    if not (vendor / "esp-web-tools" / "install-button.js").is_file():
        fetch()


def firmware_source() -> Path | None:
    configured = os.environ.get("BORESIGHT_FIRMWARE")
    if configured:
        return Path(configured)
    return DEFAULT_FIRMWARE if (DEFAULT_FIRMWARE / "flash_args").is_file() else None


def assemble(docs: Path, vendor: Path = VENDOR, fetch=fetch_vendor) -> None:
    for source, page in PAGES.items():
        text = (REPO / source).read_text(encoding="utf-8")
        write_if_changed(docs / page, rewrite_page(text, source, docs).encode())
    copy_tree(WEBSITE / "flash", docs / "flash")
    ensure_vendor(vendor, fetch)
    copy_tree(vendor, docs / "vendor")
    firmware = firmware_source()
    if firmware is not None:
        # Staged outside the docs, then copied in only where it differs.
        with tempfile.TemporaryDirectory() as staged:
            if flasher.write_bundle(firmware, Path(staged)) is not None:
                copy_tree(Path(staged), docs / "flash")
            else:
                print(f"hooks: no firmware bundle in {firmware}", file=sys.stderr)


def on_pre_build(config, **kwargs) -> None:
    assemble(Path(config["docs_dir"]))
