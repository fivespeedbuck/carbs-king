# Build 96 候选交付摘要

日期：2026-08-04

## 结果

- 候选 APK：`D:\carbs-king\release_candidates\carbs-king-v1.2.3-build96-candidate.apk`
- 大小：201,904,219 字节
- SHA-256：`967609BF409D8E0ECFA8CF5BD3626376E9FACE87B55B5D87E2FCE4D94960793B`
- 包名：`com.chenyang.carbs_king`
- versionName / versionCode：`1.2.3 / 96`
- 签名：APK Signature Scheme v2；证书 SHA-256 `172A8B5C7A909A79FB483F83CF9FEA71FE6567937C900C1D47EAF0FD67AD75CE`，与 Build 95 连续
- 资源：1,326 GIF、1,326 JPG、2 MP3；源目录、镜像和 APK 内层资源门禁通过
- 自动化：`538 passed + 448 subtests`；`compileall` 与 `git diff --check` 通过

## 修复范围

1. 数据页固定选择栏恢复整行等宽，并退出异步滚动恢复，避免下方详情操作带动上方分类闪动。
2. 自重重量框显示完整“自重”，记录模式下补充灰色说明，不改变现有输入和保存行为。
3. 动作全部确认后训练主卡显示当前碳档；待确认时仍显示确认提示。
4. 目标按钮改为临时预览，显示三档 kcal、宏量克数和倍率；只有明确应用并二次确认才更新未来阶段。

## 边界

- V3.3 冻结算法、参数、证据版本和唯一规范未修改。
- 历史快照不倒改；目标预览不保存、不清空当前阶段。
- 本文件记录本地候选，不代表已安装、真机通过或已发布。
