# Build 111 正式交付（2026-08-11）

## 范围

- 食物库与动作库搜索／新增控件对齐。
- 动作参数改为 `20 kg × 4 / 4`，动作主部位栏加宽。
- 新增／修改食物的计量口径全宽；添加饮食显示只读真实口径。
- 常用食物使用三行内流式标签：长名不换行、先缩字后省略，并消除尾部无意义空白。

## 验证与产物

- 自动化：`561 passed, 448 subtests passed`。
- APK：`build/apk/carbs_king.apk`，201,898,707 bytes。
- SHA-256：`06497F6AB208A49493A368E3057855B6CDB82657FE8B60A72B924CF79B03ED1F`。
- 包：`com.chenyang.carbs_king`，`1.2.3 / Build 111`，v2 签名通过。
- 资源／运行时门禁：1326 GIF、1326 JPG、2 MP3 与原生休息提醒通过。
- 已无线覆盖安装 V2304A，`dumpsys` 确认 `versionCode=111`、`versionName=1.2.3`，用户数据保留。

## 发布边界

- GitHub Release `v1.2.3` 更新为 Build 111 APK，并同步根目录 `update_manifest.json`。
- 源码已预备为 Build 112；V3.3 动态碳循环计算规则未改动。
