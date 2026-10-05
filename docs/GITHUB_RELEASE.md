# GitHub 首次发布

仓库名：wallpaper-studio。

仓库介绍：Windows 本地壁纸录制与视频选帧工具：中文工作台、轻量预览、精确选帧、统一裁切，以及 PNG / GIF / MP4 导出。

Release 标题：Wallpaper Studio v0.4.7 — 首个公开预览版。

## 发布前

1. 连接 GitHub 插件，确认账号。不得把账号已安装插件等同于发布完成。
2. 运行完整测试和 scripts/build.ps1 -Both。
3. 运行 scripts/release_bundle.py --version 0.4.7。
4. 审核 dist/v0.4.7/release 中的源码 ZIP；仅公开源码、构建脚本、测试、文档和许可证。
5. 检查提交内容与历史，不提交壁纸、照片、测试输出、个人路径、密钥或打包二进制。

## 发布

- 在已确认的账号下创建公开 wallpaper-studio 仓库，填写上面的介绍。
- 推送审核过的源码；源码用于 Code 页面，EXE 和便携 ZIP 放入 Releases。
- 使用 v0.4.7 标签，Release 设为 prerelease；说明使用 docs/RELEASE_NOTES.md。
- 上传 release 目录的三个分发文件、SHA256SUMS.txt 和 RELEASE_NOTES.md。
- 重新打开仓库和 Release，核对版本、资产名称、大小及哈希，再报告成功。

仓库尚未创建时，不将本地发布包称为已上传。

官方说明：
https://docs.github.com/en/migrations/importing-source-code/using-the-command-line-to-import-source-code/adding-locally-hosted-code-to-github
https://docs.github.com/en/repositories/releasing-projects-on-github/about-releases
