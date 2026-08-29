# Build 117 正式发布总结

日期：2026-08-29  
版本：`1.2.3 / Build 117`  
包名：`com.chenyang.carbs_king`

## 本次交付

- 修复训练总结包含有氧项目时四项统计数字在窄屏上的自适应显示。
- 四项数字统一使用同一自适应字号，并保持单行显示；`4471.5` 使用 20 号字，更长的 `10000.5`、`99999.9` 使用 18 号字。
- 未修改训练统计口径、标签、列结构或其他已冻结 UI。

## 验证

- 全量自动化：`568 passed, 457 subtests passed`。
- Python 编译与 `git diff --check` 通过。
- APK 资源、原生提醒、包名和签名门禁通过；包含 1326 GIF、1326 JPG、2 MP3。
- APK：201,848,887 bytes。
- APK SHA-256：`05DA174E91492904B1D97C78496A7A2B8C65A0344DB2AD85C5C16B2DA25CB676`。
- APK Signature Scheme v2 通过；证书 SHA-256：`172A8B5C7A909A79FB483F83CF9FEA71FE6567937C900C1D47EAF0FD67AD75CE`。

## 发布

- GitHub Release：<https://github.com/fivespeedbuck/carbs-king/releases/tag/v1.2.3>
- Release APK 已替换为 Build 117，远端状态为 `uploaded`，大小和 SHA-256 与本地一致。
- `update_manifest.json`、README、CHANGELOG、CURRENT_HANDOFF 和 PROJECT_CONTEXT 已同步；源码已预备下一 Build 118。

## 真机边界

- 本批代码和 APK 门禁已通过；发布前手机无线 ADB 曾离线，未形成新的真机截图证据。用户已确认可以发布。
