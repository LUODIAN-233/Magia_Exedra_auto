<div align="center">
  <h1>Magia Exedra 自动挂机</h1>
  <p>基于图像识别的 <strong>Magia Exedra</strong> Windows 游戏自动化脚本</p>
  <p>支持 Link Raid 与晶花双模式自动挂机，附语言/分辨率切换与素材自动缩放</p>
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

## 功能一览

### Link Raid 自动挂机

> 起始界面：游戏主界面（灯台界面）

- 自动进入 `backup_requests` 界面，刷新并寻找指定等级队伍
- 找不到目标等级时自动下滑列表，最多下滑 4 次
- 自动清理已结束的战斗（joined battles）
- 战斗结束后自动点赞
- 可设置体力药使用次数（**0 ~ 10 次**）
- 支持 LV6 ~ LV12 等级选择

### 晶花自动挂机

> 起始界面：选好队伍后的界面（点 `play` 即进入战斗的界面）

- 自动重复刷关，战斗结束后自动点击 `retry` 继续
- 可设置体力药使用次数（**0 ~ 8 次**）
- 体力耗尽且喝药次数用完则自动停止

### 通用功能

- 启动时自动将游戏窗口置前
- 停止按钮可随时中断任意挂机任务
- 两种挂机任务互斥运行，挂机期间禁止切换或刷新模板
- 普通界面等待 60 秒、战斗等待 30 分钟仍未识别到目标时自动安全停止
- 仅截取游戏窗口进行识别；窗口或模板异常时记录失败，不会直接崩溃
- 语言 / 分辨率切换（支持英语、日语，多分辨率素材自动缩放）
- 2K 原生素材一键缩放至 720p / 1080p / 4K

---

## 运行原理

| 模块 | 技术方案 |
|:-----:|:---------|
| 图像识别 | OpenCV `TM_SQDIFF_NORMED`，匹配阈值 `0.8` |
| 点击操作 | PyAutoGUI（先移动再点击，否则游戏判定无效） |
| 窗口管理 | pywinctl（按标题 `MadokaExedra` 查找窗口） |
| GUI 界面 | PySide6 |
| 素材缩放 | ImageMagick（`tools/ImageMagick/magick.exe`） |
| 模板切换 | Windows 目录联接（junction），`aim/` 指向 `language/` 下的真实包 |

### 工作流程

```
main.py（GUI 入口，仅负责启动/停止/传参）
   │
   ├── workers/LinkRaidWorker ──► click_action ──► click_behavior ──► 游戏
   │   (Link Raid)               (模板迭代+坐标)  (匹配+点击+窗口)
   │
   ├── workers/CrystalisWorker ──► click_action ──► click_behavior ──► 游戏
   │   (晶花)
   │
    └── LanguageSwitcherWidget
          ├── language_switcher（junction 管理）
          └── image_scaler（2K -> 其他分辨率）
```

---

## 环境要求

| 项目 | 要求 |
|:----:|:-----|
| 操作系统 | Windows |
| 游戏 | Magia Exedra，窗口标题 `MadokaExedra`，**16:9** 窗口化运行 |
| Python | 3.x |

---

## 使用方法

### 方式一：使用发行版（推荐）

下载发行版并解压，运行对应 EXE 即可（所有依赖已打包在内）。

### 方式二：从源码运行 / 自行打包

```bash
# 安装依赖（项目无 requirements.txt，需手动安装）
pip install pyautogui PySide6 opencv-python pywinctl

# 运行
python main.py

# 打包为 exe
pyinstaller -D -i resource/main.ico main.py
```

---

## 操作说明

### 1. Link Raid 挂机

需在游戏主界面（灯台界面）启动

- 选择要挂机的等级（LV6 ~ LV12）
- 设置喝体力药次数（0 ~ 10）
- 点击「**link raid挂机启动**」

### 2. 晶花挂机

需在选好队伍后的界面启动（点 `play` 即进入战斗的界面）

- 设置喝体力药次数（0 ~ 8）
- 点击「**自动刷晶花，需要在play界面启动**」

### 3. 语言 / 分辨率切换

- 下拉选择语言和分辨率后**自动切换**，无需额外点击确认
- 语言下拉显示中文名（英语 / 日语），数据为真实代码
- 空模板包显示为「（空）」并拒绝切换

### 4. 刷新列表

将 2K（2560×1440）原生素材自动缩放到其他分辨率：

| 源分辨率 | → 缩放目标 | 倍率 |
|:--------:|:----------:|:----:|
| 2560×1440 | 1280×720 | 0.5x（下采样）|
| 2560×1440 | 1920×1080 | 0.75x（下采样）|
| 2560×1440 | 3840×2160 | 1.5x（上采样）|

> 720p / 1080p 为下采样，质量良好；4K 为上采样（非整数倍重采样），模板略糊。
> 目标文件不存在或对应 2K 源文件内容变化时会自动生成，已从源包删除的派生模板会自动清理。缩放完成后列表会自动刷新。

---

## 注意事项

> **测试状态：** 本次线程停止、等待超时、游戏窗口截图和模板增量缩放相关更新仅通过语法、导入及静态差异检查，尚未在真实游戏中进行长时间、全流程深度测试。使用前建议先短时间观察运行情况。

- **游戏窗口必须在最前面且不能被其他窗口遮挡**，挂机软件自身可以放在后台
- Link Raid 的首次点击使用**硬编码坐标**（`2000,1000` → `2400,1200`，2K 基准），会按当前激活分辨率自动缩放，720p / 1080p / 2K / 4K 均可正常使用
- 游戏需以 **16:9** 窗口化运行，且模板的语言与分辨率需与游戏一致
- JP 服务器可在游戏内切换至 EN，从而复用英语模板，无需重新截图

---

## 项目结构

```
Magia_Exedra_auto/
├── main.py                  # GUI 入口：仅构造/启动/停止工作线程并传参
├── workers/                 # 挂机运行逻辑包（与 GUI 解耦）
│   ├── base.py              # 工作线程基类（运行/停止状态、重试与超时停止）
│   ├── link_raid.py         # Link Raid 挂机流程
│   └── crystalis.py         # 晶花挂机流程
├── click_action.py          # 高级点击动作（模板迭代、坐标点击、拖拽）
├── click_behavior.py        # 低级操作（截图、匹配、点击、窗口聚焦）
├── language_switcher.py     # 语言/分辨率切换（junction 管理）
├── image_scaler.py          # 素材缩放（2K → 其他分辨率）
├── language/                # 模板包目录
│   ├── EN/                  # 英语
│   │   ├── EN_1280x720/     # 720p（缩放生成）
│   │   ├── EN_1920x1080/    # 1080p（缩放生成）
│   │   ├── EN_2560x1440/    # 2K 原生素材
│   │   └── EN_3840x2160/    # 4K（缩放生成）
│   └── JP/                  # 日语
│       └── ...
├── aim/                     # 运行时 junction，指向当前使用的模板包
├── screenshot/              # 运行时截图存放目录
├── resource/
│   └── main.ico             # 程序图标
├── tools/
│   └── ImageMagick/         # 便携版 ImageMagick（用于素材缩放）
└── AGENTS.md                # 给 AI 助手的项目说明（开发参考）
```

### 核心约定

- **返回值约定**：`2` = 成功 / 找到 / 点击；`1` = 未找到 / 继续尝试。非布尔。
- **模板编号**：`click_item_with_result` 按 `<name>_1.png`、`<name>_2.png`… 递增尝试直到文件不存在，新增变体只需放入下一个编号图片。
- **运行/停止状态**：每个工作线程各自维护 `_active`（自身是否运行）与 `_stop_event`（GUI 停止事件），不再使用全局 `guaji` 标志；`stop()` 对未启动或已结束的线程调用也安全，同一个线程对象可反复启动。

---

## 鸣谢

| 贡献者 | 贡献内容 |
|:------:|:---------|
| **TIAN000000** | v1.0.0+ 脚本整体思路及后续维护 |
| **洛殿** | v1.0.0+ 部分日语素材及分辨率缩放方案<br>v2.0.0+ 提供算力支撑及日语素材 |
| **智谱AI** | v2.0.0+ 完全由 GLM-5.2 重写并构建 |

---

## 补充说明

此脚本**无法在手机上运行**（无法通过 ADB 控制）。游戏在检测到 ADB 连接后会拒绝运行，且反作弊机制限制键盘输入脚本。基于窗口图像识别的 PC 方案是目前折中门槛最低的方案。

> 本脚本仅供学习交流使用，请遵守游戏服务条款，对使用本脚本产生的任何后果概不负责。
