# 碳水大王

基于 Flet 开发的 Android 碳循环饮食、训练与身体数据记录 APP。

当前版本：**v46**

Flet：**0.85.3**

Android 包名：`com.chenyang.carbs_king`

## 主要功能

- 高碳、中碳、低碳目标和碳水/蛋白质/脂肪区间
- 自动计算或自定义高中低碳倍数
- 饮食、训练、饮水、补剂和睡眠记录
- 体重、体脂、腰围、臂围及 BMR/TDEE 计算
- 历史记录与详情
- 完整或分类 JSON 备份导入、导出

## 目录

- `src/main.py`：APP 主要源码
- `assets/`：应用图标
- `pyproject.toml`：项目、依赖和 Android 包名配置
- `build_apk_fast.bat`：Windows 快速打包入口
- `build_apk_update.ps1`：固定包名、签名和构建号的打包脚本
- `CHANGELOG.md`：版本变化
- `GITHUB_新手上传指南.md`：第一次发布到 GitHub 的图形化教程

## 本地运行

```powershell
flet run
```

也可以双击 `run_desktop.bat`。

## 打包 APK

双击 `build_apk_fast.bat`。成功后脚本会自动准备下一个 Android 构建号。

签名密钥备份位于：

```text
%USERPROFILE%\.carbs_king_signing\debug.keystore
```

请另外妥善备份该密钥。后续 APK 必须保持相同包名和签名，Android 才能覆盖更新并保留 APP 数据。

## 版本管理

仓库已包含以下历史标签：`v42`、`v43`、`v44`、`v44.1`、`v45`、`v46`。旧版本无需作为 ZIP 放进源码目录，可通过 Git 历史或 GitHub Release 获取。

第一次上传请阅读：[GITHUB_新手上传指南.md](GITHUB_新手上传指南.md)。
