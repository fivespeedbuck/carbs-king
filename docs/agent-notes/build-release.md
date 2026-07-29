# 本地 APK 构建与发布门禁（P0）

## P0：资源完整性是发布阻断项

本项目的 Flet 应用目录是 `src`。Android 构建器只会打包 `src/assets`；根目录的
`assets` 不会自动进入 APK。训练 GIF、提示音和图标必须同时在 `src/assets` 中存在，
并且训练 GIF 必须被 Git 跟踪，保证干净检出后的构建也完整。

以下任一情况都视为 P0，禁止发布或替换 GitHub Release：

- APK 内 GIF 或音频数量为 0，或明显低于源资源数量；
- `src/assets/exercises` 缺失、为空或被 `.gitignore` 排除；
- 仅验证了构建命令成功，未检查 APK 压缩包内容；
- 构建日志出现 UTF-8/GBK 编码错误。

## 每次本地构建的固定流程

1. 在正式目录 `D:\carbs-king` 执行，不能在临时 worktree 或其他目录发布。
2. 构建前启用 UTF-8：

   ```powershell
   chcp 65001
   $env:PYTHONUTF8 = "1"
   $env:PYTHONIOENCODING = "utf-8"
   ```

3. 核对源资源数量：`assets` 与 `src/assets` 的 GIF、MP3、WAV 数量应一致。
4. 使用项目指定的 Flet 执行 APK 构建。
5. 将 APK 当作 ZIP 检查：Flet 会把应用资源放在
   `assets/flutter_assets/app/app.zip` 的内层 ZIP；必须统计这个内层 ZIP 的 GIF、MP3、WAV
   数量和总体积，并与第 3 步对照。不能只统计 APK 最外层文件名。
6. 运行相关测试及 `git diff --check`。所有检查通过后，才允许提交、推送或上传 Release。

## 验收基线

截至 2026-07-29，源资源基线为：1324 个 GIF、3 个音频文件。数字变化时应有对应的
资源变更说明；不能因为 APK 体积变小或构建成功而跳过内容核验。

## 复现与诊断

若 APK 缺资源，先检查 `pyproject.toml` 的 `[tool.flet.app] path = "src"`，再检查
`src/assets/exercises` 是否实际存在且已纳入版本控制。不要先怀疑 Android 构建器，也不要
直接重试发布。
