"""`boresight-gun`: aim with the gun's camera, and either report as a USB
mouse to another machine (`output = "usb"`) or move the cursor of the
display this computer drives, under the on-screen markers (`"local"`)."""

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
        description="A light gun: camera in, and a USB absolute mouse, or this "
        "display's cursor under on-screen markers, out.",
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
        "reports (or, for the local output, the cursor positions) instead "
        "of sending them",
    )
    parser.add_argument(
        "--screen",
        default="1920x1080",
        metavar="WxH",
        help="with --emulate and the local output: the display size the "
        "stand-in overlay reports (default: 1920x1080)",
    )
    parser.add_argument(
        "--autostart",
        nargs="?",
        const="write",
        choices=["write", "remove"],
        help="write a desktop autostart entry that starts the gun, with this "
        "--config, when you log in to your desktop and restarts it if it "
        "fails; `--autostart remove` deletes it",
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

    if args.autostart is not None:
        return _autostart(args.autostart, path, log)
    # Nothing is presented to the host until the config and pins are known
    # good: a half-configured mouse is worse than none.
    try:
        loaded = load(path)
        validate_pins(loaded.config.pins.trigger, loaded.config.pins.led)
    except (ConfigError, PinError) as error:
        log.error("%s", error)
        return 2

    if loaded.config.output == "local":
        if args.emulate is not None:
            return _emulate_local(loaded, args.emulate, args.screen)
        return _local(loaded, log)
    if args.emulate is not None:
        return _emulate(loaded, args.emulate)

    from boresight.gun.cameras import open_camera
    from boresight.gun.hardware import GpioLed, GpioTrigger

    led = (
        GpioLed(loaded.config.pins.led) if loaded.config.pins.led is not None else None
    )
    indicator = StatusIndicator(led, log=log.info)
    indicator.start()
    try:
        gun = Gun(
            loaded,
            open_camera(loaded.config.camera),
            HidGadgetBackend(DeviceSink(loaded.config.hid_path)),
            GpioTrigger(loaded.config.pins.trigger),
            indicator,
        )
    except ConfigError as error:
        log.error("%s", error)
        indicator.set_state(State.ERROR)
        return 2
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


def _autostart(action: str, config: Path | None, log) -> int:
    from boresight.gun.autostart import remove_entry, write_entry

    if action == "remove":
        removed = remove_entry()
        log.info("removed %s" if removed else "no autostart entry to remove", removed)
        return 0
    if config is not None and not Path(config).exists():
        log.error("config %s does not exist", config)
        return 2
    log.info("the gun starts when you log in: %s", write_entry(config))
    return 0


def _stop_on_signals() -> threading.Event:
    stop = threading.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: stop.set())
    return stop


def _local(loaded, log) -> int:
    from boresight.gun.cameras import open_camera
    from boresight.gun.hardware import GpioLed, GpioTrigger
    from boresight.gun.local import run_local
    from boresight.inject import CursorBackendUnavailable, UinputCursorBackend

    pins = loaded.config.pins
    indicator = StatusIndicator(
        GpioLed(pins.led) if pins.led is not None else None, log=log.info
    )
    indicator.start()
    try:
        try:
            cursor = UinputCursorBackend()
        except CursorBackendUnavailable as error:
            log.error("%s", error)
            indicator.set_state(State.ERROR)
            return 2
        try:
            camera = open_camera(loaded.config.camera)
        except ConfigError as error:
            log.error("%s", error)
            indicator.set_state(State.ERROR)
            cursor.close()
            return 2
        return run_local(
            loaded,
            camera,
            cursor,
            GpioTrigger(pins.trigger),
            indicator,
            _stop_on_signals(),
        )
    finally:
        indicator.stop()


def _emulate_local(loaded, frames_dir: Path, screen: str) -> int:
    from boresight.gun.fakes import FixtureCamera, ScriptedTrigger
    from boresight.gun.local import run_local
    from boresight.gun.standin_overlay import launcher_for, parse_screen
    from boresight.inject import FakeCursorBackend

    cursor = FakeCursorBackend()
    code = run_local(
        loaded,
        FixtureCamera(frames_dir),
        cursor,
        ScriptedTrigger(),
        StatusIndicator(None, log=logging.getLogger("boresight.gun").info),
        threading.Event(),
        launcher=launcher_for(parse_screen(screen)),
    )
    for x, y in cursor.calls:
        print(f"x={x:.4f} y={y:.4f}")
    return code


if __name__ == "__main__":
    sys.exit(main())
