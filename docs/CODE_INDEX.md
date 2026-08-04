# 碳水大王代码索引

本索引用于接管、定位回归和发布，不替代源码。默认从 `src/main.py` 的路由和控制器装配开始，再沿功能表查找控制器、视图和服务。

Build 101 为全模块冻结基线。定位 BUG 时先查本索引和 `FROZEN_BASELINE.md`，只有用户明确授权的对应模块允许最小修改。数据页选择器位于 `src/analytics_page.py`、`src/analytics_ui.py`、`src/analytics_trend_views.py`；训练追加与评分位于 `src/training_controller.py`；后台提醒位于 `src/rest_notification.py` 和 Android 原生插件。

## 运行与基础层

| 领域 | 入口 | 关键职责 |
| --- | --- | --- |
| 应用启动 | `src/main.py` | Flet 启动、路由、状态装配、全局刷新与错误兜底 |
| 状态 | `src/app_state.py` | 当天状态、日期、页面视图和用户资料默认值 |
| 持久化 | `src/storage_service.py`、`src/repositories.py` | Flet 数据目录、JSON 仓库、备份与恢复 |
| 通用控件 | `src/ui_components.py` | 卡片、按钮、移动端字段、下拉框、响应式字段网格 |
| 表单壳 | `src/form_views.py` | 全屏表单顶栏、滚动内容和底部保存区 |

## 一级页面

| 页面 | 控制器 | 视图/服务 |
| --- | --- | --- |
| 今日 | `src/today_controller.py`、`src/daily_record_controller.py` | `src/today_views.py`、`src/nutrition_service.py` |
| 训练 | `src/training_controller.py` | `src/training_views.py`、`src/training_picker_views.py`、`src/training_plan_views.py`、`src/training_summary_views.py` |
| 饮食 | `src/diet_controller.py` | `src/diet_views.py`、`src/diet_service.py`、`src/food_library.py` |
| 数据 | `src/analytics_page.py` | `src/analytics_ui.py`、`src/analytics_trend_views.py`、`src/analytics_service.py` |
| 我 | `src/profile_controller.py` | `src/profile_views.py`、`src/profile_details_views.py`、`src/profile_theme_views.py`、`src/profile_update_views.py`、`src/profile_feature_views.py` |
| 恢复 | `src/recovery_controller.py` | 复用 `src/form_views.py`、`src/ui_components.py` 与日记录控制器；当前没有独立的恢复视图或服务文件。 |

## 训练功能定位

- 动作模型与训练记录：`src/training_models.py`、`src/training_service.py`。训练 schema v3 保存 `load_kind`、`parameters_confirmed` 和 `assistance_kg`，旧数据缺失时保持未知而不猜成自重。
- 动作目录加载、常用中文名、别名相关性和筛选放宽：`src/exercise_library.py`、`src/exercise_catalog_data.json`、`src/exercise_catalog_overrides.json`、`src/exercise_catalog_additions.json`。
- 上游动作导入与审计：`tools/assemble_exercise_catalog.py`、`tools/audit_exercise_catalog.py`。
- 训练前/训练中排序：`src/training_plan_views.py`、`src/training_controller.py`。
- 训练游标和顶部进度：`src/training_experience_service.py`、`src/training_views.py`。
- 休息、音频、悬浮窗和训练完成：`src/rest_notification.py`、`src/training_experience_service.py`、`src/training_controller.py`、`src/training_summary_views.py`、`android/rest_alarm_plugin/android/src/main/kotlin/com/chenyang/carbs_king/restalarm/RestOverlayService.kt`。
- 训练回收站：`src/training_recycle_service.py`、`src/profile_feature_views.py`、`src/profile_controller.py`、`src/daily_record_controller.py`。
- APK 原生提醒运行时门禁：`tools/apk_runtime_gate.py`、`tests/test_apk_runtime_gate.py`、`build_apk_update.ps1`。
- 应用内 APK 下载、校验与系统安装交接：`src/apk_update_download.py`、`src/profile_controller.py`、`src/profile_update_views.py`、`tests/test_apk_update_download.py`。

## 饮食与更新功能定位

- 食物搜索和目录：`src/food_library.py`。
- 添加饮食、常用回填、空搜索结果、底部向上白色选择面板与食物库编辑：`src/diet_controller.py`；其他页面的通用 Android 下拉样式位于 `src/ui_components.py`。
- “我”页体重/体脂保存同步当天趋势：`src/profile_controller.py` 调用 `src/analytics_service.py` 的明确测量合并逻辑，再由 `src/daily_record_controller.py` 写入当天记录。
- 动作选择卡 GIF、帮助/选择按钮与左侧部位栏：`src/training_picker_views.py`；动作浏览区宽度和分页布局：`src/training_controller.py`。
- 现行营养入口：`src/nutrition_service.py`。自动宏量模式调用动态碳循环，自定义宏量模式只读取用户倍率，不调用动态引擎。
- 动态碳循环：`src/dynamic_carb_engine.py` 负责确定性计算，`src/dynamic_carb_adapter.py` 负责 App 数据语义、快照持久化和 UI 投影，`src/carb_cycle_views.py` 负责首页与饮食页共用的简化详情。旧 `src/carb_cycle_service.py` 已删除。
- 动态碳循环回放：`tools/replay_dynamic_carb_fixture.py`（100 天 golden）、`tools/simulate_dynamic_carb_personas.py`（长期画像与 shadow 校准）、`tools/replay_dynamic_carb_edge_cases.py`（不可协商边界）；输出位于 `release_candidates/dynamic-carb-*.json`。
- V3.3 实现差分与封闭 P0 审计：`tools/verify_dynamic_carb_v33_implementation.py`、`tools/audit_dynamic_carb_v33_closed.py`；输出位于 `release_candidates/dynamic-carb-v33-*.json`。
- Release 版本检查：`src/app_version.py`、`src/update_service.py`、`src/profile_update_views.py`；GitHub API 不可用时读取根目录 `update_manifest.json`。
- 版本配置：`pyproject.toml`；构建后由 `build_apk_update.ps1` 同步预备下一 Build。

## 测试定位

| 主题 | 测试 |
| --- | --- |
| Build 76 回归、更新解析、构建契约 | `tests/test_build76_regressions.py` |
| 饮食表单、四字段对齐、常用回填 | `tests/test_diet_information_architecture.py` |
| 动作库目录、ID、中文覆盖、常用词排序与筛选放宽 | `tests/test_exercise_library.py` |
| 训练视图、组进度、操作区 | `tests/test_training_views.py`、`tests/test_training_set_highlight.py` |
| 动作管理和组合卡 | `tests/test_training_plan_views.py` |
| 通用 UI 契约 | `tests/test_ui_contracts.py` |
| 休息调度、原生通知与 APK 运行时门禁 | `tests/test_training_clock_service.py`、`tests/test_rest_notification.py`、`tests/test_apk_runtime_gate.py` |
| 个人资料、主题和测量 | `tests/test_profile_macro_and_measurements.py` |
| 训练回收站与恢复装配 | `tests/test_training_recycle_service.py`、`tests/test_daily_record_controller.py`、`tests/test_main_dependency_wiring.py` |
| 动态碳循环内核、长期校准、数据适配、快照、自动/自定义模式隔离和回放 | `tests/test_dynamic_carb_engine.py`、`tests/test_dynamic_carb_adapter.py`、`tests/test_nutrition_auto_macros.py` |

## 发布入口

1. 在正式目录检查 `git status -sb`、`git diff --check` 和全量测试。
2. 用 `powershell -ExecutionPolicy Bypass -File .\build_apk_update.ps1` 构建；脚本会执行 LFS、根资源、镜像和 APK 内层资源门禁。
3. 用 `aapt dump badging` 检查包名/versionCode，用 `apksigner verify --print-certs` 检查签名。
4. 用 GitHub CLI 推送分支、创建 PR、合并 `main`；先确认公开 `update_manifest.json` 已随 `main` 生效，再替换 Release APK。
5. 上传大 APK 优先使用直连 `gh api --input`，上传后核对远端 state、size 和 digest。

## 预览注意事项

- Flet 0.85.3 本地 Web 预览不要使用 `--name`；命名页面的静态路径和 WebSocket 配置不一致，会表现为页面一直 `Working…`。
- 只在 `D:\carbs-king` 启动一个 8765 预览，使用 `.local-preview-data` 隔离数据；修改子模块后必须重启预览。
