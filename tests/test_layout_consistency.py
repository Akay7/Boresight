"""The shipped layout and the rendered fixtures must not drift apart.

`config/markers.toml` is what the software ships with; the fixture
manifests record what Blender actually rendered. They are maintained in
two different places -- a TOML file and a constants block in
`tests/generate_synthetic_video_fixture.py` -- so nothing but this test
stops them diverging.

The failure this prevents is a nasty one: edit one and not the other and
the symptom is a mysterious accuracy regression in the e2e decks, not an
obvious config mismatch. It also records that the shipped file is not
arbitrary -- it is the layout every accuracy figure in README was
measured against.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from boresight.marker_map import load_marker_map
from boresight.pipeline import DEFAULT_CONFIG_PATH

FIXTURE_DIRS = [
    Path(__file__).parent / "fixtures" / "synthetic_video",
    Path(__file__).parent / "fixtures" / "close_range",
]


@pytest.fixture(scope="module")
def layout():
    return load_marker_map(DEFAULT_CONFIG_PATH)


@pytest.mark.parametrize("fixture_dir", FIXTURE_DIRS, ids=lambda p: p.name)
def test_shipped_layout_matches_fixture_manifest(layout, fixture_dir: Path) -> None:
    manifest = json.loads((fixture_dir / "manifest.json").read_text())

    assert layout.screen_size_mm == tuple(manifest["screen_size_mm"])

    rendered = {
        int(marker_id): tuple(top_left)
        for marker_id, top_left in manifest["marker_layout_mm"].items()
    }
    assert set(layout.markers) == set(rendered), (
        "config/markers.toml and the rendered scene declare different marker IDs"
    )

    rendered_size = manifest["marker_size_mm"]
    for marker_id, top_left in rendered.items():
        marker = layout.markers[marker_id]
        assert (marker.x_mm, marker.y_mm) == top_left, (
            f"marker {marker_id} is at {(marker.x_mm, marker.y_mm)} in "
            f"config/markers.toml but was rendered at {top_left}"
        )
        assert marker.size_mm == rendered_size


def test_the_reference_layout_is_the_one_the_readme_describes(layout) -> None:
    """Eight markers: four corners plus four edge midpoints, all on the
    bezel outside the active panel. If this changes, README's
    "Marker visibility and accuracy" numbers no longer describe it."""
    screen_width_mm, screen_height_mm = layout.screen_size_mm

    assert len(layout.markers) == 8
    assert set(layout.markers) == set(range(8))

    for marker in layout.markers.values():
        right = marker.x_mm + marker.size_mm
        bottom = marker.y_mm + marker.size_mm
        outside = (
            right <= 0.0
            or bottom <= 0.0
            or marker.x_mm >= screen_width_mm
            or marker.y_mm >= screen_height_mm
        )
        assert outside, (
            f"marker {marker.marker_id} overlaps the active panel; every "
            "marker is meant to sit on the bezel outside it"
        )
