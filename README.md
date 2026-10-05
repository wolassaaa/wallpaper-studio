# Wallpaper Studio

**让动态壁纸，成为你喜欢的画面。**

Windows 本地壁纸录制与视频选帧工具。中文界面，将素材库、轻量预览、片段选择、裁切和导出放进同一个工作台。

> **v0.4.7 · 首个公开预览版**：先把录制、选帧和常规导出做清楚。Live Photo、iPad 横竖适配等实验入口默认隐藏，不作为已经完成的功能发布。

## 这一版能做什么

| 流程 | 功能 |
| --- | --- |
| 找到素材 | 添加 Steam / Workshop 路径、导入视频或项目目录；按类型、标签与分级筛选 |
| 预览与录制 | 视频轻量代理预览；Scene / Web 使用 Wallpaper Engine 临时窗口渲染与录制 |
| 选择画面 | 播放、逐帧浏览、设置封面、起止区间与定间隔选帧 |
| 调整构图 | 比例、像素尺寸、裁切铺满、补边或拉伸；渲染尺寸与导出尺寸分开设置 |
| 导出 | PNG、批量 PNG、GIF、H.264 MP4；选择输出位置，后台任务可取消 |

预览代理只用于浏览，正式导出读取原始素材。提高输出像素尺寸不代表恢复原图细节。

## 下载与开始使用

在仓库的 **Releases** 页面下载：

- **`WallpaperStudio-0.4.7-win64.zip`**：推荐。解压后运行目录中的 `WallpaperStudio.exe`，保留其他文件。
- **`WallpaperStudio-0.4.7-win64.exe`**：单文件版本，首次启动需解包运行组件。
- `wallpaper-studio-0.4.7-source.zip` 是源码，不是可直接运行的程序。

运行打包版无需安装 Python。视频处理使用随包提供的 FFmpeg；Scene / Web 的真实渲染仍需要已安装 Wallpaper Engine。

### 三步导出

1. 添加素材库路径，或导入视频 / 项目。
2. 预览或录制后，在时间轴选择片段和封面，调整构图。
3. 设置导出位置，选择 PNG / GIF / MP4，点击导出。

## 原始素材与隐私

- 先复制素材到独立任务目录，源项目保持只读；输出位置禁止设在源项目内部。
- 窗口采集针对本工具创建的临时窗口，不录整个桌面，也不结束用户已有的 Wallpaper Engine 会话。
- 真实壁纸、私人照片、测试副本及个人路径不进入公开源码包。
- 实际效果、录制帧率与丢帧以任务报告和设备测试为准。

## 当前边界

- 这是公开预览版，不是全部设备验收完成的稳定版。
- iPad 动态识别尚未通过用户测试；Live Photo 配对结构检查不等同于 Apple 相册识别。
- AI 超分、背景生成与苹果内置壁纸式自动重排尚未完成。
- 实验代码保留，开发测试可使用 `WallpaperStudio.exe --experimental` 显示相关入口；默认界面只展示常规导出。
- 本地 EXE 启动与导出已测试；尚未在全新、未安装 Python 的 Windows 环境完成独立验收。
- Windows 10 1903+ x64 是采集接口要求；推荐 Windows 11。Scene / Web 性能取决于 Wallpaper Engine 与素材本身。

## 开发与构建

Python 3.12：

```powershell
.\scripts\setup.ps1
.\.venv\Scripts\python.exe -m wallpaper_studio
.\.venv\Scripts\python.exe -m pytest -q
.\scripts\build.ps1 -Both
.\.venv\Scripts\python.exe scripts\release_bundle.py --version 0.4.7
```

GitHub Actions 执行测试和 Windows 打包；版本标签生成 **draft / prerelease**，检查通过后再公开发布。发布资产附 SHA-256。

## 反馈与贡献

这是我的第一个公开项目，欢迎反馈。提交 Issue 时，请附上版本、Windows 版本、素材类型、复现步骤和任务日志；上传前去掉个人路径与私人素材。

首版优先修复启动、导入、录制、选帧和常规导出问题，暂不继续扩展功能。

## 来源与许可证

项目源码采用 **GPL-3.0-or-later**。FFmpeg、RePKG、Qt / PySide6 等第三方组件的来源与许可证见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) 和 `licenses/`。

本项目不是 Wallpaper Engine 或 Apple 的官方产品，不附带 Workshop 壁纸。

[历史开发记录](docs/HISTORY.md) · [验收记录](docs/ACCEPTANCE.md) · [发布步骤](docs/GITHUB_RELEASE.md)
