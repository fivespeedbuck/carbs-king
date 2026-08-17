# Build 113 正式发布总结（2026-08-17）

## 发布内容

- 正式发布 V3.4 Wiki 个人微周期：减脂四练、保持四练与五练逐项 50% 插值、控制增肌五练；支持男女。
- 每周碳水分配固定为 `2 高 + 2 中 + 3 低`，公式为 `高=A+0.5、中=A、低=A−1/3`；体脂不参与 V3.4 宏量计算。
- 常规力量训练按主训练部位判档：腿／臀／背高，胸／肩中，手臂／核心低；明确双练或高强度／长有氧可升级。
- V3.3 历史展示快照不可变；当前及未来自动阶段签发 V3.4。
- 数据页月历图例更正为“主题色=选中”，与紫／蓝／绿／黄主题一致；不改 UI 交互。

## 验证与产物

- 全量测试：`566 passed, 454 subtests passed`。
- `python -m compileall -q src tests tools` 与 `git diff --check` 通过。
- 包名：`com.chenyang.carbs_king`；`versionCode=113`；`versionName=1.2.3`。
- APK：`build/apk/carbs_king.apk`，`201,902,635` bytes，SHA-256 `42724D5BA29840D16DCB5CFDE5BADE034584C684A08EE1D8FB86602A00E831E7`。
- v2 签名证书 SHA-256：`172A8B5C7A909A79FB483F83CF9FEA71FE6567937C900C1D47EAF0FD67AD75CE`。
- 资源门禁：1326 GIF、1326 JPG、2 MP3；原生后台提醒门禁通过。
- 已无线覆盖安装 V2304A；系统确认 `versionCode=113`、`versionName=1.2.3`。
- GitHub 首页补充真机截图：今日、训练计划、训练中、动作选择、饮食、数据、月历、个人资料与备份（用户已授权公开真实使用数据）。

## 发布后

- GitHub 默认分支、README、`update_manifest.json` 与 `v1.2.3` Release 同步为 Build 113。
- 构建脚本已将源码版本预备为 Build 114。
