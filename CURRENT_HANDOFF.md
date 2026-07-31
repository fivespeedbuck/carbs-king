# 当前交接：2026-07-31 Build 80 原生组间声音与组合卡片

## 当前状态

- 正式目录：`D:\carbs-king`
- 发布分支：`codex/build80-rest-audio-group-cards`
- Build 80 已完成全量测试、Kotlin 编译、APK 资源门禁、原生提醒运行时门禁、包名、版本、v2 签名和 ZIP 对齐检查。
- `pyproject.toml` 与 `src/app_version.py` 已预备下一次 Build 81。

## 最终 APK

- 文件：`build/apk/carbs_king.apk`
- 包名：`com.chenyang.carbs_king`
- versionName：`1.2.3`
- versionCode：`80`
- 大小：`201,668,355` 字节
- SHA-256：`7590EEE32CFA94EE8595C45A872DE3397FC0751261887B39F44BFA7588C82644`
- APK v2 签名有效；证书 SHA-256：`172A8B5C7A909A79FB483F83CF9FEA71FE6567937C900C1D47EAF0FD67AD75CE`。

## 本次结果

- Flet Android 生命周期枚举恢复前台的状态已被正确识别，切后台再返回后，应用内后续组间声音不会继续被错误屏蔽。
- 到点声音由 Android 原生 Receiver 直接播放内置 `raw/rest_coin`，不依赖 Flet/Python 进程在后台继续存活，也不把通知权限视为播放声音的前提。
- 原生直接播放成功时不经 v3 声音渠道重复通知；只有原生播放启动失败时才使用通知渠道有声兜底。
- 超级组与复合组成员卡固定为四行：动作名、部位·组数、重量×次数、训练前留白/训练中完成组数，并增加内框、底部空间和成员间距。

## 验证基线

- 全量测试：446 passed，441 subtests passed。
- Kotlin：`:carbs_king_rest_alarm:compileReleaseKotlin` 通过。
- APK 内层资源：1324 GIF、1324 JPG、2 MP3、1 WAV。
- 原生提醒门禁：`RestAlarmReceiver`、插件类、`POST_NOTIFICATIONS`、`USE_EXACT_ALARM`、v3 渠道、`raw/rest_coin` 和 R8 可达性均通过。

## 真机验收顺序

1. 覆盖安装 Build 80。
2. 连续验证四次休息：第一轮前台、第二轮后台、第三和第四轮回到前台。
3. 再分别验证锁屏、暂停、加减时间和跳过。
4. 检查训练前和训练中的超级组/复合组四行成员卡、内框与底部留白。

## 发布门禁

- `main/update_manifest.json` 必须为 Build 80、`201,668,355` 字节和本文件 SHA-256。
- `v1.2.3` Release 只保留一个 `carbs_king.apk`，远端状态、大小和 digest 必须与本地一致。
