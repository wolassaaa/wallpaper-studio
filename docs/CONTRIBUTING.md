# 贡献指南

感谢你愿意帮助 Wallpaper Studio。这个项目的目标是做一个轻量、好用的 Windows 壁纸小工具，而不是万能编辑器。小修复、清晰的问题报告和文档改进都很有价值。

## 1. 可以贡献什么

| 方式 | 不需要写代码也能做的事 |
| --- | --- |
| 报告问题 | 写出可重复的操作步骤，说明预期和实际结果 |
| 验证使用流程 | 测试启动、导入、录制、选帧、裁切和导出，记录版本与环境 |
| 完善文档 | 纠正错误、补充使用说明、改善中文表述 |
| 制作测试素材 | 提供小型自制视频、网格图或最小项目，让别人能够复现 |
| 改进代码 | 修复明确的问题、改善性能、补充自动测试 |

当前优先保证基本流程可靠。新格式、大规模界面重写或增加运行依赖等改动，请先通过 [Issue](https://github.com/wolassaaa/wallpaper-studio/issues) 讨论，再开始实现；提交建议不代表一定会合并。

## 2. 怎样报告一个问题

先搜索已有 Issue，避免重复。如果相关问题已存在，可以补充你的测试结果。新问题可复制以下内容：

```text
标题：简短描述出错的步骤

程序版本：
Windows 版本及系统架构：
安装包类型：便携 ZIP / 单文件 EXE / 源码运行
素材类型：Scene / PKG / Web / 视频
是否依赖 Wallpaper Engine：版本或未安装

复现步骤：
1.
2.
3.

预期结果：
实际结果：
是否每次发生：
请求的尺寸 / 帧率 / 片段范围（如相关）：
实际采集报告或错误日志（已去除私人信息）：
最小自制样本（可选）：
```

性能问题请注明素材大致大小、长度、预览档位、采集设置，以及 CPU / 显卡型号。截图优先展示程序错误和设置，不需要提供整个桌面。

**不要公开** API 密钥、令牌、账号凭据、个人路径、私人照片或日志中的敏感信息。不要上传整套 Workshop 壁纸库；优先用自制小素材复现。发现敏感信息时，不要继续转贴到公开 Issue 或 PR。

## 3. 怎样提交代码或文档

1. 在 GitHub 上 Fork 本仓库到自己的账号。
2. 克隆自己的 Fork，创建独立分支；一份 PR 尽量只解决一个问题。
3. 完成修改，检查差异和测试结果，不混入输出文件或私人素材。
4. 将分支推送到自己的 Fork。
5. 向本仓库的 `main` 分支提交 Pull Request，说明改动和验证结果。

以下示例中的 `YOUR_GITHUB_NAME` 要替换为你的 GitHub 用户名：

```powershell
git clone https://github.com/YOUR_GITHUB_NAME/wallpaper-studio.git
cd wallpaper-studio
git checkout -b fix/short-description

# 修改完成后，仅添加本次相关文件
git add docs/USAGE.md
git diff --cached
git commit -m "docs: clarify usage instructions"
git push -u origin fix/short-description
```

`git add` 的文件名和提交说明只是文档贡献示例，请按实际改动替换。使用你希望公开的 Git 提交身份；不希望公开个人邮箱时，可使用 GitHub 提供的 noreply 邮箱。

## 4. 测试与提交要求

代码开发使用 Windows x64 与 Python 3.12。在仓库根目录执行：

```powershell
.\scripts\setup.ps1
$env:QT_QPA_PLATFORM = 'offscreen'
.\.venv\Scripts\python.exe -m pytest -q
```

`setup.ps1` 会安装锁定依赖并准备外部工具，需要网络。交互检查界面前，清除无界面测试设置：

```powershell
Remove-Item Env:QT_QPA_PLATFORM -ErrorAction SilentlyContinue
.\.venv\Scripts\python.exe -m wallpaper_studio
```

- 修复程序问题时，尽量加入能复现原问题的自动测试，再验证修复后的结果。
- 自动测试使用小型自制素材，不把真实壁纸和私人照片加入仓库。
- Scene / Web 的真实渲染测试需要 Wallpaper Engine；本机缺少环境时，如实说明哪些检查未执行。
- 只改文档时，检查链接、示例命令和描述是否与当前程序一致，无需重新打包 EXE。
- 涉及打包、依赖或运行资源时，使用 `scripts/build.ps1 -Both` 验证两种包，并说明启动、依赖检测与导出的结果。
- 不把低清代理当作正式导出源；不将插值放大称为无损恢复；不将 Live Photo 结构检查称为设备识别通过。
- 不提交 `.venv`、`dist`、`build`、任务缓存、密钥或本机配置。提交前查看 `git status` 与 `git diff --cached`。

PR 说明建议包含：

```text
关联 Issue（如有）：
解决的问题：
主要改动：
测试命令与结果：
手动验证步骤与环境（如适用）：
未执行的检查及原因：
截图或自制样本（如适用）：
是否新增依赖、改变导出行为或影响原始素材：
```

请保留与本次修改无关的代码，避免大范围格式化和顺手重构。评审中可能要求缩小改动、补测试或调整方案；暂未合并不代表贡献没有价值，也不承诺固定处理时间。

## 5. 来源、署名与许可证

项目源码的许可证见根目录 [LICENSE](../LICENSE)，第三方来源见 [THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md)。贡献应与项目现有许可证要求兼容，不删除已有版权和许可证说明。

复用第三方代码或增加依赖时，请说明来源、版本和许可证，并补充必要的声明；不要把他人的代码、图片或壁纸当作自己原创提交。

代码贡献通过提交历史和 Pull Request 保留记录，合并提交会体现在 GitHub 的贡献记录中。文档修订、问题报告和测试反馈也同样欢迎。署名只使用你主动公开的 GitHub 身份，不把私人信息写入说明。

## 6. 项目方向

先把启动、素材读取、录制、选帧、构图和常规导出做好。欢迎针对真实问题的小改进；大型功能先讨论，实验功能保持明确标注。

感谢每一份认真反馈，也欢迎从改正一个错字开始。
