## 1. Pipeline clamp margin

- [x] 1.1 Add `EDGE_MARGIN = 0.01` constant to `pipeline.py`
- [x] 1.2 Change `_clamp_unit` to bound into `[EDGE_MARGIN, 1.0 -
      EDGE_MARGIN]` instead of `[0.0, 1.0]`

## 2. Tests

- [x] 2.1 Update `test_an_off_panel_aim_point_is_clamped_and_reported`
      to expect `(EDGE_MARGIN, 1.0 - EDGE_MARGIN)` instead of the
      literal `(0.0, 1.0)`
- [x] 2.2 Confirm the full suite still passes (`uv run pytest`) and
      `ruff check` is clean

## 3. Manual verification

- [ ] 3.1 On a machine where the edge-gesture interference was
      observed, run the aim pipeline with an aim point held near a
      screen edge/corner for several seconds and confirm no
      window-manager gesture (minimize, overview, show-desktop) fires
