# 本地 APK 构建与发布门禁（P0）

## 单一资源源

- 根目录 `assets/**` 是唯一应用资源源。
- 训练媒体只由 `assets/exercises/**` 进入 Git LFS；不得再提交
  `src/assets/**` 的副本。
- Flet 应用路径是 `src`，所以 `build_apk_update.ps1` 会在构建前把根目录
  `assets` 镜像到被 Git 忽略的 `src/assets`。该目录是生成物。

## 以下情况禁止发布

- `git lfs pull` 失败；
- 根资源中出现 `version https://git-lfs.github.com/spec/v1` 指针文本；
- 任一 GIF 文件头不是 `GIF87a` 或 `GIF89a`；
- 根资源与 `src/assets` 的路径、大小或 SHA-256 不一致；
- APK 缺少 `assets/flutter_assets/app/app.zip`；
- 内层 ZIP 的资源路径、大小、SHA-256 或 GIF 文件头与根资源不一致；
- 构建、测试、语法检查或 `git diff --check` 失败。

## 固定构建流程

在正式目录 `D:\carbs-king` 使用：

```powershell
chcp 65001
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
powershell -ExecutionPolicy Bypass -File .\build_apk_update.ps1
```

脚本按顺序执行：

1. `git lfs pull --include="assets/exercises/**"`；
2. `tools/asset_gate.py verify-source`，同时核对 Git 资源清单；
3. 使用固定源/目标路径将 `assets` 镜像到 `src/assets`；
4. `tools/asset_gate.py verify-mirror` 逐文件核对；
5. Flet APK 构建；
6. `tools/asset_gate.py verify-apk` 检查 APK 内层 `app.zip`；
7. 只有以上全部通过后，才把 `pyproject.toml` 的 Build 号加一。

长时间构建应使用隐藏后台进程和独立日志，每次轮询不超过 60 秒。工具等待超时
不等于构建失败；必须继续检查实际进程、日志和 APK 更新时间。

## 当前资源基线

截至 2026-07-29：

- 根目录 `assets/exercises`：2649 个文件、155,007,984 字节；
- GIF：1324 个；JPG：1324 个；
- 根目录全部 `assets`：2653 个文件、155,783,546 字节；
- 音频：2 个 MP3、1 个 WAV。

基线变化必须有对应资源提交说明。门禁以逐文件一致为最终标准，不以 APK 大小或
“Successfully built”作为完整性证据。

## Release 规则

- APK 不提交 Git，只上传 GitHub Release；
- 上传前记录本地大小和 SHA-256；上传后核对远端大小与 digest；
- 未经用户确认，不推送分支、不合并 `main`、不覆盖 Release；
- 2026-07-29 的 `v1.2.3` 71,915,571 字节 APK 含 LFS 指针，是已知错误包。
