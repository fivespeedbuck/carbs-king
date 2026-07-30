# Build 76 最终总结

日期：2026-07-30
仓库：`fivespeedbuck/carbs-king`
合并提交：`a6dea1d54fa266b48f72369bf93b31a968e9b18a`
PR：[2 - ship Build 76 training and update flow](https://github.com/fivespeedbuck/carbs-king/pull/2)

## 交付结果

- Build 76 APK 已构建并上传到 [v1.2.3 Release](https://github.com/fivespeedbuck/carbs-king/releases/tag/v1.2.3)。
- 下载地址：[carbs_king.apk](https://github.com/fivespeedbuck/carbs-king/releases/download/v1.2.3/carbs_king.apk)。
- 包名：`com.chenyang.carbs_king`。
- versionName：`1.2.3`；versionCode：`76`。
- APK 大小：`201,554,171` 字节。
- SHA-256：`3205A3F4CA6D8739C5FDB5F73A64FF1AA1658D4DE3E7B265BB5131AD77F31892`。
- Android v2 签名有效；证书 SHA-256 与 Build 75 一致：`172A8B5C7A909A79FB483F83CF9FEA71FE6567937C900C1D47EAF0FD67AD75CE`。

## 需求收口

- 训练顶部进度按真实完成的动作/组逐格显示，跳过前序组不会错误标绿。
- 普通动作、超级组和复合组统一使用动作管理流程，支持排序、编辑、增删和成员移出，并保持训练游标。
- 动作库筛选联合使用部位、细分肌群和器械；动作卡标题固定两行，器械与重量/次数/组数沉到底部。
- 摘要打开/关闭后搜索框不再抢回焦点或弹出键盘。
- 上游 1324 条动作与本地 ID、媒体 ID、GIF/JPG 文件逐项核对；腿/臀错分、乱码名称和中文重名已修正。
- 饮食表单四个字段在手机尺寸等高对齐；“最近”移除，只保留通栏“常用”。点击常用食物只回填食物和数量，确认保存前不写入餐次。
- “我”页面加入更新检查入口，按 Release 中显式的 Build 号判断是否有更新，并提供 APK 下载地址。

## 验证记录

- 自动测试：`427 passed`，`425 subtests passed`。
- Python 语法：`python -m compileall -q src tests tools` 通过。
- 差异格式：`git diff --check` 通过。
- 动作库审计：`upstream=1324 local=1324`；缺失 ID、额外 ID、媒体错配、缺失资源、待修分类均为 0。
- APK 内层 `assets/flutter_assets/app/app.zip`：2653 文件、155,783,546 字节、1324 GIF、1324 JPG、2 MP3、1 WAV；与根目录资源哈希一致。
- 本地网页预览根因已修复：Flet 0.85.3 使用 `flet run --name` 时页面路径与 WebSocket 配置不一致，导致 `Working…`；正式预览不再带 `--name`，根路径 `/` 的 WebSocket 已实测连接成功。

## 更新功能说明

Release 资产和 SHA-256 已由 GitHub 远端确认。手机应用访问 GitHub Releases API 若出现 HTTP 403，优先检查手机自身的梯子/VPN 或 GitHub API 限流；电脑上的代理不会自动作用于手机。网络不可达时可直接打开上面的 APK 下载地址，覆盖安装时不要先卸载旧版。

构建脚本成功后已把 `pyproject.toml` 和 `src/app_version.py` 一起预备为 Build 77，避免下一次源码版本不一致。

## 后续真机确认

在 iQOO 11S 上重点确认：应用内下载、系统安装器确认、覆盖安装后的数据保留、Android 中文日期选择器、主题持久化和输入框失焦保存提示。自动化测试与 APK 门禁通过不替代这些厂商系统行为的真机验证。
