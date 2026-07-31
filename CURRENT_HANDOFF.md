# 当前交接：2026-07-31 Build 81 组合成员卡紧凑间距

## 当前状态

- 正式目录：`D:\carbs-king`
- 源码 PR：[#11](https://github.com/fivespeedbuck/carbs-king/pull/11) 已合并到 `main`（merge commit `b1fa945`）。
- Build 81 已完成全量测试、APK 资源门禁、原生提醒运行时门禁、包名、版本和 v2 签名检查。
- GitHub `v1.2.3` Release 已替换为 Build 81，远端只保留单一 `carbs_king.apk`，size/digest 已核对一致。
- `pyproject.toml` 与 `src/app_version.py` 已预备下一次 Build 82。

## 最终 APK

- 文件：`build/apk/carbs_king.apk`
- 包名：`com.chenyang.carbs_king`
- versionName：`1.2.3`
- versionCode：`81`
- 大小：`201,668,435` 字节
- SHA-256：`0D385C6B6C36BD926E5235D2FF9F1308D81C343CCCC2D17C0F8E3626B0D1923D`
- APK v2 签名有效；证书 SHA-256：`172A8B5C7A909A79FB483F83CF9FEA71FE6567937C900C1D47EAF0FD67AD75CE`。

## 本次结果

- 超级组/复合组成员卡保留标题、部位·组数、重量×次数和训练中完成组数；训练前高度从 112 收紧为 88，训练中从 126 收紧为 104。
- 成员内框、卡片间距、拖动与编辑操作均保留，底部空白不再显著大于内容行距。
- Build 80 的前台组间声音修复保持不变；用户已确认切回前台后声音恢复正常，后台声音不再继续迭代。

## 验证基线

- 全量测试：446 passed，441 subtests passed。
- APK 内层资源：1324 GIF、1324 JPG、2 MP3、1 WAV。
- 原生提醒门禁：`RestAlarmReceiver`、插件类、通知/精确闹钟权限、v3 渠道、`raw/rest_coin` 和 R8 可达性均通过。

## 远端发布结果

- `main/update_manifest.json` 已公开 Build 81、`201,668,435` 字节和本文件 SHA-256。
- `v1.2.3` Release 只保留一个 `carbs_king.apk`，状态为 `uploaded`。
- 远端 digest 为 `sha256:0d385c6b6c36bd926e5235d2ff9f1308d81c343cccc2d17c0f8e3626b0d1923d`。
