# 下一次 Codex 会话交接提示

将下列内容完整复制到新的 Codex 会话：

```text
请接手 D:\carbs-king 项目。默认使用中文；先不要写代码，按以下顺序阅读并汇报当前状态：

1. 全局协作规则：
- C:\Users\chenyanggggg\.codex\memories\PROFILE.md
- C:\Users\chenyanggggg\.codex\memories\ACTIVE.md

2. 项目入口与结构：
- D:\carbs-king\README.md
- D:\carbs-king\PROJECT_CONTEXT.md
- D:\carbs-king\docs\ARCHITECTURE.md
- D:\carbs-king\docs\CODE_INDEX.md

3. 当前交接与发布状态：
- D:\carbs-king\CURRENT_HANDOFF.md（Build 82）
- D:\carbs-king\CHANGELOG.md
- D:\carbs-king\docs\BUILD82_FINAL_SUMMARY_2026-08-01.md
- D:\carbs-king\PENDING_FEATURES.md
- D:\carbs-king\NEXT_SESSION_PROMPT.md

4. 只读核对：
- 在 D:\carbs-king 运行 git status -sb、git diff --check、git log -5 --oneline。
- 不要丢弃任何未提交文件；先报告文件名、用途和是否属于当前任务。

当前正式基线为 Build 82（v1.2.3）。源代码已自动预备到下一构建号 Build 83；不要擅自构建或发布 APK，除非我明确要求。

本轮已新增“站姿器械下夹胸”和“站姿器械侧平举”及其 180×180 JPG、GIF 素材；动作定义在 src/exercise_catalog_additions.json，媒体位于 assets/exercises/。根目录 gif/ 中的四张 PNG 是用户保留的原始帧，不属于发布包，也不要擅自删除。

当前首要待修问题：添加饮食弹窗中，输入框与下拉框在 iQOO 11S 真机上仍未视觉对齐。此前只改了 src/diet_controller.py 的控件高度设置，自动化测试通过但真机没有变化；不要再把该项称为已修复。下一版应先对照 Build 76 的实现与 Flet/Android 实际渲染层，定位是否由内部 TextField/Dropdown、标签容器或主题样式固定尺寸造成，再作最小修改，并以真机截图验收。

已提出但尚未实现的功能以 PENDING_FEATURES.md 为准：训练回收站、组间休息悬浮倒计时、切后台/锁屏到点可靠提醒、个人资料页体重体脂同步至数据趋势。

重要边界：此前 Kimi K3 未提交的悬浮窗、后台/锁屏提醒、回收站等尝试已清理；不要把它们当作已实现功能。Android 后台提醒必须分别说明代码存在、APK 合并、权限完成、iQOO 11S 前后台/锁屏真机验收四种状态，缺少最后一项不能称为可用。
```

## 下一会话首次回复参考

```text
我已完成交接核对：当前正式基线为 Build 82（v1.2.3），并已阅读代码索引、发布交接、待办清单和工作区状态。

“添加饮食”弹窗的输入框与下拉框对齐问题仍未解决：此前的高度设置改动没有改变 iQOO 11S 真机效果，因此会作为下一版的首要定位项，不会误报为已修复。

请把下一次遇到的痛点、复现步骤和截图发给我；我会先定位再给出最小修复与验收方式。
```
