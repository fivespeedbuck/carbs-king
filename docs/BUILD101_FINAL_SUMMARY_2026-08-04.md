# Build 101 正式交付总结

日期：2026-08-04

状态：正式发布；全模块冻结。

## 本批次结果

- V3.3-final 动态碳循环及其阶段基线、历史快照和模式旁路完成交付。
- 数据页选择器恢复点击，保持横向滚动位置，下级选择不再带动上级闪跳。
- 训练中增加动作后直接返回并原地刷新“调整动作顺序”。
- Android 后台休息使用系统闹钟；正常训练不再自动反复打开悬浮窗授权页。
- 结束训练 1–5 评分整排居中。
- 体重超过 7 天、体脂和围度超过 28 天的黄色更新提示保留并冻结。

## 验证

- 全量回归：`542 passed, 448 subtests passed`
- Python 编译：通过
- Git 差异格式：通过
- 网页预览：数据页和训练交互通过
- iQOO 11S：Build 101 覆盖安装成功，系统确认 `versionCode=101`
- APK 资源：1,326 GIF、1,326 JPG、2 MP3，源与包内资源门禁通过
- 原生提醒：Receiver、Overlay Service、闹钟权限和原生声音门禁通过

## APK

- 文件：`release_candidates/carbs-king-v1.2.3-build101-release.apk`
- 大小：`201,914,395` 字节
- SHA-256：`8BC9DE0B9489288D2F8B630D7FD3E1289BE272018E6BA2A4C42C1A0167B59DE9`
- 包名：`com.chenyang.carbs_king`
- versionName / versionCode：`1.2.3 / 101`
- 签名：APK Signature Scheme v2
- 证书 SHA-256：`172A8B5C7A909A79FB483F83CF9FEA71FE6567937C900C1D47EAF0FD67AD75CE`

## 冻结

Build 101 发布源码全部冻结。后续只有用户针对明确 BUG 授权的对应模块允许最小修改；新功能必须进入独立后续 Build。
