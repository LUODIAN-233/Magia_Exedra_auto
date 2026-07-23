<div align="center">
  <h1>Magia Exedra 自动挂机</h1>
  <p>基于图像识别的 <strong>Magia Exedra</strong> Windows 游戏自动化工具</p>
  <p>支持 Link Raid 与晶花自动挂机，以及英语/日语、多分辨率模板切换</p>
  <p>
    <img alt="Platform" src="https://img.shields.io/badge/平台-Windows-blue">
    <img alt="Python" src="https://img.shields.io/badge/Python-3.x-blue">
    <img alt="Qt" src="https://img.shields.io/badge/GUI-PySide6-green">
    <img alt="License" src="https://img.shields.io/badge/用途-游戏辅助-orange">
  </p>
  <p>
    <a href="./README.md">简体中文</a> · <a href="./README_EN.md">English</a> · <a href="./README_JP.md">日本語</a>
  </p>
</div>

---

## 功能

| 模式 | 说明 |
|:----:|:-----|
| **Link Raid** | 自动进入求援列表、刷新、寻找 LV6-LV12 队伍、清理结束战斗、加入战斗并点赞 |
| **晶花** | 自动点击 `play`、等待结算并通过 `retry` 重复刷关 |

- 两种模式都可设置体力药使用次数；次数用完后自动停止
- 支持英语、日语模板，以及 `720p` / `1080p` / `2K` / `4K`
- 普通界面等待 60 秒、战斗等待 30 分钟仍未识别到目标时安全停止
- 启动前检查游戏窗口、分辨率和必需模板，避免在明显不匹配时误点
- 支持 stable / beta 更新检查；发行版可安全下载和安装通过校验的更新包

## 下载

从 [GitHub Releases](https://github.com/LUODIAN-233/Magia_Exedra_auto/releases) 下载完整 ZIP，解压后运行根目录的 `Magia_Exedra_auto.exe`。

> **不要只复制单个 EXE。** 发行包还需要同级的 `_internal/`、`resource/`、`language/` 和 `tools/`。

## 源码运行

从源码运行需先安装依赖，再执行入口：

```bash
pip install -r requirements.txt
python main.py
```

详细的运行与构建说明见 [Wiki · 源码运行与构建](https://github.com/LUODIAN-233/Magia_Exedra_auto/wiki/源码运行与构建)。

## 快速开始

### Link Raid

1. 让游戏停留在主界面（灯台界面）。
2. 在「选择挂机脚本」中选择「link raid挂机启动」。
3. 设置等级和体力药次数。
4. 点击「启动：link raid挂机启动」。

### 晶花

1. 选择好关卡和队伍，停留在点击 `play` 即可开战的界面。
2. 在「选择挂机脚本」中选择「自动刷晶花，需要在play界面启动」。
3. 设置体力药次数。
4. 点击「启动：自动刷晶花，需要在play界面启动」。

> 点击「停下当前运行的脚本」可以请求停止当前任务。

## 模板设置

- 语言和分辨率在下拉框中选择后**自动切换**
- 界面中的「英语」「日语」对应 `EN` / `JP`
- 「（空）」表示该模板包当前不可用
- 「刷新列表」会从 2K 原始模板生成 `720p` / `1080p` / `4K` 模板
- 游戏语言和窗口分辨率应与当前模板包一致

## 使用须知

- 仅支持 Windows x86-64 / AMD64 窗口化游戏
- 游戏窗口必须保持可见，不能被其他窗口遮挡识图区域
- 程序会激活游戏窗口并使用全局鼠标，挂机期间不要同时操作鼠标
- 坐标换算支持 `720p` / `1080p` / `2K` / `4K`，但实际识图效果仍受 DPI、窗口尺寸和模板质量影响
- JP 服务器可在游戏内切换到 EN，从而复用英语模板
- 运行时日志会滚动写入程序根目录的 `logs/` 文件夹，出现异常时可用于排查；设置环境变量 `MAGIA_LOG_LEVEL=DEBUG` 可让控制台输出全部日志

## Wiki

源码运行、构建发布、项目架构、模板制作、自动更新安全机制和开发约定已移至 Wiki。Wiki 现已支持多语言：

| 语言 | 入口 |
|:----:|:-----|
| 简体中文 | [Wiki 首页](https://github.com/LUODIAN-233/Magia_Exedra_auto/wiki) |
| English | [Wiki Home (EN)](https://github.com/LUODIAN-233/Magia_Exedra_auto/wiki/Home_EN) |
| 日本語 | [Wiki ホーム](https://github.com/LUODIAN-233/Magia_Exedra_auto/wiki/ホーム) |

中文 Wiki 文档：

- [源码运行与构建](https://github.com/LUODIAN-233/Magia_Exedra_auto/wiki/源码运行与构建)
- [项目架构](https://github.com/LUODIAN-233/Magia_Exedra_auto/wiki/项目架构)
- [模板包与分辨率](https://github.com/LUODIAN-233/Magia_Exedra_auto/wiki/模板包与分辨率)
- [自动更新与发布](https://github.com/LUODIAN-233/Magia_Exedra_auto/wiki/自动更新与发布)
- [开发约定](https://github.com/LUODIAN-233/Magia_Exedra_auto/wiki/开发约定)

## 鸣谢

| 贡献者 | 贡献内容 |
|:------:|:---------|
| **TIAN000000** | v1.0.0+ 脚本整体思路及后续维护 |
| **洛殿** | v1.0.0+ 部分日语素材及分辨率缩放方案<br>v2.0.0+ 提供算力支撑及日语素材 |
| **智谱AI** | v2.0.0+ 完全由 GLM-5.2 重写并构建 |

---

> 本脚本仅供学习交流使用，请遵守游戏服务条款。使用本脚本产生的后果由使用者自行承担。
