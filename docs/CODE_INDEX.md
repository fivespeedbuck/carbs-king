# 碳水大王代码索引

本索引用于接管、定位回归和发布，不替代源码。默认从 `src/main.py` 的路由和控制器装配开始，再沿功能表查找控制器、视图和服务。

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
| 今日 | `src/today_controller.py` | `src/today_views.py`、`src/today_service.py` |
| 训练 | `src/training_controller.py` | `src/training_views.py`、`src/training_picker_views.py`、`src/training_plan_views.py`、`src/training_summary_views.py` |
| 饮食 | `src/diet_controller.py` | `src/diet_views.py`、`src/diet_service.py`、`src/food_library.py` |
| 数据 | `src/analytics_page.py` | `src/analytics_ui.py`、`src/analytics_trend_views.py`、`src/analytics_service.py` |
| 我 | `src/profile_controller.py` | `src/profile_views.py`、`src/profile_details_views.py`、`src/profile_theme_views.py`、`src/profile_update_views.py` |
| 恢复 | `src/recovery_controller.py` | `src/recovery_views.py`、`src/recovery_service.py` |

## 训练功能定位

- 动作模型与训练记录：`src/training_models.py`、`src/training_service.py`。
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
- 添加饮食、常用回填、空搜索结果与食物库编辑：`src/diet_controller.py`；Android 下拉菜单表面样式位于 `src/ui_components.py`。
- 营养计算：`src/app_utils.py`、`src/nutrition_service.py`。
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

## 发布入口

1. 在正式目录检查 `git status -sb`、`git diff --check` 和全量测试。
2. 用 `powershell -ExecutionPolicy Bypass -File .\build_apk_update.ps1` 构建；脚本会执行 LFS、根资源、镜像和 APK 内层资源门禁。
3. 用 `aapt dump badging` 检查包名/versionCode，用 `apksigner verify --print-certs` 检查签名。
4. 用 GitHub CLI 推送分支、创建 PR、合并 `main`；先确认公开 `update_manifest.json` 已随 `main` 生效，再替换 Release APK。
5. 上传大 APK 优先使用直连 `gh api --input`，上传后核对远端 state、size 和 digest。

## 预览注意事项

- Flet 0.85.3 本地 Web 预览不要使用 `--name`；命名页面的静态路径和 WebSocket 配置不一致，会表现为页面一直 `Working…`。
- 只在 `D:\carbs-king` 启动一个 8765 预览，使用 `.local-preview-data` 隔离数据；修改子模块后必须重启预览。
