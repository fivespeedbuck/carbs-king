# Build 82：固定轨迹器械动作与饮食表单待验证调整

## 发布内容

- 新增“站姿器械下夹胸”和“站姿器械侧平举”两条固定轨迹器械动作。
- 两条动作均提供搜索别名、训练提示、180×180 JPG 和双帧 180×180 GIF。
- 曾调整添加饮食表单中 Dropdown 与 TextField 的内部字段高度与外层约束；iQOO 11S 真机视觉效果未变化，问题留待下一版继续定位。

## APK

- 包名：`com.chenyang.carbs_king`
- versionName / versionCode：`1.2.3 / 82`
- 文件：`build/apk/carbs_king.apk`
- 大小：`201,768,011` 字节
- SHA-256：`B5509404BF82482688DB0592EA39041D7C33905F1095A00D810590E6847B51C9`
- v2 签名：有效；证书 SHA-256 为 `172A8B5C7A909A79FB483F83CF9FEA71FE6567937C900C1D47EAF0FD67AD75CE`。

## 验证

- 全量测试：446 passed，441 subtests passed。
- 动作库测试：12 passed，16 subtests passed。
- 资源门禁通过：源与 APK 内均为 1,326 GIF、1,326 JPG、2 MP3、1 WAV。
- APK 内已确认包含 `exercise_catalog_additions.json`。

## 发布后

- GitHub `v1.2.3` Release 仅保留 `carbs_king.apk`，并同步 `update_manifest.json` 的 Build、大小和 SHA-256。
- 源码已预备下一次 Build 83。
