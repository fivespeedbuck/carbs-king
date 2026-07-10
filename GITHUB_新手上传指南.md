# GitHub 新手上传指南

这份项目已经包含 Git 历史，不需要手动创建提交。推荐使用 GitHub Desktop 的图形界面发布。

## 第一次上传

### 1. 安装并登录 GitHub Desktop

1. 打开 <https://desktop.github.com/download/> 下载 Windows 版。
2. 安装后选择 `Sign in to GitHub.com`。
3. 在浏览器中登录你现有的 GitHub 账号并授权。

### 2. 解压项目

将收到的 GitHub 仓库包完整解压，例如：

```text
D:\carbs-king
```

不要只复制 `src` 文件夹，压缩包里的隐藏 `.git` 目录保存着 v42 到 v44.1 的版本历史。

### 3. 添加本地仓库

1. 打开 GitHub Desktop。
2. 点击 `File` → `Add Local Repository`。
3. 选择刚才解压的 `D:\carbs-king`。
4. 点击 `Add Repository`。

### 4. 发布到 GitHub

1. 点击上方的 `Publish repository`。
2. `Name` 填写：`carbs-king`。
3. `Description` 可填写：`碳水大王 Flet Android APP`。
4. 保持 `Keep this code private` 勾选。
5. `Organization` 选择 `None`，表示放在你的个人账号下。
6. 点击 `Publish Repository`。

发布后，点击 `Repository` → `View on GitHub` 即可打开网页仓库。

### 5. 上传已有版本标签

发布仓库后，双击项目里的 `上传版本标签.bat`。看到 `Version tags uploaded successfully` 表示完成。

随后 GitHub 的 Tags 页面会显示：`v42`、`v43`、`v44`、`v44.1`。

## 以后怎样提交新版本

1. 始终修改同一个 `D:\carbs-king` 文件夹，不要每个版本创建一个新仓库。
2. 打开 GitHub Desktop，左侧会显示变更文件。
3. 左下角 `Summary` 填写本次修改，例如：`release: v45 food statistics`。
4. 点击 `Commit to main`。
5. 点击顶部 `Push origin` 上传。
6. 切换到 `History`，右键刚提交的版本，选择 `Create Tag`，输入 `v45`。

GitHub Desktop 默认会将新建标签与对应提交一起上传。

## APK 应放在哪里

不要把 APK、SO、DILL、构建目录放进源码提交。发布 APK 时：

1. 打开 GitHub 仓库网页。
2. 点击右侧 `Releases` → `Draft a new release`。
3. 选择对应版本标签，例如 `v44.1`。
4. 上传 `carbs_king.apk`。
5. 点击 `Publish release`。

## 重要安全事项

- 不要上传 `.jks`、`.keystore`、`.env` 或任何密码。
- 不要上传真实体重、饮食、训练等个人记录。
- Android 签名密钥要单独保存在加密网盘、U 盘或 NAS 中。
- GitHub 保存的是源码，APP 内的个人记录仍要使用“完整备份”导出。
