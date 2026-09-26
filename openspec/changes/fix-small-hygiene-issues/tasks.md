## 1. Layout source: empty `file:` path

- [x] 1.1 In `layout_source.resolve_layout`, test the raw text after `file:` (stripped) instead of `Path(...)`, raising `LayoutSourceError` with the "needs a path ... or use plain 'file'" message; verify `marker_map_factory('file:')` no longer raises `IsADirectoryError`
- [x] 1.2 Add tests in `tests/test_layout_source.py` for `file:` and `file:   `; verify `uv run pytest tests/test_layout_source.py` passes

## 2. uinput permission message

- [x] 2.1 Point the `/dev/uinput` error in `inject.py` at README.md's "`/dev/uinput` permission" paragraph under "Running the server"; verify with `grep -n "setup notes" src/boresight/inject.py` returning nothing and the README paragraph existing

## 3. Vulkan layer: rects against the swapchain extent

- [x] 3.1 Add `bsov_fits_extent` to `canvas_format.{h,c}` (size equals extent, pixels present, every rect inside the extent via `rect_is_valid`); verify the layer and tests build with `-Wall -Wextra` cleanly
- [x] 3.2 Use it in `overlay_layer.c`'s `try_setup_overlay` right after the existing size comparison (which keeps its specific size-mismatch log line); verify the layer `.so` builds
- [x] 3.3 Add `bsov_fits_extent` cases to `tests/test_canvas_format.c` (exact match incl. edge-touching rects, larger/smaller canvas in each axis, hand-built out-of-extent/overflowing rect, no pixels, NULL); verify `ctest` passes
- [x] 3.4 Make `canvas_format.write_file` reject rects the layer would reject, sharing the rule with `unpack`; add tests in `tests/test_overlay_vulkan_canvas.py`; verify they pass

## 4. Verification

- [x] 4.1 Run `uv run pytest -q`, `uv run ruff check`, `uv run ruff format --check`; all pass
- [x] 4.2 Build the native tests plain, under ASan+UBSan, and under TSan; run ctest (incl. `test_startup_watchdog`) in each and record the results
- [x] 4.3 Run `openspec validate fix-small-hygiene-issues`; it passes
