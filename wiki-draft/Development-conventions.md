# Development conventions

Language: [简体中文](./首页) · [English](./Home_EN) · [日本語](./ホーム)

## Code style

- Code comments and GUI prose are Chinese-first
- `README.md` is authoritative; `README_EN.md` and `README_JP.md` are maintained translations
- Default to ASCII; introduce non-ASCII or other Unicode only when there is a clear reason and the file already lives in that character set
- Add succinct comments only where the code is not self-explanatory; avoid empty narration like "assigns the value to the variable"

## Key return-value conventions

- **Template-action return values are `2`/`1`, not booleans.** `2` means success/found/clicked; `1` means not found/keep trying/cancelled. `find_win()` is the exception: it returns a geometry tuple or `None`
- **Template filenames use the `picture` argument, not `name`.** `click_item_with_result(self, picture, name)` and `find_item_with_result(...)` try `<picture>_1.png`, `<picture>_2.png`, and so on until the first missing number. `name` is only a log label. Numbering must start at `_1` and remain contiguous
- Match threshold is strictly `> 0.8` in `click_behavior.routine()` and `routine_only_find()`

## Run/stop state

- Run/stop state is per worker. `_running()` is `_active and not _stop_event.is_set()`
- Use `worker.stop()`; do not reintroduce global `guaji` flags
- `start()` refuses restart while the old thread still runs

## LP recovery values

- LP recovery values are drinks + 1. The GUI displays 0-10 for Link Raid and 0-8 for Crystalis, but passes `shown + 1`
- Internal `1` means zero drinks and stop on first depletion

## Logging

- Use `logging.getLogger(__name__)` for runtime debug output, not `print()`
- The console defaults to WARNING and the file to DEBUG under `logs/`; the `MAGIA_LOG_LEVEL` environment variable overrides the console level
- Worker user-facing status messages still go through `signal.emit` (the GUI log box); do not replace them with `logging`
- `if __name__ == "__main__"` diagnostic blocks may keep `print`; that is CLI direct output, not runtime noise

## GUI parameters

- GUI parameters are registry-driven; there are no module-level parameter globals
- `ParamSpec.kind` supports `choice`, `lp_recover`, and `int`
- To add a new control type, add a `kind` in `registry.py` and a corresponding branch in `main.py`'s `_build_param_widget`

## Adding a new farming mode

1. Write a `BaseWorker` subclass file under `src/workers/`
2. Decorate it with `@register`, declaring the display name, start-screen hint, parameter list, and required templates
3. Add one import line in `src/workers/__init__.py`
4. The `main.py` GUI will automatically show the corresponding button and parameter controls; no GUI code changes needed

The worker must be no-argument-constructible and must route `run()` through `_run_safely()`.

## DPI-sensitive import order

Keep `src.workers` lazy. Startup must remain `QApplication(...) -> mywindow() -> get_worker_registry()`. Importing workers earlier imports PyAutoGUI and may prevent Qt from setting Windows DPI awareness.

## Template pack rules

- `aim/` is a runtime Windows directory junction, not a real template folder
- Never manually merge/rename `aim/` or edit derived templates as the source of truth. Add variants to the 2K source pack and regenerate
- Do not delete empty-pack `.gitkeep` placeholders. Missing pack directories are not recreated by the scaler
- When adding a language, add an entry in `language_switcher.LANG_LABELS`; the GUI reads it automatically

## Game title

The game window title is hardcoded as `MadokaExedra`. Changing it requires updating `main.py`, `click_action.py`, and `click_behavior.py`, or centralizing it first.

## Git and local artifacts

- `.gitignore` ignores `aim/`, `language/active.json`, `__pycache__/`, `*.pyc`, and `logs/`
- Derived PNGs, `.source_hashes.json`, `build/`, `dist/`, and generated `main.spec` may appear untracked; never stage them accidentally
- `tools/ImageMagick/` is committed and required by release packages
- The repository has `main`, `beta`, and potentially other branches. Never infer target branch or release channel from the current branch alone
- Commit messages are plain-language Chinese with a concise subject and body

## Checklist

There is no formal test suite, lint/typecheck config, or CI. After changes, run every applicable non-game check manually:

- Python compile/import checks
- Worker registry and template validation
- Update ZIP/extraction checks
- Lock/updater checks
- AMD64 PE validation
- Packaged-app smoke start

> This page is an AI translation and may contain ambiguities or inaccuracies. For authoritative content, refer to the [简体中文 Wiki](./开发约定).
