# Build 77 更新备用源交付总结

日期：2026-07-30
仓库：`fivespeedbuck/carbs-king`
发布分支：`codex/build77-update-fallback`

## 问题与结论

Build 76 在手机已开启梯子的情况下，应用内更新检查仍收到 GitHub Releases API HTTP 403。Release 页面、APK、包名和签名均正常，问题位于手机网络出口访问匿名 `api.github.com` 的链路；开着梯子并不保证该 API 出口不被限流或策略拒绝。

Build 77 保留 GitHub Releases API 为首选来源。当 API 返回 403、发生网络错误、超时或返回无效 JSON 时，自动读取公开备用清单：

`https://raw.githubusercontent.com/fivespeedbuck/carbs-king/main/update_manifest.json`

清单只包含公开的 Release 标题、页面、APK 下载地址、文件大小和 SHA-256，不在 APK 中内嵌 GitHub Token。

## 交付物

- APK：`build/apk/carbs_king.apk`
- 包名：`com.chenyang.carbs_king`
- versionName：`1.2.3`
- versionCode：`77`
- 大小：`201,554,835` 字节
- SHA-256：`9AE333EA927A5D3B3BBF771152CDD50CB322DBA81F01A68F71753E4E0EBA2B7C`
- v2 签名证书 SHA-256：`172A8B5C7A909A79FB483F83CF9FEA71FE6567937C900C1D47EAF0FD67AD75CE`

## 验证结果

- 全量测试：`428 passed`，`425 subtests passed`。
- API 403 自动回退备用清单的回归测试通过。
- Python 编译检查和 Git 差异格式检查通过。
- APK 内层资源：2653 个文件、155,783,546 字节、1324 GIF、1324 JPG、2 MP3、1 WAV。
- APK 的 package、versionCode、versionName 和 v2 签名通过 Android 工具校验。

## 安装边界

Build 76 自身没有备用更新源逻辑，因此收到 403 时无法靠远端配置自我修复。用户需要手动下载并覆盖安装 Build 77 一次，不要卸载旧版；从 Build 77 开始，未来 GitHub API 再返回 403 时才会自动走备用清单。
