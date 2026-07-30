# 下一会话交接：Build 76 真机修复、动作库与训练中动作管理

更新时间：2026-07-29
正式目录：`D:\carbs-king`
当前分支：`codex/build76-device-fixes`
当前基线：`main@3f16743`，Build 75 已正确发布
重要：当前修改尚未提交、尚未构建 Build 76、尚未上传 GitHub。

## 一、下一会话启动时必须读取

1. `C:\Users\chenyanggggg\.codex\memories\PROFILE.md`
2. `C:\Users\chenyanggggg\.codex\memories\ACTIVE.md`
3. 本文件
4. `PROJECT_CONTEXT.md`
5. `CURRENT_HANDOFF.md`
6. `docs\agent-notes\build-release.md`
7. `STAGE_RETROSPECTIVE_2026-07-29.md`

只使用 `D:\carbs-king`，不要创建 worktree，不要 reset、checkout 或批量还原当前工作树。

## 二、本会话已落盘但未提交的修改

当前 `git status --short` 有 17 个代码/测试文件修改或新增。

### 1. 动作库筛选与手机布局

文件：`src/training_controller.py`

已修改：

- 搜索动作时继续使用当前“热门 / 最近”排序。
- 搜索范围不再越过筛选条件：始终限定当前部位、细分肌群和器械。
- 点击动作或动作说明前主动让搜索框失焦并尝试调用 `blur()`，避免返回后反复弹出键盘。
- 左侧部位栏从 88 收窄到 72，内容栏获得更多宽度。
- “更多器械”不再使用会把入口挤出屏幕的横向滚动条。
- 热门器械按既定顺序自适应排列；一行能放三个就放三个。
- 冷门器械使用剩余宽度见缝插针。
- “全部”后“更多器械”始终保持可见，修复入口打不开/找不到的回归。

必须真机验证：

- 选择器械“全部”后点击“更多器械”。
- 切换部位、细分肌群、器械后搜索。
- 搜索后点击动作，再返回，键盘不自动抢焦点。
- iQOO 11S 宽度下长器械名称不越界。

### 2. 训练中三个操作区

文件：`src/training_views.py`、`src/training_controller.py`

用户最终确认的训练卡底部顺序：

1. 上一组 / 下一组
2. 减一组 / 加一组
3. 调整训练顺序（独立整行）
4. 下一个训练项

已实现：

- “减一组”只删除未完成组，已经完成的组不能删除，每个力量动作至少保留一组。
- “加一组”复制当前组的重量、次数和热身属性，生成新组。
- “调整训练顺序”打开全屏动作管理页。
- 管理页可以增加动作、删除尚未完成的动作、上移/下移动作。
- 已经完成过组数的动作不能删除。
- 调整顺序时通过动作 ID 保持当前动作和当前组游标，不把已完成记录串到别的动作。
- 增加动作复用现有完整动作库，不另做输入框。

最新训练修改完成后还没有重新跑测试，下一会话必须先跑专项。

### 3. 真机 UI 修复

- `src/diet_controller.py`
  - 添加饮食表单中的“搜索食物”和“食物”下拉框固定为相同 52 高度和相同垂直内边距。
- `src/training_plan_views.py`
  - “今天练什么”空状态里的“自由训练”按钮不再与英雄卡背景同色，恢复可见底色。
- `src/analytics_page.py`
  - 六个“体重、体脂、围度、饮食、训练、恢复”按钮从手机上一行六个改为两行三列，避免中文被压成空白。
- `src/recovery_controller.py`
  - “记录体脂”从固定蓝色改为与“记录体重”一致，跟随主题。
- `src/profile_views.py`
  - 目标挑战卡浅灰底、无边框；挑战名称恢复黑色；旗子、等级和进度仍使用等级语义色。
- `src/profile_theme_views.py`
  - 主题区域浅灰底、无边框。

以上还没有重新启动正式目录预览，也没有真机复验。

### 4. “我”页面自动保存和功能设置卡

文件：`src/profile_controller.py`、`src/profile_details_views.py`

已实现：

- 体重、体脂、身高、年龄四项均在失焦时自动保存。
- 分别提示“体重已保存 / 体脂已保存 / 身高已保存 / 年龄已保存”。
- 保存会同步 profile 与当天记录，宏量计算读取同一状态。
- 现有“我”卡只放个人资料、身体数据和宏量公式。
- “我”卡下方新增同级“功能设置”大卡，不嵌在“我”卡内部。
- “功能设置”卡依次包含：主题色、备份与恢复、应用更新。
- 三个内部区域统一使用浅灰底、无边框。

### 5. GitHub Release 更新检查

新增：

- `src/app_version.py`
- `src/update_service.py`
- `src/profile_update_views.py`

已实现：

- 运行时版本：`1.2.3 / Build 76`，与 `pyproject.toml` 对齐。
- 进入“我”页面后自动检查 GitHub 最新 Release，并可手动重新检查。
- 从 Release 标题、正文或标签解析显式 `Build N`。
- 读取 APK 下载地址、大小和 SHA-256 digest。
- 有更高 Build 时显示下载入口。
- Android 不尝试静默安装；下载后仍由系统安装器让用户确认。

未验证风险：

- `page.launch_url/open_url` 在当前 Flet 0.85.3 Android 真机上的实际行为尚未验证。
- 自动检查失败时不应阻塞页面，但需要真机断网验证。
- 当前 GitHub Release 仍是 Build 75；Build 76 发布后标题必须包含明确 `Build 76`。

## 三、本会话测试结果

已通过：

- `test_build76_regressions.py`：10 项
- `test_profile_macro_and_measurements.py`：20 项
- `test_theme_service.py`：3 项
- `test_analytics_views.py`：56 项
- `test_diet_information_architecture.py`：24 项
- `test_training_views.py`：15 项
- `test_training_set_highlight.py`：2 项

`test_ui_contracts.py` 当时结果：

- 49 项通过。
- 1 项旧断言失败，因为“我”页面现在有两张同级 `page_card`；断言随后已更新。
- 更新断言后又新增了“增减组”和“动作管理全屏页”两个运行时测试，但尚未重跑。

语法检查：

- 在最新训练功能加入前，相关模块 `py_compile` 已通过。
- 最新训练功能加入后必须重跑。

命令环境注意：

- `tests` 不是 Python 包，使用：
  `python -m unittest discover -s tests -p 'test_xxx.py' -v`
- `test_diet_information_architecture.py` 单独运行时需要：
  `$env:PYTHONPATH='D:\carbs-king\src'`
- 本会话 Codex Windows 沙箱异常：项目 Python 和 `.git` 每次触发审核，内置 `apply_patch` 还出现 sandbox refresh error。换新会话后先验证工具权限，不要误判为代码失败。

## 四、下一会话立即执行顺序

1. 读取上述文件。
2. 检查：
   - `git branch --show-current`
   - `git status --short`
   - `git diff --check`
   - 当前完整 diff
3. 先跑：
   - `test_build76_regressions.py`
   - `test_ui_contracts.py`
   - `test_training_views.py`
   - `test_training_set_highlight.py`
4. 修复任何代码失败后，运行本轮所有专项。
5. 运行全量测试。Build 75 前全量基线为 391 项；本轮新增测试后数量应更多。
6. 运行相关 `py_compile` 与 `git diff --check`。
7. 停止旧预览，只从 `D:\carbs-king` 启动单一手机宽度预览。
8. 真实点击验证动作库、训练中按钮顺序、功能设置卡和更新检查。
9. 测试全绿后直接构建 Build 76，但暂时不要上传 GitHub，等用户真机确认。
10. 构建必须使用 `build_apk_update.ps1`，并检查 APK 内层 `assets/flutter_assets/app/app.zip`。

## 五、构建和资源硬门禁

Build 75 正确基线：

- APK：`build\apk\carbs_king.apk`
- versionCode：75
- 大小：201,518,971 字节
- SHA-256：`765E3EA57233BDA6D497048B652F7DC294BE21F457D9E6B001D8B7158D80210F`
- 内层资源：2653 文件、1324 GIF、1324 JPG、2 MP3、1 WAV
- GitHub Release：`https://github.com/fivespeedbuck/carbs-king/releases/tag/v1.2.3`

Build 76 必须满足：

- versionCode 确实为 76。
- 根目录 `assets` 是唯一资源源，`src/assets` 只是构建前镜像。
- 1324 个 GIF 文件头是真实 `GIF87a/GIF89a`，不能是 LFS 指针。
- APK 内层资源逐文件匹配，不能只看 APK 大小或“Successfully built”。
- 记录 APK 大小、SHA-256、签名证书和资源统计。
- 用户当前要求：先构建，等其锻炼回来再决定是否上传；新会话不要自行上传 Release。

## 六、Git 与最终交付

- 当前所有修改留在 `codex/build76-device-fixes`。
- 不直接写 `main`，不 force-push，不重写历史。
- 测试、预览和 APK 资源门禁通过后再提交分支。
- 用户回来确认 APK 后，才推送、合并 `main`、替换 GitHub Release。
- Release 替换后核对远端大小和 digest。
- 更新 `CURRENT_HANDOFF.md`、`PROJECT_CONTEXT.md`、`CHANGELOG.md`、构建复盘。
- 最终报告仍需列出上一任项目经理造成的问题、实际后果和本轮如何修正；已有历史复盘可参考 `STAGE_RETROSPECTIVE_2026-07-29.md`，不要用情绪化描述代替事实。
