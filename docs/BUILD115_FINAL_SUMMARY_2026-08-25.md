# Build 115 正式发布总结

日期：2026-08-25
版本：`1.2.3 / Build 115`
包名：`com.chenyang.carbs_king`

## 本次交付

- 修复动作选择卡在 Android/Flet 触摸事件竞态下偶发双触发。保留整卡和右侧按钮的现有 UI，仅对同一动作增加 350ms 去抖。
- 修复前台 Flet 播放与 Android AlarmManager 原生播放在同一休息周期到点时的竞态。两条链路共享 `SharedPreferences` 送达标记，原生接收器先认领周期再启动 `MediaPlayer`；前台检测到原生已认领时不再播放。
- 保留音频路由：后台/锁屏组间休息使用 `USAGE_ALARM` 闹钟流；前台组间休息和训练完整结束使用 Flet 媒体播放器；通知渠道只负责显示，不新增第二个声音来源。
- 用户提供的组间休息音频继续同步到 Flet 与 Android 原生资源，SHA-256：`8F732DE8D36241FF8B431DDF8317B2E33F14CBA0A1BAB830BAE3C30E03D6E32A`。

## 验证

- 全量自动化：`567 passed, 454 subtests passed`。
- Python：`python -m compileall -q src tests tools` 通过。
- 格式：`git diff --check` 通过。
- APK 资源门禁：1326 GIF、1326 JPG、2 MP3，根目录与内嵌资源一致；原生 Receiver、Overlay Service、权限、`raw/rest_coin` 与防裁剪可达性通过。
- APK：201,848,183 bytes。
- APK SHA-256：`D6A36090317A780DC6E70AA787FFE02D8BA916FE8344B42B0BB034D264B1ED37`。
- APK Signature Scheme v2 通过；证书 SHA-256：`172A8B5C7A909A79FB483F83CF9FEA71FE6567937C900C1D47EAF0FD67AD75CE`。

## 发布

- `update_manifest.json` 已同步 Build 115、APK 大小与 SHA-256。
- README、CHANGELOG、CURRENT_HANDOFF、PROJECT_CONTEXT、代码索引已同步。
- GitHub 主线已提交并推送，Release `v1.2.3` 的 `carbs_king.apk` 已替换为 Build 115；远端资产大小、digest 和上传状态需在发布命令完成后复核。
- Build 115 真机覆盖安装待 iQOO 15U 重新连接后完成最终复验；在此之前不宣称真机复验通过。

## 边界

- 未修改 V3.3 历史快照、V3.4 宏量合同、数据页统计规则或现有 UI 布局。
- APK 不提交 Git；源码构建后已预备下一 Build 116。
