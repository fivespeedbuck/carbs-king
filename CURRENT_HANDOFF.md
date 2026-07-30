# 当前交接：2026-07-31 Build 79 前台休息提示与应用内更新

> 本文件只记录当前可执行事实。稳定产品约束见 `PROJECT_CONTEXT.md`，本次完整结果见 `docs/BUILD79_FOREGROUND_REST_UPDATE_2026-07-31.md`。

## 当前状态

- 正式目录：`D:\carbs-king`
- Build 79 已完成全量测试、APK 资源门禁、原生提醒/应用内安装运行时门禁、包名、版本和签名校验。
- 待发布：合并本次源码后，替换 GitHub `v1.2.3` Release 的单一 `carbs_king.apk`，并核对远端 size/digest。
- 构建脚本已把 `pyproject.toml` 与 `src/app_version.py` 预备为下一次 Build 80。

## 最终 APK

- 文件：`build/apk/carbs_king.apk`
- 包名：`com.chenyang.carbs_king`
- versionName：`1.2.3`
- versionCode：`79`
- 大小：201,667,039 字节
- SHA-256：`26CF622FF2B6B3F0C310A27092C914DB6F3036EAC58C75B2F47322B2223374AE`
- APK v2 签名有效；证书 SHA-256：`172A8B5C7A909A79FB483F83CF9FEA71FE6567937C900C1D47EAF0FD67AD75CE`
- 证书与历史 Build 55/77 一致，具备覆盖安装所需的签名连续性。

## 验证基线

- 全量测试：444 passed，441 subtests passed。
- 动作目录：1324 个稳定 ID，缺失/额外/媒体错配/缺失文件均为 0。
- APK 内层资源：2653 个文件、155,783,546 字节、1324 GIF、1324 JPG、2 MP3、1 WAV。
- 原生提醒与更新门禁：`RestAlarmReceiver`、插件类、`POST_NOTIFICATIONS`、`USE_EXACT_ALARM`、`REQUEST_INSTALL_PACKAGES`、Flet FileProvider、v3 渠道、`raw/rest_coin` 与防 R8 裁剪可达性全部通过。

## 当前产品结果

- 1324 条动作保留原 ID/GIF/JPG，用户可见名称只用中文；雪橇体系改为倒蹬机，杠杆式器械改为悍马机体系。
- 搜索按主名/别名相关性排序，常用基础动作优先；选错肌群、器械或部位时自动逐级放宽并显示提示，不再空白。
- 应用可见时，组间到点由 Flet 内置音频直接交付；后台、锁屏或失焦时交由 Android `AlarmManager`，暂停、调整、跳过仍取消或重排。
- 原生通知使用 v3 中文高优先级渠道与内置 `rest_coin`，截止时间使用毫秒精度和向上取整。
- 全量备份已覆盖主题色和年龄基准年的导入后运行时同步，并通过模拟卸载往返一致性测试。
- 添加动作卡片为单列、保留右侧留白并增加底部间距；动作顺序卡使用独立外框，避免边框裁切。
- 更新页支持应用内 APK 下载、进度、大小/哈希校验与系统安装界面交接。

## 用户真机验收顺序

1. 在旧版中执行全量导出并确认备份文件可用。
2. 覆盖安装或按用户决定全新安装 Build 79。
3. 导入全量备份，核对训练、饮食、身体、个人资料、主题色、年龄基准年、食物库和补剂库。
4. 首次休息提醒时允许通知与精确闹钟权限。
5. 分别验证应用前台、切到后台、锁屏三种状态的自然到点声音；再验证暂停、加减时间和跳过不会误响。

## 远端发布结果

- `main/update_manifest.json` 必须显示 Build 79、201,667,039 字节和上述 SHA-256。
- `v1.2.3` Release 最终只保留一个 `carbs_king.apk`。
- 上传后远端 `size` 必须为 201,667,039，`digest` 必须为 `sha256:26cf622ff2b6b3f0c310a27092c914db6f3036eac58c75b2f47322b2223374ae`。
- Release URL：`https://github.com/fivespeedbuck/carbs-king/releases/tag/v1.2.3`
