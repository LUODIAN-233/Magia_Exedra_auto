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

Startup also calls `log_setup.configure_logging()` to configure logging: the console defaults to WARNING and above (so image-recognition retries do not spam), while DEBUG-level entries are written to a rotating file under `logs/` for post-mortem analysis. Set `MAGIA_LOG_LEVEL=DEBUG` to surface all log output on the console.

## Packaging

Use PyInstaller onedir mode:

```bash
pyinstaller -D -i resource/main.ico main.py
```

This produces only the PyInstaller onedir output (`dist/main/` containing `main.exe` and `_internal/`). A distributable package must also place version-controlled runtime files beside `main.exe`:

- `resource/` (icons and other resources)
- `language/` (template packs, including `.gitkeep` placeholders)
- `tools/` (ImageMagick executables)

`main.exe` must be at the ZIP root. Do not include `aim/`, `active.json`, `.source_hashes.json`, locally generated derived templates, caches, or Git/build metadata in the release package.

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

Only claim live-game validation when it has actually been performed.

> This page is an AI translation and may contain ambiguities or inaccuracies. For authoritative content, refer to the [简体中文 Wiki](./源码运行与构建).
