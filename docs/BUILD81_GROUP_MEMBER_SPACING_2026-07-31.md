# Build 81：组合成员卡紧凑间距

## 变更

- 训练前超级组/复合组内部成员卡由 112 收紧至 88。
- 训练中成员卡由 126 收紧至 104，保留“已完成 N 组”行。
- 保留成员卡内框、三/四行信息、拖动操作和成员之间的固定间距。

## 验证

- 全量测试：446 passed，441 subtests passed。
- Python 编译与 Git 差异格式检查通过。
- APK 资源门禁和原生提醒运行时门禁通过。
- 包名 `com.chenyang.carbs_king`，versionCode `81`，v2 签名证书连续。

## APK

- 文件：`build/apk/carbs_king.apk`
- 大小：201,668,435 字节
- SHA-256：`0D385C6B6C36BD926E5235D2FF9F1308D81C343CCCC2D17C0F8E3626B0D1923D`

## GitHub 发布结果

- 源码 PR [#11](https://github.com/fivespeedbuck/carbs-king/pull/11) 已合并到 `main`。
- `v1.2.3` Release 已更新为 Build 81，仅保留 `carbs_king.apk`。
- 远端资产状态为 `uploaded`，大小 `201,668,435` 字节，digest 为 `sha256:0d385c6b6c36bd926e5235d2ff9f1308d81c343cccc2d17c0f8e3626b0d1923d`。
