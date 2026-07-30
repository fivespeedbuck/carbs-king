# 下一会话交接：Build 76 训练进度、组合卡间距与饮食输入框

更新时间：2026-07-30
正式目录：`D:\carbs-king`
当前分支：`codex/build76-device-fixes`
状态：工作树包含本轮真实修改，尚未提交、推送、合并、构建新 APK 或上传 GitHub Release。

## 一、新会话开始前必须完整读取

先完整读取两个全局记忆文件：

1. `C:\Users\chenyanggggg\.codex\memories\PROFILE.md`
2. `C:\Users\chenyanggggg\.codex\memories\ACTIVE.md`

随后完整读取 `D:\carbs-king` 中现有的全部工程 Markdown 文件。不得只读最新交接或按需抽取：

1. `D:\carbs-king\NEXT_SESSION_HANDOFF_BUILD76_2026-07-30.md`（本文）
2. `D:\carbs-king\NEXT_SESSION_HANDOFF_BUILD76_2026-07-29.md`
3. `D:\carbs-king\NEXT_SESSION_HANDOFF_2026-07-29.md`
4. `D:\carbs-king\PROJECT_CONTEXT.md`
5. `D:\carbs-king\CURRENT_HANDOFF.md`
6. `D:\carbs-king\PROJECT_MANAGER_BRIEF.md`
7. `D:\carbs-king\GOAL_CHALLENGES_BRIEF.md`
8. `D:\carbs-king\STAGE_RETROSPECTIVE_2026-07-29.md`
9. `D:\carbs-king\README.md`
10. `D:\carbs-king\CHANGELOG.md`
11. `D:\carbs-king\GITHUB_新手上传指南.md`
12. `D:\carbs-king\docs\ARCHITECTURE.md`
13. `D:\carbs-king\docs\REFACTOR_BASELINE.md`
14. `D:\carbs-king\docs\agent-notes\build-release.md`
15. `D:\carbs-king\docs\agent-notes\delivery-directory-policy.md`
16. `D:\carbs-king\docs\agent-notes\development.md`
17. `D:\carbs-king\docs\agent-notes\testing.md`
18. `D:\carbs-king\docs\agent-notes\ui.md`
19. `D:\carbs-king\docs\retrospectives\2026-07-28-goal-challenges-delivery.md`
20. `D:\carbs-king\release_candidates\v62-pr-body.md`
21. `D:\carbs-king\release_candidates\v62-release-notes.md`

如果新会话启动时又发现新的 `.md` 文件，也必须一并完整读取。可以先用下面的命令核对清单：

```powershell
rg --files -g "*.md" -g "!build/**" -g "!.git/**" | Sort-Object
```

只使用 `D:\carbs-king` 正式目录。禁止 reset、checkout、批量还原、覆盖当前工作树或创建 worktree。

## 二、当前必须优先修复的运行时错误

当前正式预览为 `http://127.0.0.1:8765/`。

点击训练页的“调整训练顺序”会出现：

```text
The application encountered an error:
isinstance() arg 2 must be a type, a tuple of types, or a union
```

错误由 `src/training_plan_views.py` 最新增加的外层卡片间距处理触发，重点检查：

```python
if isinstance(block_card, ft.Container):
```

当前 Flet 运行环境里 `ft.Container` 不能可靠作为 `isinstance()` 的第二个参数。

新会话应先恢复动作管理页可正常打开：

- 最保守方案是删除最新的外层卡片 `margin` 循环，并把外层列表恢复为原来的稳定实现。
- 保留组内成员卡自身产生间距的方案，再从真实页面验证。
- 修复后必须重启 8765 正式预览；只刷新浏览器不足以加载子模块修改。

## 三、本轮新增的训练顶部进度修复

用户场景：

- 第 1、2 组没有训练；
- 直接选择并完成第 3 组；
- 完成后当前游标来到第 4 组；
- 顶部进度正确结果应为：灰、灰、绿、金。

已实现：

- `src/training_views.py`
  - `ActiveTrainingModel` 增加 `work_completed`。
  - `_segmented_progress()` 改为逐格着色。
  - 当前项为金色 `#FFD166`。
  - 真实完成项为绿色 `#21A366`。
  - 未完成项为灰色 `#31413C`。
  - 未传 `work_completed` 时保留旧比例兼容行为。
- `src/training_controller.py`
  - 增加 `training_completion_sequence()`。
  - 按 `training_cursor_sequence()` 的真实动作/组顺序生成完成标记。
- 已增加视图与运行时回归测试。

专项测试已证明 `(False, False, True, False)` 会生成“灰、灰、绿、金”，但尚未由用户完成最终真机确认。

## 四、组合卡当前状态

用户已经确认生效：

- 每个超级组/复合组成员右侧已经出现红色“移出组合”按钮。
- 每个成员仍有移动与编辑按钮。
- 三个以上成员时只移出所选动作。
- 两个成员时移出一个会自动解散组合，动作全部保留。

仍未收口：

- 用户确认组内成员卡之间没有可见间隙。
- `ReorderableListView.spacing=8` 在真实 Flet Web 页面中没有画出视觉间隙。
- 最新代码已尝试让成员卡自身产生 8 像素间距：
  - 普通成员卡可见高度 66，项目步长 74；
  - 带已完成信息的成员卡可见高度 80，项目步长 88；
  - 成员列表 `spacing=0`；
  - 列表高度减去最后一个尾部间隔，避免底部再次出现大块空白。
- 上述组内方案的专项测试通过，但因随后外层卡片间距代码触发运行时错误，尚未完成真实页面验收。
- 组合大卡底部空白、组合卡与普通动作卡之间的距离也需要在恢复页面后重新检查。

## 五、添加饮食四个框

用户真实截图显示：

- “餐次”和“食物”两个下拉框实际可见高度约为 60。
- “数量”和“搜索食物”两个文字输入框实际可见高度约为 48。
- 相差约 12 像素，同一行左右底边无法对齐。

之前的 `INPUT_FIELD_HEIGHT + 8` 补偿仍然不足。

最新代码已改为：

```python
text_input_height = INPUT_FIELD_HEIGHT + 20
```

目标：

- 餐次、食物两个下拉框等高。
- 数量、搜索食物两个文字框等高。
- 同一行左右输入边框顶部与底部完全对齐。
- 食物下拉菜单继续使用 `menu_height = 300`，避免菜单顶到页面顶部。

这版尚未经过重启后的真实页面确认，不能向用户声称已经修好。

## 六、本轮之前已经落盘的重要功能

### 训练结果与组合显示

- 每组按照实际重量、次数和单组容量单独统计。
- “今日已训练”显示超级组/复合组关系。
- 完整训练和未完整训练总结页显示组合关系。
- 训练完成卡主题色跟随用户主题。

### 训练前与训练中动作管理

- 训练前动作安排和训练中调整动作顺序共用组合卡组件。
- 普通动作按钮布局为：上排编辑、加号；下排移动、删除。
- 组合大卡只能从标题区域或顶部移动按钮拖动。
- 组合成员支持长按/移动按钮拖动、编辑、移出组合。
- 保存组合后留在动作管理页并即时刷新。
- 添加动作后留在动作管理页。
- 只有点击动作管理底部“完成”才返回训练或休息页面。

### 训练页与休息页

- 超级组动作卡已替代多余的普通动作标题格。
- 组合成员名字、组内位置和动作摘要问号已加入训练页。
- “下一个训练项”卡已经恢复。
- 休息页加入“调整训练顺序”。
- 从休息页完成调整时：倒计时未结束返回休息页，已结束返回训练页。
- 休息按钮底色和间距已向训练卡统一。
- 自重重量编辑允许留空，空值保存为 `0.0`，不再报“重量不能为空”。

### 其他 Build 76 修改

- 动作库部位栏收窄，“核心稳定”简化为“核心”。
- 常用器械横向排列，更多器械只在点击后展开。
- 移除热门/最近按钮，保留默认排序逻辑。
- 修复添加动作时 `set_input_focused` 未定义错误。
- 修复动作摘要提示入口。
- 功能设置卡和训练完成卡跟随主题换色。
- 今日页哑铃和奖杯图标已调整。
- 体重、体脂、围度等六个数据按钮恢复为一排六个。
- 饮食汇总改为单行整数显示。
- GitHub Release 更新检查入口已实现，但尚未做完整真机更新验证。

## 七、最近测试结果

最新一轮专项曾通过：

- `test_training_plan_views.py`：15 项
- `test_diet_information_architecture.py`：25 项
- `test_training_views.py`：18 项
- `test_ui_contracts.py`：57 项

合计 115 项通过。

之后又单独重跑 `test_training_plan_views.py`，15 项通过。

但是测试没有捕获真实 Flet 环境中的 `isinstance()` 运行时错误，因此当前代码不能视为可交付。

更早一次全量为 419 项测试、425 个子测试通过。最新修改后尚未重新跑全量。

## 八、新会话执行顺序

1. 完整读取第一节列出的全部文件。
2. 检查：
   - `git branch --show-current`
   - `git status --short`
   - 当前完整 diff
   - `git diff --check`
3. 先修复动作管理页的 `isinstance()` 运行时错误。
4. 运行 `test_training_plan_views.py` 和相关运行时测试。
5. 停止旧预览和对应 Python 子进程，只从 `D:\carbs-king` 启动一个 8765 手机宽度预览。
6. 实际点击验证动作管理页：
   - 页面不报错；
   - 红色断开按钮可见；
   - 组内成员之间有适度间隙；
   - 组合卡底部没有大块空白；
   - 组合卡和普通动作卡之间有正常距离。
7. 实际打开添加饮食页，核对四个框的可见顶部、底部和高度。
8. 验证跳过第 1、2 组并完成第 3 组后的顶部进度位置。
9. 重跑本轮所有专项、全量测试、全部 Python `py_compile` 和 `git diff --check`。
10. 用户确认预览前不要构建 APK。
11. 未经用户明确授权，不提交、推送、合并或替换 GitHub Release。

## 九、当前交付限制

- 暂不上传 GitHub Release。
- 暂不推送或合并 `main`。
- 暂不替换远端 APK。
- Build 76 最终构建仍必须使用 `build_apk_update.ps1`，并逐文件验证 APK 内层 `assets/flutter_assets/app/app.zip` 中的 GIF、JPG、MP3 和 WAV 资源。
- Windows 沙箱、权限或进程连接错误必须与代码失败分开判断。
