"""Generates the checked-in synthetic "video" fixture used by
test_solve_video_e2e.py: a sequence of rendered, degraded frames under
tests/fixtures/synthetic_video/ plus manifest.json and the Blender scene
that produced them.

Run manually when the fixture needs to change -- e.g. a deliberate change
to the camera path, marker layout, or degradation model:

    uv run python -m tests.generate_synthetic_video_fixture

Requires Blender (`blender-5.2`, override with $BORESIGHT_BLENDER). The
test suite does NOT: it reads the checked-in frames, so `pytest` never
invokes Blender and Blender is not a project dependency.

The fixture is checked in rather than regenerated per run for the same
reason the photo fixture is: it makes the e2e test a real regression
test. If detect.py or solve.py changes and produces a different result
against these exact frames, that is a signal worth investigating rather
than noise from a re-rolled scene.

Blender's role is to supply what warping a 2D canvas cannot: a real
pinhole camera moving through a 3D scene, giving each frame a genuine
perspective projection and -- the reason it is worth the dependency --
a per-frame ground-truth aim point derived from the camera's own pose
(see blender_video_scene.py), independent of the homography math
solve.py uses to reconstruct it.

The scene follows README's markers.toml convention: a 16:9 panel with
screen-mm origin at the top-left of the ACTIVE display area, and the
markers printed on white cardstock stuck to the bezel outside it, hence
their negative coordinates.

Lighting is real: the panel is the only emitter, and the bezel,
cardstock and room wall are Principled BSDF surfaces lit by area lamps,
rendered in Cycles. So README's dominant failure mode -- a bright screen
beside dim paper in a dim room -- arrives as an optical consequence,
with real falloff across the layout, real spill from the screen onto the
cardstock, and real blown highlights, instead of brightness constants
and a gradient painted on in 2D afterwards. A roughness map separates
matte cardstock from the semi-gloss bezel, which is what README's
"Matte substrate only. Never glossy" warning is about.

What the scene still does NOT model, so nothing here should be read as
evidence about it: geometric depth (the bezel is painted on a flat
plane, so it never occludes a marker at an oblique angle), lens
distortion, rolling shutter, and panel content detailed enough to
generate false-positive quad candidates.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import cv2
import numpy as np

TESTS_DIR = Path(__file__).parent
FIXTURE_DIR = TESTS_DIR / "fixtures" / "synthetic_video"
MANIFEST_PATH = FIXTURE_DIR / "manifest.json"
BLEND_PATH = FIXTURE_DIR / "scene.blend"
SCENE_SCRIPT = TESTS_DIR / "blender_video_scene.py"

BLENDER_BINARY = os.environ.get("BORESIGHT_BLENDER", "blender-5.2")

RESOLUTION = (1280, 720)
FRAME_COUNT = 20
CAMERA_FOV_DEG = 45.0

# A 16:9 panel, matching README's markers.toml worked example.
SCREEN_SIZE_MM = (1220.0, 686.0)
BEZEL_MM = 160.0
TV_SIZE_MM = (
    SCREEN_SIZE_MM[0] + 2.0 * BEZEL_MM,
    SCREEN_SIZE_MM[1] + 2.0 * BEZEL_MM,
)
ROOM_SIZE_MM = (6000.0, 3600.0)
ROOM_DISTANCE_MM = 900.0

MARKER_SIZE_MM = 80.0
# White cardstock the marker is printed on. The margin is the quiet zone
# ArUco needs to find the quad: without it the marker's black border
# runs straight into the dark bezel and stops decoding. ArUco needs
# roughly one cell (~13mm at this size); 20mm is comfortably more.
CARDSTOCK_MM = 120.0

# Top-left of each 80mm marker, in screen mm, origin at the panel's
# top-left corner per markers.toml. All are negative or past the panel
# extent because they sit on the bezel, outside the active area.
# 4 corners plus 4 edge midpoints, README's minimum layout: the
# midpoints matter because a narrow-FOV camera close in loses the
# corners first.
_BEZEL_NEAR = -(BEZEL_MM + MARKER_SIZE_MM) / 2.0  # centred in the bezel band
_MARKER_LEFT = _BEZEL_NEAR
_MARKER_TOP = _BEZEL_NEAR
_MARKER_RIGHT = SCREEN_SIZE_MM[0] + (BEZEL_MM - MARKER_SIZE_MM) / 2.0
_MARKER_BOTTOM = SCREEN_SIZE_MM[1] + (BEZEL_MM - MARKER_SIZE_MM) / 2.0
_MID_X = (SCREEN_SIZE_MM[0] - MARKER_SIZE_MM) / 2.0
_MID_Y = (SCREEN_SIZE_MM[1] - MARKER_SIZE_MM) / 2.0

MARKER_LAYOUT_MM = {
    0: (_MARKER_LEFT, _MARKER_TOP),
    1: (_MARKER_RIGHT, _MARKER_TOP),
    2: (_MARKER_RIGHT, _MARKER_BOTTOM),
    3: (_MARKER_LEFT, _MARKER_BOTTOM),
    4: (_MID_X, _MARKER_TOP),
    5: (_MARKER_RIGHT, _MID_Y),
    6: (_MID_X, _MARKER_BOTTOM),
    7: (_MARKER_LEFT, _MID_Y),
}

# The panel is the only emitter; everything else is a lit surface. This
# is README's dominant failure mode -- a bright screen beside dim paper
# in a dim room -- produced optically, so the blown highlights, the
# falloff across the bezel and the screen's spill onto the cardstock all
# follow from the scene instead of being painted on afterwards.
SCREEN_EMISSION_STRENGTH = 5.0

# Matte cardstock against a semi-gloss bezel: README's "Matte substrate
# only. Never glossy" distinction, as an actual surface property.
ROUGHNESS = {"bezel": 0.35, "cardstock": 0.88}

# Dim, warm room lighting from one side plus a cooler fill, so
# illumination across the marker layout is genuinely uneven.
# Energies are ~1e7 because 1 unit == 1mm while Cycles reads distance as
# metres for falloff; see build_lights() in blender_video_scene.py.
LIGHTS = [
    {
        "name": "RoomLamp",
        "size": [1200.0, 800.0],
        "energy": 6.0e7,
        "color": [1.0, 0.92, 0.82],
        "location": [-2200.0, -2000.0, 1400.0],
        "rotation_deg": [62.0, 0.0, -38.0],
    },
    {
        "name": "Fill",
        "size": [900.0, 900.0],
        "energy": 1.2e7,
        "color": [0.82, 0.88, 1.0],
        "location": [2400.0, -1800.0, -600.0],
        "rotation_deg": [100.0, 0.0, 52.0],
    },
]

CYCLES_SAMPLES = 96
CYCLES_SEED = 0

# Sensor-side effects only. The exposure gradient that used to live here
# is gone: uneven illumination is now a property of the lighting rig, so
# painting a second one on in 2D would double-count it. Blur and noise
# stay, because those happen in the lens and sensor, after the light has
# already left the scene. Noise is seeded per frame so successive frames
# differ the way a real sensor's would, while the sequence as a whole
# stays reproducible.
DEGRADATION = {
    "base_seed": 0,
    "blur_kernel": 5,
    "blur_sigma": 1.0,
    "noise_sigma": 4.0,
}

# Frames are stored as JPEG, not PNG: it is what the phone client will
# actually stream (README's "Software stack"), it adds a real
# compression artifact to decode against, and it keeps a 20-frame
# checked-in fixture to a few MB instead of ~12MB of noisy PNG.
JPEG_QUALITY = 88

# A sweep across the panel, not a model of any real light-gun swing:
# enough motion, over enough frames, to make the per-frame homography
# genuinely vary and give the frame-to-frame coherence check something
# to bite on. Camera positions drift too, so the change is not purely
# rotational.
#   frame, aim x/y (screen mm),  camera x/y/z (world mm)
_KEYFRAME_TABLE = [
    (1, (300.0, 200.0), (-450.0, -3000.0, 260.0)),
    (7, (900.0, 240.0), (250.0, -2900.0, 180.0)),
    (13, (880.0, 500.0), (420.0, -3100.0, -200.0)),
    (17, (340.0, 470.0), (-300.0, -3000.0, -240.0)),
    (20, (610.0, 343.0), (0.0, -3200.0, 0.0)),
]

KEYFRAMES = [
    {
        "frame": frame,
        "aim_screen_mm": list(aim),
        "camera_position": list(position),
    }
    for frame, aim, position in _KEYFRAME_TABLE
]


def _screen_to_canvas(x_mm: float, y_mm: float) -> tuple[int, int]:
    """Screen mm -> TV-face canvas pixel (1px per mm, bezel included)."""
    return (int(round(x_mm + BEZEL_MM)), int(round(y_mm + BEZEL_MM)))


def _render_tv_face() -> np.ndarray:
    """The TV's front face: dark bezel plus the markers on white cardstock.

    The panel area is left dark; a separate, brighter plane covers it in
    the 3D scene.
    """
    width = int(round(TV_SIZE_MM[0]))
    height = int(round(TV_SIZE_MM[1]))
    face = np.full((height, width, 3), (38, 36, 34), dtype=np.uint8)

    dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
    inset = int(round((CARDSTOCK_MM - MARKER_SIZE_MM) / 2.0))
    card = int(round(CARDSTOCK_MM))

    for marker_id, (x_mm, y_mm) in MARKER_LAYOUT_MM.items():
        marker = cv2.aruco.generateImageMarker(
            dictionary, marker_id, int(MARKER_SIZE_MM)
        )
        card_x, card_y = _screen_to_canvas(x_mm - inset, y_mm - inset)
        face[card_y : card_y + card, card_x : card_x + card] = 250

        marker_x, marker_y = card_x + inset, card_y + inset
        size = marker.shape[0]
        face[marker_y : marker_y + size, marker_x : marker_x + size] = marker[
            :, :, np.newaxis
        ]

    return face


def _render_tv_face_roughness() -> np.ndarray:
    """Per-pixel roughness for the TV face, aligned with its base colour.

    Matte cardstock patches on a semi-gloss bezel -- the distinction
    README's "Matte substrate only. Never glossy" warning turns on, as a
    surface property the renderer acts on rather than a note.
    """
    width = int(round(TV_SIZE_MM[0]))
    height = int(round(TV_SIZE_MM[1]))
    roughness = np.full((height, width), round(ROUGHNESS["bezel"] * 255), np.uint8)

    card = int(round(CARDSTOCK_MM))
    inset = int(round((CARDSTOCK_MM - MARKER_SIZE_MM) / 2.0))
    for x_mm, y_mm in MARKER_LAYOUT_MM.values():
        card_x, card_y = _screen_to_canvas(x_mm - inset, y_mm - inset)
        roughness[card_y : card_y + card, card_x : card_x + card] = round(
            ROUGHNESS["cardstock"] * 255
        )
    return roughness


def _render_screen_content() -> np.ndarray:
    """Colourful game-ish content for the panel.

    Deterministic, and only ever a bright, saturated, high-contrast
    thing next to the markers -- which is the point, not the artwork.
    """
    width = int(round(SCREEN_SIZE_MM[0]))
    height = int(round(SCREEN_SIZE_MM[1]))
    image = np.zeros((height, width, 3), dtype=np.uint8)

    sky_top = np.array([200, 90, 40], dtype=np.float64)
    sky_bottom = np.array([250, 200, 120], dtype=np.float64)
    ramp = np.linspace(0.0, 1.0, height)[:, np.newaxis]
    image[:, :] = (sky_top * (1 - ramp) + sky_bottom * ramp)[:, np.newaxis, :].astype(
        np.uint8
    )

    horizon = int(height * 0.62)
    image[horizon:, :] = (40, 120, 60)

    rng = np.random.default_rng(seed=7)
    for index in range(9):
        block_w = int(rng.integers(60, 190))
        block_h = int(rng.integers(70, 230))
        x = int(rng.integers(0, width - block_w))
        y = int(rng.integers(horizon - block_h, height - block_h))
        colour = tuple(int(c) for c in rng.integers(30, 255, size=3))
        cv2.rectangle(image, (x, y), (x + block_w, y + block_h), colour, -1)
        if index % 2 == 0:
            cv2.rectangle(image, (x, y), (x + block_w, y + block_h), (20, 20, 20), 4)

    cv2.circle(image, (int(width * 0.8), int(height * 0.2)), 60, (90, 240, 250), -1)
    return image


def _render_room() -> np.ndarray:
    """Colourful room wall behind the TV.

    Rendered at a coarse scale: it only has to give the background
    something for the detector to reject and the camera to parallax
    against, so storing it at full mm resolution would be waste.
    """
    width, height = 600, 360
    room = np.zeros((height, width, 3), dtype=np.uint8)

    wall_top = np.array([150, 130, 110], dtype=np.float64)
    wall_bottom = np.array([90, 80, 75], dtype=np.float64)
    ramp = np.linspace(0.0, 1.0, height)[:, np.newaxis]
    room[:, :] = (wall_top * (1 - ramp) + wall_bottom * ramp)[:, np.newaxis, :].astype(
        np.uint8
    )

    rng = np.random.default_rng(seed=11)
    for _ in range(7):
        block_w = int(rng.integers(40, 120))
        block_h = int(rng.integers(40, 110))
        x = int(rng.integers(0, width - block_w))
        y = int(rng.integers(0, height - block_h))
        colour = tuple(int(c) for c in rng.integers(40, 220, size=3))
        cv2.rectangle(room, (x, y), (x + block_w, y + block_h), colour, -1)

    return room


def _degrade(image: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    working = image.astype(np.float64)

    kernel = DEGRADATION["blur_kernel"]
    working = cv2.GaussianBlur(
        working, (kernel, kernel), sigmaX=DEGRADATION["blur_sigma"]
    )

    working += rng.normal(loc=0.0, scale=DEGRADATION["noise_sigma"], size=working.shape)

    return np.clip(working, 0, 255).astype(np.uint8)


def render_sequence(
    work_dir: Path,
    keyframes: list[dict],
    frame_count: int,
    blend_path: Path,
) -> tuple[Path, list[dict]]:
    """Render the TV scene along a camera path; returns (raw dir, ground truth).

    Shared with the close-range fixture generator, which needs the same
    scene and the same ground-truth derivation and differs only in where
    the camera goes.
    """
    tv_face_texture = work_dir / "tv_face.png"
    tv_face_roughness = work_dir / "tv_face_roughness.png"
    screen_texture = work_dir / "screen.png"
    room_texture = work_dir / "room.png"
    cv2.imwrite(str(tv_face_texture), _render_tv_face())
    cv2.imwrite(str(tv_face_roughness), _render_tv_face_roughness())
    cv2.imwrite(str(screen_texture), _render_screen_content())
    cv2.imwrite(str(room_texture), _render_room())

    raw_dir = work_dir / "raw"
    ground_truth_path = work_dir / "ground_truth.json"
    config_path = work_dir / "scene_config.json"
    config_path.write_text(
        json.dumps(
            {
                "tv_face_texture": str(tv_face_texture),
                "tv_face_roughness_texture": str(tv_face_roughness),
                "screen_texture": str(screen_texture),
                "room_texture": str(room_texture),
                "raw_dir": str(raw_dir),
                "ground_truth_path": str(ground_truth_path),
                "blend_path": str(blend_path),
                "screen_size_mm": list(SCREEN_SIZE_MM),
                "tv_size_mm": list(TV_SIZE_MM),
                "room_size_mm": list(ROOM_SIZE_MM),
                "room_distance_mm": ROOM_DISTANCE_MM,
                "screen_emission_strength": SCREEN_EMISSION_STRENGTH,
                "lights": LIGHTS,
                "cycles_samples": CYCLES_SAMPLES,
                "cycles_seed": CYCLES_SEED,
                "resolution": list(RESOLUTION),
                "camera_fov_deg": CAMERA_FOV_DEG,
                "frame_count": frame_count,
                "keyframes": keyframes,
            },
            indent=2,
        )
    )

    result = subprocess.run(
        [
            BLENDER_BINARY,
            "--background",
            "--python",
            str(SCENE_SCRIPT),
            "--",
            str(config_path),
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        sys.stderr.write(result.stdout)
        sys.stderr.write(result.stderr)
        raise RuntimeError(
            f"{BLENDER_BINARY} failed with exit code {result.returncode}. "
            "Set $BORESIGHT_BLENDER if your Blender binary has another name."
        )

    return raw_dir, json.loads(ground_truth_path.read_text())


def main() -> None:
    if FIXTURE_DIR.exists():
        shutil.rmtree(FIXTURE_DIR)
    FIXTURE_DIR.mkdir(parents=True)

    with tempfile.TemporaryDirectory() as tmp:
        # Raw renders live in a temp dir and are discarded: only the
        # degraded frames are the fixture, and keeping both would double
        # the checked-in bytes for no added coverage.
        raw_dir, ground_truth = render_sequence(
            Path(tmp), KEYFRAMES, FRAME_COUNT, BLEND_PATH
        )

        frames = []
        for entry in ground_truth:
            frame_number = entry["frame"]
            raw_path = raw_dir / f"frame_{frame_number:04d}.png"
            raw_image = cv2.imread(str(raw_path), cv2.IMREAD_COLOR)
            if raw_image is None:
                raise RuntimeError(f"Blender did not produce {raw_path}")

            rng = np.random.default_rng(seed=DEGRADATION["base_seed"] + frame_number)
            degraded = _degrade(raw_image, rng)

            filename = f"frame_{frame_number:04d}.jpg"
            cv2.imwrite(
                str(FIXTURE_DIR / filename),
                degraded,
                [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY],
            )
            frames.append(
                {
                    "frame": frame_number,
                    "file": filename,
                    "aim_point_screen_mm": entry["aim_point_screen_mm"],
                }
            )

    manifest = {
        "image_size": [float(RESOLUTION[0]), float(RESOLUTION[1])],
        "screen_size_mm": list(SCREEN_SIZE_MM),
        "marker_size_mm": MARKER_SIZE_MM,
        "cardstock_mm": CARDSTOCK_MM,
        "marker_layout_mm": {str(k): list(v) for k, v in MARKER_LAYOUT_MM.items()},
        "bezel_mm": BEZEL_MM,
        "tv_size_mm": list(TV_SIZE_MM),
        "camera_fov_deg": CAMERA_FOV_DEG,
        "screen_emission_strength": SCREEN_EMISSION_STRENGTH,
        "roughness": ROUGHNESS,
        "lights": LIGHTS,
        "cycles_samples": CYCLES_SAMPLES,
        "keyframes": KEYFRAMES,
        "degradation": DEGRADATION,
        "jpeg_quality": JPEG_QUALITY,
        "blender": BLENDER_BINARY,
        "frames": frames,
    }
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2) + "\n")

    print(f"Wrote {len(frames)} frames, {MANIFEST_PATH}, and {BLEND_PATH}")


if __name__ == "__main__":
    main()
