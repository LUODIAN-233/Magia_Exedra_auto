# Run from source and build

Language: [简体中文](./首页) · [English](./Home_EN) · [日本語](./ホーム)

## Runtime environment

- OS: Windows x86-64 / AMD64
- Python: 3.x (3.10+ recommended)

## Installing dependencies

Runtime dependencies are declared in `requirements.txt`:

```bash
pip install -r requirements.txt
```

Building a release additionally requires `pyinstaller` (listed but commented out in `requirements.txt`; uncomment it or install separately):

```bash
pip install pyinstaller
```

Asset scaling uses the committed `tools/ImageMagick/magick.exe` and needs no separate install; `magick` on PATH also works.

## Running from source

```bash
python main.py
```

`main.py` is the entry point. On startup it changes the working directory to the script directory so relative runtime paths (`./aim/...`, `./resource/...`) resolve correctly. Startup calls `language_switcher.ensure_active()`, which restores or creates the `aim/` directory junction.

Startup also calls `log_setup.configure_logging()` to configure logging. The GUI log level can be selected at runtime from DEBUG / INFO / WARNING / ERROR / CRITICAL; windowed builds provide logs through the GUI and rotating DEBUG files under `logs/`. When running from source, the console defaults to WARNING and above (so image-recognition retries do not spam), and `MAGIA_LOG_LEVEL` controls its level; for example, set `MAGIA_LOG_LEVEL=DEBUG` to show all log output.

## Packaging

Use PyInstaller onedir mode:

```bash
pyinstaller -D --windowed -i resource/main.ico -n Magia_Exedra_auto main.py
```

`--windowed` prevents an empty console window from appearing beside the GUI. Older console-mode frozen builds remain compatible and hide an existing console at startup. `-n Magia_Exedra_auto` names the built entry executable after the project (`Magia_Exedra_auto.exe` instead of the default `main.exe`); this is the entry executable used in releases. This produces only the PyInstaller onedir output (`dist/Magia_Exedra_auto/` containing `Magia_Exedra_auto.exe` and `_internal/`). A distributable package must also place version-controlled runtime files beside `Magia_Exedra_auto.exe`:

- `resource/` (icons and other resources)
- `language/` (template packs, including `.gitkeep` placeholders)
- `tools/` (ImageMagick executables)

`Magia_Exedra_auto.exe` must be at the ZIP root. Do not include `aim/`, `active.json`, `.source_hashes.json`, locally generated derived templates, caches, or Git/build metadata in the release package.

## Packaging notes

- In frozen mode, `OPENCV_SKIP_PYTHON_LOADER=1` must be set before anything imports `cv2`. `main.py` handles this at the entry point; do not reorder imports.
- **DPI-sensitive import order**: keep `src.workers` lazy. Startup must remain `QApplication(...) -> mywindow() -> get_worker_registry()`. Importing workers earlier imports PyAutoGUI and may prevent Qt from setting Windows DPI awareness. `main.py` calls `log_setup.configure_logging()` at module import, before `QApplication`; the module is stdlib-only and safe, and must run before any business module import so all loggers are captured.

## Verification checks

There is no formal test suite, lint, or CI configuration. After changes, run every applicable non-game check manually:

- Python compile and import checks
- Worker registry and template validation
- Update ZIP and extraction checks
- Lock and updater checks
- AMD64 PE validation
- Packaged-app smoke start

> This page is an AI translation and may contain ambiguities or inaccuracies. For authoritative content, refer to the [简体中文 Wiki](./源码运行与构建).
