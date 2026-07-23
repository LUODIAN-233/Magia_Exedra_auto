# Template packs and resolutions

Language: [简体中文](./首页) · [English](./Home_EN) · [日本語](./ホーム)

## The aim junction

The `aim/` directory at the repository root is not a real folder but a Windows directory junction that points to one of the real template packs under `language/<lang>/<lang>_<resolution>/`. Switching language or resolution just repoints the `aim` junction; the actual template files are never moved. All runtime paths (`./aim/...`) work as usual because the junction is transparent to reads.

The junction is created with `cmd /c mklink /J` (no admin privileges required) and removed with `os.rmdir` (which removes only the link, not the target contents).

## Pack organization

Source packs are `language/EN/EN_2560x1440` and `language/JP/JP_2560x1440`. Derived 720p/1080p/4K directories are preserved by committed `.gitkeep` files and populated by the Refresh button.

`language/active.json` stores the last selection, but the actual `aim` target remains authoritative.

## Template file naming

Template filenames use the `picture` argument, not `name`. `click_item_with_result(self, picture, name)` and `find_item_with_result(...)` try `<picture>_1.png`, `<picture>_2.png`, and so on until the first missing number. `name` is only a log label.

Numbering must start at `_1` and remain contiguous. For example, under `crystalis/` you have `play_1.png`, `result_1.png` through `result_13.png`, `retry_1.png`, and so on.

## Resolution scaling

2K (2560x1440) is the single standard source; other resolutions are derived by scale factor:

| Resolution | Factor | Notes |
|:----------:|:------:|:------|
| 1280x720 | 0.5x | Downsample, good quality |
| 1920x1080 | 0.75x | Downsample, good quality |
| 3840x2160 | 1.5x | Upsample, non-integer, slightly blurry |

Downsampled 720p/1080p packs are higher quality than upsampled 4K packs, but better than an empty pack.

Scaling uses `tools/ImageMagick/magick.exe`. `mogrify -path` flattens subdirectories and breaks the `<dirpath>_N.png` grouping, so scaling runs `magick convert` per file and preserves the source pack's subdirectory structure in the target pack.

A target is generated only when missing or older than the 2K source, so repeated refreshes do not reprocess or leave stale templates.

## Pack usability

A pack is usable only when its safe real directory tree contains at least one non-reparse PNG that passes structure, CRC, and Pillow decode checks. Complete PNG validation checks chunk length, CRC, and IHDR/IEND to prevent truncated files from being mistaken for complete packs.

Dropdown selection auto-switches on `QComboBox.activated`; programmatic refresh does not trigger switching. Empty/invalid packs show `（空）`.

## Runtime resolution matching

At startup the client width and height (the actual render area, excluding title bar and borders) are compared independently, each allowing `|detected - expected| <= max(40px, expected*10%)`. This tolerates small offsets from title bars, borders, and DPI scaling without requiring exact equality.

Unknown or mismatched resolution blocks startup. Scaled coordinate actions reject an unknown pack factor rather than guessing 2K.

## Important rules

- Never manually merge/rename `aim/` or edit derived templates as the source of truth. Add variants to the 2K source pack and regenerate
- Do not delete empty-pack `.gitkeep` placeholders. Missing pack directories are not recreated by the scaler
- `aim/`, `active.json`, derived PNGs, and `.source_hashes.json` are all gitignored (see `.gitignore`)

> This page is an AI translation and may contain ambiguities or inaccuracies. For authoritative content, refer to the [简体中文 Wiki](./模板包与分辨率).
