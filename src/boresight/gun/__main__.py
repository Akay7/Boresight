"""`boresight-gun`: aim with the Pi's camera, report as a USB mouse."""

from __future__ import annotations

import argparse
import logging
import signal
import sys
import threading
from collections.abc import Sequence
from pathlib import Path

from boresight.gun.app import Gun
from boresight.gun.config import DEFAULT_CONFIG_PATH, ConfigError, load
from boresight.gun.hid import (
    REPORT_DESCRIPTOR,
    DeviceSink,
    HidGadgetBackend,
    parse_report,
)
from boresight.gun.led import State, StatusIndicator
from boresight.gun.pins import PinError, validate_pins


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m boresight.gun",
        description="A Raspberry Pi light gun: camera in, USB absolute mouse out.",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help=f"configuration file (default: {DEFAULT_CONFIG_PATH} if it exists)",
    )
    parser.add_argument(
        "--emulate",
        type=Path,
        metavar="FRAMES_DIR",
        help="no Pi: replay a recorded frame sequence and print the mouse "
        "reports instead of sending them",
    )
    parser.add_argument(
        "--print-descriptor",
        action="store_true",
        help="write the USB HID report descriptor to stdout, as raw bytes, "
        "for the gadget setup script, and exit",
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    if args.print_descriptor:
        sys.stdout.buffer.write(REPORT_DESCRIPTOR)
        return 0

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    log = logging.getLogger("boresight.gun")

    path = args.config
    if path is None and DEFAULT_CONFIG_PATH.exists():
        path = DEFAULT_CONFIG_PATH
    # Nothing is presented to the host until the config and pins are known
    # good: a half-configured mouse is worse than none.
    try:
        loaded = load(path)
        validate_pins(loaded.config.pins.trigger, loaded.config.pins.led)
    except (ConfigError, PinError) as error:
        log.error("%s", error)
        return 2

    if args.emulate is not None:
        return _emulate(loaded, args.emulate)

    from boresight.gun.hardware import GpioLed, GpioTrigger, PiCamera

    led = (
        GpioLed(loaded.config.pins.led) if loaded.config.pins.led is not None else None
    )
    indicator = StatusIndicator(led, log=log.info)
    indicator.start()
    try:
        gun = Gun(
            loaded,
            PiCamera(loaded.config.camera),
            HidGadgetBackend(DeviceSink(loaded.config.hid_path)),
            GpioTrigger(loaded.config.pins.trigger),
            indicator,
        )
    except Exception:
        log.exception("could not start")
        indicator.set_state(State.ERROR)
        raise SystemExit(1) from None
    stop = threading.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: stop.set())
    try:
        return gun.run(stop)
    finally:
        indicator.stop()


def _emulate(loaded, frames_dir: Path) -> int:
    from boresight.gun.fakes import FixtureCamera, RecordingSink, ScriptedTrigger

    sink = RecordingSink()
    gun = Gun(
        loaded,
        FixtureCamera(frames_dir),
        HidGadgetBackend(sink),
        ScriptedTrigger(),
        StatusIndicator(None, log=logging.getLogger("boresight.gun").info),
    )
    code = gun.run(threading.Event())
    for report in sink.reports:
        x, y, pressed = parse_report(report)
        print(f"x={x:.4f} y={y:.4f} button={'down' if pressed else 'up'}")
    return code


if __name__ == "__main__":
    sys.exit(main())
