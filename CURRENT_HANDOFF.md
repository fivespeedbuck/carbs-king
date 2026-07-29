# 当前交接：2026-07-29 阶段收尾

> 本文件只记录当前可执行事实。完整复盘见 `STAGE_RETROSPECTIVE_2026-07-29.md`，稳定产品约束见 `PROJECT_CONTEXT.md`。

## 当前状态

- 正式目录：`D:\carbs-king`
- 收尾分支：`codex/main-cleanup`
- 功能/资源清理提交：`ca4f08c fix: finalize challenge flow and asset build gate`
- UI 收口提交：`b44934f fix: align mobile page card widths`
- 用户已明确授权推送并快进合并到 `main`；禁止 force-push 和历史改写。
- 全量回归：381 项通过。
- 工作树在提交复盘文档后应保持干净。

## 最终 APK

- 文件：`build/apk/carbs_king.apk`
- 包名：`com.chenyang.carbs_king`
- versionName：`1.2.3`
- versionCode：`74`
- 大小：201,510,855 字节
- SHA-256：`A460541071FE27DD40962284F36B09A4A81E2BFAA0240E7E9AD2E7C5A08DBA7C`
- APK v2 签名有效；证书 SHA-256：`172A8B5C7A909A79FB483F83CF9FEA71FE6567937C900C1D47EAF0FD67AD75CE`
- 证书与历史 Build 55 APK 一致，具备覆盖安装所需的签名连续性。
- `pyproject.toml` 已准备下一次 Build 75。

## 资源门禁

- 根目录 `assets/**` 是唯一应用资源源。
- 训练媒体只由 `assets/exercises/**` 进入 Git LFS。
- `src/assets/**` 是构建前生成的镜像，不提交 Git。
- 根资源与 APK 内层 `assets/flutter_assets/app/app.zip` 一致：
  - 2653 个文件
  - 155,783,546 字节
  - 1324 GIF
  - 1324 JPG
  - 2 MP3
  - 1 WAV
- 构建入口：`powershell -ExecutionPolicy Bypass -File .\build_apk_update.ps1`
- 详细流程：`docs/agent-notes/build-release.md`

## 当前产品结果

- 自动宏量公式已按减脂、保持、增肌和高/中/低碳日分别计算并保证热量闭合。
- 目标挑战支持最多 3 个同时进行且可属于同一赛道；完成和失败均由用户点击卡片后确认，不自动打断页面。
- 精锐为红色最高等级且仅精锐播放完整训练完成音频；失败为灰色且静音。
- 挑战详情弹窗已改为内容自适应高度。
- 新建挑战目标值与单位控件已对齐。
- 今日、训练、饮食、数据、我五个主页的大卡均以数据页边界为统一宽度。
- `main.py` 仍只承担路由、控制器装配和运行时基础职责，没有功能表单或直接 JSON 持久化。

## 远端发布注意事项

- GitHub `main` 在本阶段收尾时由用户授权快进合并。
- GitHub Release `v1.2.3` 上 71,915,571 字节的 APK 是已知错误包，内含 LFS 指针。
- 不得继续交付该错误包。
- 替换 Release 前必须再次核对本地 APK 的大小、SHA-256、包名、versionCode、签名和内层资源统计。

## 下一阶段

- 下一阶段是整体 UI 视觉重做，重点处理颜色体系、层级和组件风格。
- 视觉重做不得破坏本阶段已经稳定的功能、数据契约、资源门禁、主页宽度和手机布局。
- 目标设备仍为 iQOO 11S，20:9；网页预览用于快速检查，最终以 Android APK 真机为准。
