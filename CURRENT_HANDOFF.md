# 当前交接：Build 111 已发布

更新时间：2026-08-11

> [!warning] 当前最高优先级
> Build 111 已由用户完成本批 UI 验收并发布。没有用户针对具体 BUG 的明确授权，禁止修改任何源码模块；获准后也只能修改与该 BUG 直接相关的最小文件集合。
>
> 模型唯一规范仍绑定 SHA-256 `790ABE73F2B34F48FD9B2DFAF938F685A1D4242DA161CA6350AB1CE0B4C3D16B`。

## 当前会话优先事实（高于下方历史 Build 101 记录）

- 正式发布为 `1.2.3 / Build 111`；V2304A 已无线覆盖安装，系统确认 `versionCode=111`、`versionName=1.2.3`。
- APK：`build/apk/carbs_king.apk`，201,898,707 bytes，SHA-256 `06497F6AB208A49493A368E3057855B6CDB82657FE8B60A72B924CF79B03ED1F`；包名、v2 签名、1326 GIF、1326 JPG、2 MP3 和原生提醒门禁通过。
- 本批完成：搜索与新增控件对齐、动作主部位栏可读、动作参数窄屏显示、食物计量口径全宽/只读展示、常用食物流式标签及长名处理。
- 完整自动化 `561 passed, 448 subtests passed`；源码版本已预备为 Build 112。未处理新需求前，不再构建或修改。

## 历史 Build 101 基线说明

下方内容是 Build 101 冻结基线与早期候选证据；它不覆盖上述当前状态。

## 当前结论

- 正式发布线为 `1.2.3 / Build 101`；APK 已在 iQOO 11S 覆盖安装，发布资产与更新清单使用同一 SHA-256。
- 全量回归为 `542 passed, 448 subtests passed`；编译、差异格式、APK 资源、原生提醒、版本和 v2 签名门禁通过。
- Build 101 APK：`201,914,395` 字节；SHA-256 `8BC9DE0B9489288D2F8B630D7FD3E1289BE272018E6BA2A4C42C1A0167B59DE9`。
- 全模块冻结规则见 `FROZEN_BASELINE.md` 和 `docs/BUILD101_FINAL_SUMMARY_2026-08-04.md`。

## 历史候选状态

- 公开正式版仍为 `1.2.3 / Build 89`。
- `1.2.3 / Build 96` 本地候选已完成构建、自动化验证、资源门禁、运行时门禁、哈希、包名、版本和签名连续性核验。
- Build 94 已安装到 iQOO 11S；Build 96 尚未安装，因此不得创建 GitHub Release。
- 动态碳循环模型适合当前唯一用户进入个人长期测试；公开多用户发布仍为 `HOLD`。
- 源码版本已预备为下一次 Build 97；旧候选文件均保留，禁止覆盖。
- 当前全量回归为 `538 passed, 448 subtests passed`；独立差分审计 `5686` 案例和封闭代码审计均 `OPEN P0=0`。

## Build 96 候选

- APK：`release_candidates/carbs-king-v1.2.3-build96-candidate.apk`
- 大小：201,904,219 字节
- SHA-256：`967609BF409D8E0ECFA8CF5BD3626376E9FACE87B55B5D87E2FCE4D94960793B`
- 包名 / 版本：`com.chenyang.carbs_king` / `1.2.3 (96)`
- 签名：v2；证书 SHA-256 `172A8B5C7A909A79FB483F83CF9FEA71FE6567937C900C1D47EAF0FD67AD75CE`，与 Build 95 一致
- 资源：1,326 GIF、1,326 JPG、2 MP3；原生提醒门禁通过
- 状态：本地候选；待 iQOO 11S 真机；未发布

## Build 95 候选

- APK：`release_candidates/carbs-king-v1.2.3-build95-candidate.apk`
- 大小：201,900,795 字节
- SHA-256：`424E75EE172B0325D86C79D1CF18C61553B728F74B6F3539F61FD63A0F1DCA89`
- 包名：`com.chenyang.carbs_king`
- versionName：`1.2.3`
- versionCode：`95`
- 签名：v2；证书 SHA-256 `172A8B5C7A909A79FB483F83CF9FEA71FE6567937C900C1D47EAF0FD67AD75CE`，与 Build 94 一致
- 资源：1,326 GIF、1,326 JPG、2 MP3；ZIP 对齐和原生提醒门禁通过
- 状态：本地候选；未安装、未发布

## Build 94 候选

- APK：`release_candidates/carbs-king-v1.2.3-build94-candidate.apk`
- 大小：201,894,067 字节
- SHA-256：`0AA5F5A5E621EE9E148DEDFA28014BE73647FEC4EE4CCBBA28ACA031B4BC5845`
- 包名：`com.chenyang.carbs_king`
- versionName：`1.2.3`
- versionCode：`94`
- 签名：v2；证书 SHA-256 `172A8B5C7A909A79FB483F83CF9FEA71FE6567937C900C1D47EAF0FD67AD75CE`，与 Build 93 一致
- 资源：1,326 GIF、1,326 JPG、2 MP3；原生提醒门禁通过
- 状态：本地候选；未安装、未发布

## 本轮完成

- 动态碳循环采用唯一引擎和版本化快照；自定义宏量模式完全绕过自动模型。
- 抗阻、有氧和混合训练分别分类，不再使用部位乘数或统一负荷总分。
- 模型完成文献化说明、100 天回放、18 个边界用例、96 画像全年压力回放和真实备份回放。
- 训练参数历史预填、一键确认、确认后碳档提示、长按排序、训练结束 5 点评分已接入。
- 今日和饮食页使用 kcal、碳水、蛋白质、脂肪四条进度；无用摄入详情已删除。
- 修复去脂体重 `None`、三档结果异常相同、训练日普遍误判高碳、数据页横向选择跳回开头等问题。
- 新增食物支持 kcal/kJ 选择并统一保存为 kcal；食物导入导出只包含用户差分。
- 全量测试：V3.3-final `530 项通过，448 个子测试通过`。

## 真机验收清单

1. 用户授权后安装 Build 94，确认可覆盖 Build 89 且数据迁移正常。
2. 验证休息、训练待确认、参数确认后碳档变化和自定义宏量旁路。
3. 验证历史参数、一键确认、普通滑动/长按排序、训练中追加动作和结束评分。
4. 验证四条进度、kcal/kJ 新增食物、数据页横向选择不跳回开头。
5. 导出一份测试后备份，作为后续真实长期回放起点。

## 项目边界

- 31/60/90 天长期能量校准继续 shadow，不自动应用。
- 训练评分只采集，不直接改变碳档或自动建议休息。
- 根目录 `gif/` 是用户素材，不删除、不提交、不进入 APK。
- Build 91 和 Build 92 为作废内部产物；不得用于测试或发布。
