# Build 88 最终交付摘要（2026-08-01）

## 版本与 APK

- versionName：`1.2.3`
- versionCode：`88`
- 包名：`com.chenyang.carbs_king`
- APK：`build/apk/carbs_king.apk`
- 大小：`201,774,031` 字节
- SHA-256：`F1DD624C4906E3F5AA28B73534D467A6DBF3F4BFFBB27D7BF7E698A039102739`
- v2 签名证书 SHA-256：`172A8B5C7A909A79FB483F83CF9FEA71FE6567937C900C1D47EAF0FD67AD75CE`

## 交付内容

- 后台、锁屏、息屏组间休息提醒与主题色悬浮倒计时。
- 悬浮窗下一动作、点击返回、平滑拖动；调整时间复用持续通知。
- 每动作独立休息时间，默认 90 秒。
- “我 → 功能设置”后台提醒权限检查入口。
- 完成训练 15 天回收站、原日期恢复、彻底删除与备份。
- 添加饮食字段外框对齐、下拉菜单不透明表面及无结果禁用。

## 验证结果

- `455 passed, 441 subtests passed`。
- Python 编译、Git 差异格式检查通过。
- APK 包名、versionCode 88、v2 签名和历史证书一致。
- APK 内 1,326 GIF、1,326 JPG、2 MP3、0 WAV；源资源与内层资源哈希一致。
- APK 原生门禁确认 `RestAlarmReceiver`、`RestOverlayService`、插件类、权限、通知渠道和提示音可达。
- iQOO 11S 已验证休息提醒与悬浮窗链路；食物下拉菜单最终视觉效果待安装 Build 88 后确认。

## 后续重点

- 动态碳循环与训练负荷评分是下一阶段核心升级，完整产品约束记录在 `PENDING_FEATURES.md`。
- “我”页体重/体脂同步数据趋势仍未实现。
- 源码已预备到 Build 89。
