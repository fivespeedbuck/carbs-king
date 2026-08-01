# 下一次 Codex 会话交接提示

将下列内容完整复制到新的 Codex 会话：

```text
请接手 D:\carbs-king 项目。默认使用中文；先不要写代码，按以下顺序阅读并汇报当前状态：

1. 全局记忆：C:\Users\chenyanggggg\.codex\memories\PROFILE.md、ACTIVE.md。
2. 项目入口：README.md、PROJECT_CONTEXT.md、docs/ARCHITECTURE.md、docs/CODE_INDEX.md。
3. 当前交接：CURRENT_HANDOFF.md（Build 88）、CHANGELOG.md、docs/BUILD88_FINAL_SUMMARY_2026-08-01.md、PENDING_FEATURES.md。
4. 只读运行 git status -sb、git diff --check、git log -5 --oneline；保留根目录 gif/ 原始素材，不得删除或提交。

当前正式发布为 1.2.3 / Build 88，源码已预备到 Build 89。Build 88 包含并已在 iQOO 11S 验证后台/锁屏/息屏休息提醒、悬浮倒计时、下一动作、主题色、点击返回和时间调整复用通知；还包含每动作默认 90 秒休息、15 天训练回收站，以及添加饮食下拉菜单不透明白色修复。饮食灰色浮层修复进入 APK 但仍要安装 Build 88 后真机确认。

下一阶段最核心升级是动态碳循环：不要直接开工，先阅读 PENDING_FEATURES.md 中的完整产品约束，再用低按钮密度的页面原型与用户确认。核心输入优先级为今日明确训练计划、用户手动选择、常用训练时段、近 7–28 天真实训练规律、无数据回退。目标使用范围而非强制吃满，建议只做可解锁的软稳定，不能让软件绑架用户。
```
