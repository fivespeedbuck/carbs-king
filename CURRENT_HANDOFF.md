# 当前交接：2026-07-30 Build 77 发布

> 本文件只记录当前可执行事实。完整复盘见 `STAGE_RETROSPECTIVE_2026-07-29.md`，稳定产品约束见 `PROJECT_CONTEXT.md`。

## 当前状态

- 正式目录：`D:\carbs-king`
- 发布分支：`codex/build77-update-fallback`
- Build 77 已完成自动测试、APK 资源门禁、包名、版本和签名校验。
- 用户已明确授权提交、推送、合并到 `main` 并替换 GitHub Release；禁止 force-push 和历史改写。
- 构建后源码已预备下一次 Build 78。

## 最终 APK

- 文件：`build/apk/carbs_king.apk`
- 包名：`com.chenyang.carbs_king`
- versionName：`1.2.3`
- versionCode：`77`
- 大小：201,554,835 字节
- SHA-256：`9AE333EA927A5D3B3BBF771152CDD50CB322DBA81F01A68F71753E4E0EBA2B7C`
- APK v2 签名有效；证书 SHA-256：`172A8B5C7A909A79FB483F83CF9FEA71FE6567937C900C1D47EAF0FD67AD75CE`
- 证书与历史 Build 55 APK 一致，具备覆盖安装所需的签名连续性。
- `pyproject.toml` 与 `src/app_version.py` 已准备下一次 Build 78。

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
- 数据页六个维度切换已收进“数据”主卡，本周总结等旧浅绿内容底板统一为浅灰。
- 推荐挑战从创建日向后计算周期；达到三项上限时所有创建入口统一显示底部提示。
- 主题色默认绿色，可在“我”页手动切换绿、紫、蓝、黄；白卡与浅灰底板不随主题染色。
- 身高和年龄在“我”页编辑结束后自动保存并提示；年龄按每年元旦自动递增。
- 日期选择器使用简体中文。
- `main.py` 仍只承担路由、控制器装配和运行时基础职责，没有功能表单或直接 JSON 持久化。

## 远端发布注意事项

- GitHub `main` 在本阶段收尾时由用户授权快进合并。
- GitHub Release `v1.2.3` 使用单一 `carbs_king.apk`，目标为 Build 77。
- 远端资产必须为 201,554,835 字节，SHA-256 必须与本地 Build 77 一致。
- 应用优先读取 GitHub Releases API；API 返回 403、网络错误、超时或无效 JSON 时，自动读取 `main/update_manifest.json`。
- Build 76 用户需要手动覆盖安装 Build 77 一次；从 Build 77 开始才具备备用更新源能力。
- Release URL：`https://github.com/fivespeedbuck/carbs-king/releases/tag/v1.2.3`

## 下一阶段

- 在 iQOO 11S 手动覆盖安装 Build 77，确认数据保留；以后再用应用内更新入口验证 API 403 时的备用清单路径。
