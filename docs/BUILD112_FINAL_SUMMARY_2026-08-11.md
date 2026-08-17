# Build 112 V3.4 本地测试交付（2026-08-11）

## 交付结论

- 完成 V3.4 Wiki 个人微周期动态碳循环，不修改 UI。
- 减脂使用 Wiki 四练参数；保持使用四练和五练逐项 50% 插值；控制增肌使用 Wiki 五练参数；支持男女。
- 三目标统一使用 `高=A+0.5、中=A、低=A−1/3`，参考周期为 `2 高 + 2 中 + 3 低`；蛋白质和脂肪在同目标三档固定，体脂不参与 V3.4 宏量计算。
- 普通力量训练按主部位判档：腿／臀／背高碳，胸／肩中碳，手臂／核心低碳；组数不改变同一部位档位。双练和明确高强度／长有氧仍可升级。
- V3.3 历史展示快照保持不可变；当前日旧 V3.3 阶段会签发新的 V3.4 阶段。

## 验证证据

- V3.4 专项：`5 passed, 6 subtests passed`。
- 相关回归：`108 passed, 28 subtests passed`。
- 全量回归：`566 passed, 454 subtests passed`。
- `python -m compileall -q src tests tools` 与 `git diff --check` 通过。
- 用户真实备份 14 天只读回放零违规；未复制备份或隐私明细到仓库/Obsidian。

## APK 与真机

- APK：`D:\carbs-king\build\apk\carbs_king.apk`
- 大小：`201,902,579` 字节
- SHA-256：`65C59624A5754BCA048BFD075BC88EC5458E23A5C8BD83D5453D4540DC2A87E6`
- 包名／版本：`com.chenyang.carbs_king` / `1.2.3 (112)`
- 签名：APK Signature Scheme v2；证书 SHA-256 `172A8B5C7A909A79FB483F83CF9FEA71FE6567937C900C1D47EAF0FD67AD75CE`
- 资源：1326 GIF、1326 JPG、2 MP3；原生提醒门禁通过。
- V2304A 无线覆盖安装成功；`dumpsys` 确认 `versionCode=112`、`versionName=1.2.3`、`lastUpdateTime=2026-08-11 22:29:55`。
- 构建脚本已将源码预备为 Build 113。

## 发布边界

- Build 112 是本地测试包，未提交、未推送、未建 PR、未更新 GitHub Release。
- 公开正式版仍为 Build 111。
