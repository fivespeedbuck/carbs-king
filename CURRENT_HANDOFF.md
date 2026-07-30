# 当前交接：2026-07-30 Build 78 动作搜索与休息提醒

> 本文件只记录当前可执行事实。稳定产品约束见 `PROJECT_CONTEXT.md`，本次完整结果见 `docs/BUILD78_EXERCISE_SEARCH_SOUND_2026-07-30.md`。

## 当前状态

- 正式目录：`D:\carbs-king`
- 源码 PR：[#5](https://github.com/fivespeedbuck/carbs-king/pull/5) 已合并到 `main`（merge commit `d2f5d87`）。
- Build 78 已完成全量测试、真实手机宽度页面验收、APK 资源门禁、原生提醒运行时门禁、包名、版本和签名校验。
- GitHub `v1.2.3` Release 已替换为 Build 78，远端只保留单一 `carbs_king.apk`，size/digest 已核对一致。
- 构建脚本已把 `pyproject.toml` 与 `src/app_version.py` 预备为下一次 Build 79。

## 最终 APK

- 文件：`build/apk/carbs_king.apk`
- 包名：`com.chenyang.carbs_king`
- versionName：`1.2.3`
- versionCode：`78`
- 大小：201,654,203 字节
- SHA-256：`BBD04D9961478E67917C7691AD9390A215EED31C8981D14A1CC75DBA3206E9E1`
- APK v2 签名有效；证书 SHA-256：`172A8B5C7A909A79FB483F83CF9FEA71FE6567937C900C1D47EAF0FD67AD75CE`
- 证书与历史 Build 55/77 一致，具备覆盖安装所需的签名连续性。

## 验证基线

- 全量测试：440 passed，441 subtests passed。
- 动作目录：1324 个稳定 ID，缺失/额外/媒体错配/缺失文件均为 0。
- APK 内层资源：2653 个文件、155,783,546 字节、1324 GIF、1324 JPG、2 MP3、1 WAV。
- 原生提醒门禁：`RestAlarmReceiver`、插件类、`POST_NOTIFICATIONS`、`USE_EXACT_ALARM`、v3 渠道、`raw/rest_coin` 与防 R8 裁剪可达性全部通过。
- 真实页面：430 × 900 视口下逐词验证倒蹬、大剪刀、坐姿腿屈伸、双杠臂屈伸、站姿下夹、哑铃上斜推胸、蝴蝶机夹胸、反向蝴蝶机飞鸟和鹦鹉螺。

## 当前产品结果

- 1324 条动作保留原 ID/GIF/JPG，用户可见名称只用中文；雪橇体系改为倒蹬机，杠杆式器械改为悍马机体系。
- 搜索按主名/别名相关性排序，常用基础动作优先；选错肌群、器械或部位时自动逐级放宽并显示提示，不再空白。
- 已安排的 Android `AlarmManager` 或进程内定时器独占休息到点交付；前台 tick 只持久化完成状态，暂停、调整、跳过仍取消或重排。
- 原生通知使用 v3 中文高优先级渠道与内置 `rest_coin`，截止时间使用毫秒精度和向上取整。
- 全量备份已覆盖主题色和年龄基准年的导入后运行时同步，并通过模拟卸载往返一致性测试。
- 训练卡片在手机视口宽度下重新约束，避免窄屏布局挤压。

## 用户真机验收顺序

1. 在旧版中执行全量导出并确认备份文件可用。
2. 按用户本次决定卸载旧版，再全新安装 Build 78。
3. 导入全量备份，核对训练、饮食、身体、个人资料、主题色、年龄基准年、食物库和补剂库。
4. 首次休息提醒时允许通知与精确闹钟权限。
5. 分别验证应用前台、切到后台、锁屏三种状态的自然到点声音；再验证暂停、加减时间和跳过不会误响。

## 远端发布结果

- `main/update_manifest.json` 已显示 Build 78、201,654,203 字节和上述 SHA-256。
- `v1.2.3` Release 只保留一个 `carbs_king.apk`，状态为 `uploaded`。
- 远端 `size` 为 201,654,203，`digest` 为 `sha256:bbd04d9961478e67917c7691ad9390a215eed31c8981d14a1cc75dba3206e9e1`。
- Release URL：`https://github.com/fivespeedbuck/carbs-king/releases/tag/v1.2.3`
