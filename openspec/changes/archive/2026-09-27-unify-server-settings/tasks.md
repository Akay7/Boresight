## 1. Settings model

- [x] 1.1 Add `ServerOptions`, `MarkerOptions`, `DetectionOptions`, `RecordingOptions` models and tables to `Settings`
- [x] 1.2 Load every known table from the file; map CLI keys for error messages
- [x] 1.3 Keep `save()` writing only `tuning` and `view`, preserving all other tables

## 2. Detection options

- [x] 2.1 `detect.TrackerOptions`; `MarkerTracker` built from it
- [x] 2.2 `AimPipeline(tracking=)`, `MarkerSourceController(tracked_detection=)` and `create_app(tracked_detection=)` accept options (or a bool)

## 3. Server

- [x] 3.1 argparse flags default to None; booleans get both forms
- [x] 3.2 `main()` resolves everything through `resolve_settings` and builds `ServerConfig`, marker layout, detection and recording from the result

## 4. Tests and docs

- [x] 4.1 Tests: file values for each new table, flag beats file, `--no-tls` beats `tls = true`, invalid values name their source, save preserves `[server]`
- [x] 4.2 README: the settings section lists every table
