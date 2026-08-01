# 下一次 Codex 会话交接提示

将下列内容完整复制到新的 Codex 会话：

```text
请接手 D:\carbs-king 项目。默认使用中文；先不要写代码，按以下顺序阅读并汇报当前状态：

1. 全局 Obsidian 入口（通常已由全局 AGENTS.md 自动要求，但仍须实际遵循）：
- D:\obsidian\obsidian\00-入口\启动记忆.md
- D:\obsidian\obsidian\01-用户\用户画像.md
- D:\obsidian\obsidian\02-项目\项目索引.md
- D:\obsidian\obsidian\00-入口\读取路由.md

2. 碳水大王 Obsidian 项目入口：
- D:\obsidian\obsidian\02-项目\碳水大王\功能地图-源码核验.md
- D:\obsidian\obsidian\02-项目\碳水大王\当前状态.md
- D:\obsidian\obsidian\02-项目\碳水大王\下一阶段规划.md
- D:\obsidian\obsidian\02-项目\碳水大王\代码索引.md

3. 仓库入口：README.md、PROJECT_CONTEXT.md、docs/ARCHITECTURE.md、docs/CODE_INDEX.md。
4. 当前交接：CURRENT_HANDOFF.md（Build 89）、CHANGELOG.md、docs/BUILD89_FINAL_SUMMARY_2026-08-01.md、PENDING_FEATURES.md。
5. 只读运行 git status -sb、git diff --check、git log -5 --oneline；保留根目录 gif/ 原始素材，不得删除或提交。

当前正式发布为 1.2.3 / Build 89，源码预备到 Build 90。Build 89 把添加饮食的原生透明下拉替换为底部向上展开的应用内白色选择面板；动作筛选和卡片扩展到搜索框右边界，动作卡加入 GIF 预览；“我”页体重/体脂编辑同步为当天趋势测量。458 项测试和 441 个子测试、APK 门禁及 iQOO 11S 真机验收通过。Build 90 仅用于高级动态碳循环。

下一阶段最核心升级是动态碳循环：不要直接开工，先阅读 PENDING_FEATURES.md 中的完整产品约束，再用低按钮密度的页面原型与用户确认。核心输入优先级为今日明确训练计划、用户手动选择、常用训练时段、近 7–28 天真实训练规律、无数据回退。目标使用范围而非强制吃满，建议只做可解锁的软稳定，不能让软件绑架用户。
```
