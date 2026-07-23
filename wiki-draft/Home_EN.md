# Magia Exedra Auto Bot Wiki

Documentation for the image-recognition-based **Magia Exedra** Windows automation tool.

Language: [简体中文](./首页) · [English](./Home_EN) · [日本語](./ホーム)

## Documentation Index

| Document | Description |
|:---------|:------------|
| [Run from source and build](./Run-from-source-and-build) | Running from source, installing dependencies, and PyInstaller packaging |
| [Architecture](./Architecture) | Module layout, call relationships, and key conventions |
| [Template packs and resolutions](./Template-packs-and-resolutions) | Template organization, the `aim` junction, and multi-resolution scaling |
| [Automatic updates and releases](./Automatic-updates-and-releases) | Update checking, safe installation, and release workflow |
| [Development conventions](./Development-conventions) | Code style, return-value conventions, and guide for adding new modes |

## Overview

This tool recognizes game scenes via OpenCV `TM_SQDIFF_NORMED` template matching, performs clicks with PyAutoGUI, and provides a GUI built with PySide6. Two farming modes are supported:

- **Link Raid**: enters backup requests, refreshes, searches for LV6-LV12 teams, clears finished battles, joins fights, and gives likes
- **Crystalis**: clicks `play`, waits for results, and repeats stages via `retry`

Both modes support a configurable stamina-potion count and support English/Japanese templates at `720p` / `1080p` / `2K` / `4K`.

## Quick Navigation

- First-time users should start with [Run from source and build](./Run-from-source-and-build)
- For development, read [Architecture](./Architecture) and [Development conventions](./Development-conventions)
- For template issues, read [Template packs and resolutions](./Template-packs-and-resolutions)
- For releasing a new version, read [Automatic updates and releases](./Automatic-updates-and-releases)

> This page is an AI translation and may contain ambiguities or inaccuracies. For authoritative content, refer to the [简体中文 Wiki](./首页).
