# 当前状态：V3.4 Build 115 已正式发布（2026-08-25）

更新时间：2026-08-11

> [!warning] 当前最高优先级
> V3.4 已按用户明确授权完成代码、回归、打包和正式发布。Build 115 是当前公开版本；源码已预备下一 Build 116。Build 115 修复动作选择双触发与组间休息提醒双响。
>
> V3.4 模型规范绑定 SHA-256 `8C680ABD0F34EC73C1D4B21D96D3345A4DD480B6B73491638F76EC9A1A3E79B4`；V3.3 历史快照保持不可变。

## 当前会话优先事实（高于下方历史 Build 101 记录）

- 正式版：`1.2.3 / Build 115` 已完成 APK 构建与 GitHub Release 更新；包名 `com.chenyang.carbs_king`，versionCode `115`。
- Build 115 APK：`build/apk/carbs_king.apk`，201,848,183 bytes，SHA-256 `D6A36090317A780DC6E70AA787FFE02D8BA916FE8344B42B0BB034D264B1ED37`；v2 签名证书 SHA-256 `172A8B5C7A909A79FB483F83CF9FEA71FE6567937C900C1D47EAF0FD67AD75CE`。
- V3.4：减脂=Wiki 四练、保持=4.5 练插值、控制增肌=Wiki 五练；男女分支；`2高+2中+3低`；体脂不参与宏量；腿/臀/背高、胸/肩中、手臂/核心低；不改 UI，不回写旧 V3.3 展示快照。
- 验证：专项 `5 passed + 6 subtests`；相关回归 `108 passed + 28 subtests`；全量 `566 passed + 454 subtests`；真实备份 14 天只读回放零违规；编译与差异检查通过。
- 构建资源：1326 GIF、1326 JPG、2 MP3，根资源与内嵌资源一致；原生提醒运行时门禁通过。构建脚本已把源码预备为 Build 116。
- GitHub：Build 115 的主页资料、Release 清单和 APK 已同步；Build 114 保留为本地测试历史。
- 本批修复：动作选择同动作 350ms 去抖；前台／原生休息提醒共享送达标记，原生先认领后播放；UI 未改版。
- 本批完成：搜索与新增控件对齐、动作主部位栏可读、动作参数窄屏显示、食物计量口径全宽/只读展示、常用食物流式标签及长名处理。
- 完整自动化 `567 passed, 454 subtests passed`；源码版本已预备为 Build 116。除用户明确授权的缺陷外，不再修改已发布模块。

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
