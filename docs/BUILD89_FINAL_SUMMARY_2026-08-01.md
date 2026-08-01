# Build 89 最终交付摘要（2026-08-01）

## 版本与 APK

- versionName：`1.2.3`
- versionCode：`89`
- 包名：`com.chenyang.carbs_king`
- APK：`build/apk/carbs_king.apk`
- 大小：`201,779,811` 字节
- SHA-256：`CE2CB6F28778F2A3D3F68BB4DA88E414B89C7EB3EDC1CC0214260F12E89E3AF8`
- v2 签名证书 SHA-256：`172A8B5C7A909A79FB483F83CF9FEA71FE6567937C900C1D47EAF0FD67AD75CE`

## 交付内容

- 添加饮食改用从底部向上展开的不透明白色选择面板；最后一项保留 Android 手势安全空间。
- 添加动作页收窄左侧部位栏；细分部位、器械筛选和动作卡扩展到搜索框右边界。
- 动作卡优先显示 GIF，帮助和选择按钮保持在最右侧；列表继续按需构建并以 24 项分页。
- “我”页实际修改体重或体脂后写入当天趋势；单项修改保留同日另一项明确测量，首次资料保存也会记录。

## 验证结果

- `458 passed, 441 subtests passed`。
- Python 编译和 Git 差异格式检查通过。
- APK 内 1,326 GIF、1,326 JPG、2 MP3、0 WAV；源资源与打包资源哈希一致。
- APK 原生门禁确认闹钟接收器、悬浮窗前台服务、插件类、权限、提示音和防裁剪可达性。
- APK 包名、versionCode 89、v2 签名和历史证书一致。
- iQOO 11S 真机验收通过。

## 后续

- 源码已预备到 Build 90。
- Build 90 仅用于高级动态碳循环；完整产品约束见 `PENDING_FEATURES.md`。
