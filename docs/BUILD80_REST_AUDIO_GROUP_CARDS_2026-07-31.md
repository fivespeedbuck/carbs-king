# Build 80：原生组间提示音与组合动作卡片

## 修复内容

- 修正 Flet Android 生命周期枚举识别：从后台返回时，后续休息重新视为前台，应用内 `rest_coin` 可以继续播放。
- 已排程的 Android `AlarmManager` 在到点时由原生 Receiver 直接播放 APK 内置 MP3，不依赖 Flet/Python 在后台存活，也不再因通知权限不足而放弃声音。
- 原生直接播放成功时不再经已有声音的 v3 通知渠道再发一遍，避免双响；直接播放失败才回退到通知渠道。
- 超级组/复合组成员卡固定为动作名、部位·组数、重量×次数、留白或完成组数四行，增加成员卡高度、底部呼吸空间和内边框。

## 验证

- 全量测试：446 passed，441 subtests passed。
- Python 编译与 Git 差异格式检查通过。
- `:carbs_king_rest_alarm:compileReleaseKotlin` 通过。
- APK 包名 `com.chenyang.carbs_king`，versionName `1.2.3`，versionCode `80`。
- APK v2 签名、ZIP 对齐、资源门禁和原生提醒运行时门禁均通过。
- 内层资源：1324 GIF、1324 JPG、2 MP3、1 WAV；`RestAlarmReceiver`、插件类、精确闹钟权限与 `raw/rest_coin` 均已确认存在。

## APK

- 文件：`build/apk/carbs_king.apk`
- 大小：201,668,355 字节
- SHA-256：`7590EEE32CFA94EE8595C45A872DE3397FC0751261887B39F44BFA7588C82644`

## 真机验收

1. 覆盖安装 Build 80。
2. 连续完成至少四组休息：第一组前台，第二组后台，第三、四组切回前台。
3. 分别检查前台、后台和锁屏到点声音；暂停、加减时间、跳过后不应误响。
4. 在训练前和训练中打开超级组/复合组动作调整，确认四行卡片、底部留白和成员边框。
