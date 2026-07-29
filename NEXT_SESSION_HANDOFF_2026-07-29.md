# 下一会话交接：碳水大王未完成事项与本会话踩坑复盘

> 历史说明：本文保留上一会话当时的状态，其中“把 `src/assets` 再次提交到 LFS”的
> 建议已被后续审计否决。当前正确规则是根目录 `assets` 为唯一资源源，
> `src/assets` 为构建前生成且被 Git 忽略的镜像；以最新 Git 状态和
> `docs/agent-notes/build-release.md` 为准。

更新时间：2026-07-29
正式目录：`D:\carbs-king`
交接原则：下一会话只在正式目录工作；先读本文件，再读 `PROFILE.md`、`ACTIVE.md`、`PROJECT_CONTEXT.md`、`CURRENT_HANDOFF.md`。不要创建 worktree，不要创建开发/测试/UI 子会话。

## 一、当前结论

本会话已停止。没有继续构建、上传或发布。

已完成但尚未收口：

- 目标挑战、自动宏量目标和可重复赛道等前序功能已经在 `main`，最近已推送提交 `98d5e74`。
- 资源门禁和 `src/assets` 资源纳入版本控制的第一版已提交并推送为 `38436b5 fix: enforce packaged asset completeness`，但该提交中的 `src/assets/exercises` 是 Git LFS 指针，且当时没有给 `src/assets` 配置 LFS 规则；不能把该提交视为资源完整发布。
- `v1.2.3` GitHub Release 当前被上传了一个约 68.6 MiB 的错误 APK。它的应用包中有 1324 个 GIF 文件名，但内容是约 130 字节的 LFS 指针，不是真实动画。必须重新构建后再替换 Release，不能继续使用当前 APK。
- 真实 LFS 资源已下载到根目录 `assets/exercises`，约 155 MB；已复制到 `src/assets/exercises`，两边当前总字节数一致。复制后的真实资源仍是工作树未提交修改。
- 真实资源 APK 构建已启动过一次，随后用户要求停止，已杀掉构建进程树；没有得到新的 APK。`build/apk/carbs_king.apk` 仍是旧的 71,915,571 字节错误 APK。
- 性别按钮和空挑战卡 UI 已修改并通过专项测试，但尚未提交，也没有重启预览验证。
- 自动宏量公式尚未修改。截图中的 `增肌` 仍会显示类似 `碳 7.8 | 蛋 1.95 | 脂 0.75`，这是当前未解决的核心问题。

## 一-A、重要：错误内容已被直接推送到 main

本会话曾错误地直接向 `main` 提交并推送：

- 提交：`38436b5 fix: enforce packaged asset completeness`
- 上一个功能提交：`98d5e74 feat: add macro goals and active challenges`
- 远端：`origin/main`

`38436b5` 的问题必须明确：

1. 它修改了 `.gitignore`，把 `src/assets/exercises` 纳入版本控制。
2. 它新增了 `docs/agent-notes/build-release.md`。
3. 它向 `src/assets/exercises` 提交了约 2649 个文件，但这些文件当时仍是约百字节的 Git LFS 指针文本，不是真实 GIF/JPG 内容。
4. 当时 `.gitattributes` 只有 `assets/exercises/**` 的 LFS 规则，没有 `src/assets/exercises/**`，因此这批 `src` 资源没有按正确的 LFS 路径收口。
5. 随后还用错误资源构建了约 71,915,571 字节的 APK，并覆盖上传到了 GitHub Release `v1.2.3`。

当前没有进入 `main` 的内容：

- 本交接文件 `NEXT_SESSION_HANDOFF_2026-07-29.md` 仍是未跟踪文件。
- `.gitattributes` 的 `src/assets/exercises/** filter=lfs ...` 修正尚未提交。
- 真实的 `src/assets/exercises` 文件尚未提交。
- 空挑战卡全宽修复、性别“女”修复及其测试尚未提交。
- 自动宏量公式没有产生代码修改。

下一会话处理 `main` 的安全规则：

- 不得 `git reset --hard`、不得强制推送、不得直接改写远端历史。
- 当前工作树有约 2654 项未提交内容；在保护并审查这些修改前，不得直接 `git revert 38436b5`，否则会与真实资源和 UI 修复发生大面积冲突。
- 推荐采用前向纠正提交：先确认 `.gitattributes` 同时覆盖根目录和 `src` 资源，确认工作树中的两套资源都是真实文件，再 `git add` 让 `src/assets/exercises` 正确进入 LFS，完成验证后提交并推送修正。
- 如果用户明确要求撤销 `38436b5`，必须先保护当前未提交修改，再执行普通 `git revert 38436b5`；仍然禁止 reset/force-push。撤销后还要重新设计正确的资源打包方案。
- GitHub Release 资产不属于 Git 提交历史。即使修正或撤销 `38436b5`，也必须单独重新构建并用正确 APK 替换 `v1.2.3`。

### 下一会话首要任务：把 main 中误入/无用内容拆出来

下一会话不得继续直接在 `main` 开发。应先从当前 `main` 创建清理分支，例如
`codex/main-cleanup`，所有清理和修正都先在该分支完成并验证。

必须审计：

```powershell
git show --stat --summary 38436b5
git show --name-status 38436b5
git lfs ls-files
git ls-files src/assets/exercises
```

需要从 `main` 的后续状态中拆除或纠正：

1. `src/assets/exercises/**` 中误提交的 LFS 指针/重复资源。根目录
   `assets/exercises/**` 应作为唯一真实资源源；不要长期在 Git 中维护两套相同训练资源。
2. 为适配 Flet `path = "src"` 而临时复制到 `src/assets` 的训练资源，应改成可重复的构建前同步产物，或改成经验证的构建配置；完成方案前不能直接删除，否则 APK 会再次缺资源。
3. `.gitignore` 中为错误方案放开的 `src/assets/exercises` 规则，应随最终方案修正。如果采用构建前同步，`src/assets/exercises` 应恢复为忽略的生成目录。
4. `docs/agent-notes/build-release.md` 不是无用文件，应该保留，但必须更新为最终确定的单一资源源、LFS 拉取、构建前同步和内层 APK 检查流程。
5. 不要删除 `98d5e74` 中已经实现的目标挑战/宏量 UI 功能；只针对已确认的误提交、重复资源、错误公式和错误发布产物清理。

推荐清理方案：

- Git/LFS 只跟踪 `assets/exercises/**`。
- 新增一个明确、可测试的构建前资源同步步骤，把根目录 `assets` 复制到 `src/assets`；同步目录作为生成物，不提交到 Git。
- 构建脚本先验证 `git lfs pull` 后文件不是指针，再同步资源，再启动 Flet 构建。
- 在全新临时检出目录验证：克隆/检出 -> `git lfs pull` -> 运行同步 -> 构建 -> 检查 APK 内层 ZIP。只有该链路通过，才说明 `main` 已清干净且仍可复现构建。

清理分支验证通过后，再由用户确认是否合并；不得直接向 `main` push，禁止 force-push 和历史重写。

## 二、当前工作树状态（不要丢弃）

`git status --short` 当前约 2654 项修改：

- `.gitattributes`：新增 `src/assets/exercises/** filter=lfs diff=lfs merge=lfs -text`。
- `docs/agent-notes/build-release.md`：补充了 LFS 指针检查、两套资源字节数一致检查和 APK 内层 ZIP 检查。
- `src/assets/exercises/**`：约 2649 个真实 GIF/JPG/JSON 文件，从 LFS 指针变成真实内容；不要还原。下一会话应在确认文件头和字节数后统一 `git add`，由新的 `.gitattributes` 让它们以 LFS 对象提交。
- `src/profile_views.py`：空挑战 CTA 放入 Row，并让卡片 `expand=True`，修复空状态卡不拉满挑战面板宽度。
- `src/profile_details_views.py`：性别第二按钮从 `?` 改为 `女`。
- `tests/test_profile_macro_and_measurements.py`：新增性别按钮静态回归断言。

不要用 `git reset --hard`、`git checkout --` 或任何批量还原命令清理这些修改。

## 三、已完成 UI 修复及证据

截图暴露的两个 UI 问题：

1. 没有进行中挑战时，空状态创建卡按内容宽度收缩，没有占满挑战面板；已通过 `Row` 包裹、`Container(expand=True)` 修复。
2. 性别选项第二个按钮被代码直接写成 `?`；已改成 `女`。这不是字体、数据或编码推断问题，而是源代码文案错误。

验证：

- `python.exe -m unittest discover -s tests -p 'test_profile_macro_and_measurements.py' -v`：13 passed。
- `python.exe -m py_compile src/profile_views.py src/profile_details_views.py tests/test_profile_macro_and_measurements.py`：通过。
- `git diff --check`：通过；只有 CRLF/LF 提示，没有 whitespace error。

尚未完成：

- 需要停止旧的 Flet 预览服务并用正式目录重启，刷新浏览器后真实点击确认空卡宽度和“女”按钮。当前残留的 `flet`/预览进程可能仍服务旧代码；不要仅刷新页面就认定源码已更新。
- 需要确认删除挑战后底部“已删除 3 项进行中挑战”的 Snackbar 是否按预期自动消失；截图中的提示可能只是旧操作遗留，不要误判为新 UI 错误。

## 四、自动宏量公式：未完成且不能用硬上限糊弄

当前 `src/nutrition_service.py` 的问题：

- `GOAL_CONFIG["增肌"]["calorie_factor"]` 的高/中/低碳日全部是 `1.10`，所以根本没有能量层面的碳循环。
- 自动公式先取 `TDEE * calorie_factor`，蛋白用去脂体重乘数、脂肪用体重乘数，再把剩余热量全部反推成碳水：
  `carb = (calorie_target - protein*4 - fat*9) / 4`。
- 以截图资料 61.5 kg、12.9% 体脂、175 cm、30 岁、高频训练为例，TDEE 约 2502 kcal，增肌日目标约 2752 kcal，因此得到约 480 g 碳水，即 7.8 g/kg。
- 这不是简单“加一个碳水上限”就能正确解决的问题。硬截断会让三大营养素热量和目标热量对不上。

下一会话必须先确定并实现一致的产品公式：

1. 明确高/中/低碳日分别使用什么能量系数；增肌不能把三种日型都写成 1.10。
2. 明确蛋白质基准是体重还是去脂体重，并让显示的乘数和实际计算基准一致。
3. 明确脂肪最低摄入策略；不能为了压碳水把脂肪无依据推高。
4. 碳水只能作为热量平衡的剩余项，或在采用固定碳水乘数时同步把日目标热量改为三大营养素实际热量；两者不能同时强行保持。
5. 增加自动宏量测试：完整资料、三种目标、三种日型、三大营养素热量闭合、目标切换、手动模式不被改写、空资料不计算、老用户默认减脂。
6. 用截图资料写一个明确回归样例，检查输出单位、实际克数和乘数，不允许只断言“有数值”。

前序用户已明确反对“只加上限”。因此下一会话不要未经说明加入 `min(carb, cap)` 这类补丁式截断。

## 五、APK/资源未完成收口

### 已确认的事实

- Flet 配置：`pyproject.toml` 使用 `[tool.flet.app] path = "src"`，所以构建器从 `src/assets` 收集应用资源。
- 根目录 `assets/exercises` 受 `assets/exercises/** filter=lfs` 管理；此前 `src/assets/exercises` 没有对应 LFS 规则，导致它被提交成约 130 字节的指针文本。
- 只统计 APK 最外层 ZIP 会得到 GIF/MP3/WAV 为 0；Flet 实际把 Python 应用和资源放在 `assets/flutter_assets/app/app.zip` 内层 ZIP。
- 错误 APK 内层 ZIP 的统计是：1324 GIF、2 MP3、1 WAV，但 GIF 总大小只有约 172 KB，平均约 130 字节，属于 LFS 指针假阳性。
- 真实资源已下载后：根目录与 `src/assets` 的训练资源各 2649 个、各约 155,007,984 字节；抽样 GIF 文件头为 `GIF89a`，示例文件约 92 KB。

### 下一会话固定构建流程

在 `D:\carbs-king` 执行，使用绝对路径，不使用临时 worktree：

```powershell
git lfs pull

$root = Get-ChildItem assets\exercises -Recurse -File | Measure-Object Length -Sum
$src = Get-ChildItem src\assets\exercises -Recurse -File | Measure-Object Length -Sum
# 必须验证两边 Count 和 Sum 完全一致；抽样 GIF 文件头必须是 GIF87a/GIF89a

chcp 65001
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
& "C:\Users\chenyanggggg\AppData\Local\Programs\Python\Python312\Scripts\flet.exe" build apk --verbose
```

由于单次前台工具等待约 64 秒，构建必须使用隐藏后台进程并写 stdout/stderr 日志，随后每次不超过 60 秒轮询。不能把工具超时当成 Android 构建失败，也不能让用户看到“等待审批”后无人处理。

构建结束后，用 Python 同时打开 APK 外层和 `assets/flutter_assets/app/app.zip` 内层，统计：

- GIF 数量与总原始字节数；
- MP3/WAV 数量与总原始字节数；
- `assets/exercises` 总文件数和总字节数。

只有真实 GIF 文件头正确、内层 ZIP 资源数和字节数与源目录一致、专项测试通过，才能替换 GitHub Release。当前 `v1.2.3` 上的 APK 必须被新包替换。

上传建议：

```powershell
gh release upload -R fivespeedbuck/carbs-king v1.2.3 .\build\apk\carbs_king.apk --clobber
gh api repos/fivespeedbuck/carbs-king/releases/tags/v1.2.3
```

用 `gh api` 查看资产，避免当前环境部分 `gh release view` 参数解析异常。上传前保存本地 APK SHA-256，上传后核对远端资产大小和 digest。

## 六、本会话全部踩坑复盘

### 1. 层级和会话分工失控

- 同一批任务出现重复目标挑战会话、旧宏量会话、不同负责人以及不同 worktree；正式目录已完成的代码曾被 UI/测试会话拿临时 worktree 判定为“未接入”。
- 子会话没有可靠地沿全局开发负责人链路交付，用户看不到应有的负责人对话，造成重复开发、重复检查和无效 token 消耗。
- 后续规则：项目经理只向唯一全局开发负责人下发；全局开发负责人在正式目录直接统筹开发/测试/UI；同一批次不创建多个写入者；除非用户明确要求，不创建 worktree。

### 2. 正式目录与临时目录混用

- 目标挑战曾在临时 worktree 通过 13 项测试，但正式目录缺 repository/storage/backup 接线；后来才同步修复。
- UI 预检先在不含 UI 接线的旧目录执行，得出了与正式目录相反的结论。
- 后续每次运行前必须打印并核对 cwd、`git status --short`、关键接线；正式验收只能在 `D:\carbs-king`。

### 3. 权限/审批被误判为代码阻断

- “完全访问权限”不等于每个子会话的 Windows 沙箱、worktree 写入层都可用；曾出现 `apply_patch` 的 sandbox helper 错误和正式目录 `Access is denied`。
- 不能反复重试、不能绕过审批，也不能把子会话等待审批当作用户还要再次授权；应由当前唯一负责人直接在正式目录检查环境，失败一次即记录证据并换安全路径或停止。

### 4. PowerShell 与长命令处理不当

- PowerShell 首次命令、脚本执行策略、临时 PATH 和工作区写入层曾互相混淆；`python`/`py` 不一定在 PATH，必须用绝对 Python 路径。
- `flet build apk` 和 `git lfs pull` 在前台运行超过约 64 秒会被工具层截断；命令可能仍在后台运行，也可能已被杀死，必须检查进程、日志、输出时间和文件大小后再判断。
- 后续长任务统一 `Start-Process -WindowStyle Hidden`，分别写 stdout/stderr，轮询间隔不超过 60 秒；结束时清理进程并核对端口/输出。

### 5. 编码问题

- 本机应按 UTF-8 工作。Flet 在 GBK 输出 `✅` 等字符时可能触发 `UnicodeEncodeError`；构建前必须 `chcp 65001`、`PYTHONUTF8=1`、`PYTHONIOENCODING=utf-8`。
- PowerShell 控制台显示大量中文乱码不一定代表源文件损坏；读取源文件和测试必须显式 `encoding="utf-8-sig"` 或用 UTF-8 工具。不要因控制台乱码去做大范围文案替换。

### 6. 资源检查出现两次假通过

- 第一次把“文件名数量”当作资源完整；LFS 指针只有约 130 字节，也会被计为 GIF。
- 第二次只统计 APK 外层 ZIP，当然得到 GIF/音频为 0；正确位置是内层 `app.zip`。
- 后续门禁必须同时检查：LFS 拉取状态、文件头、源目录总字节数、APK 内层 ZIP 数量/字节数，并抽样打开真实 GIF。

### 7. 构建成功被误当成可发布

- 旧 APK 命令显示 Successfully built，但资源缺失；之后还上传并替换了 GitHub Release。以后“构建命令成功”不等于交付通过，资源门禁、专项测试、APK 内容和 Release 远端 digest 都是发布前置条件。
- 70 MB 本身不是唯一判断；本项目真实资源约 155 MB，出现 70 MB 时必须阻断并查 LFS。

### 8. 预览进程和代码版本不同步

- 浏览器显示的 `?` 与工作树修改不一致，是因为预览服务仍运行旧代码；刷新页面不会重新加载 Python 源码。
- 预览前必须确认旧进程、端口和 cwd，先停止旧服务，再从正式目录以隔离数据目录启动单个服务；修改后必须重启服务并做真实点击验证。

### 9. 测试命令误用

- `python -m unittest tests.test_profile_macro_and_measurements` 失败，因为 `tests` 不是可导入包；这不是业务测试失败。
- 正确命令是：`python -m unittest discover -s tests -p 'test_profile_macro_and_measurements.py' -v`。下一会话报告必须区分“命令错误”和“代码失败”。

### 10. 中途结束造成任务状态不清

- 本会话先在回答工具超时问题后结束，用户误以为真实构建停止；之后重新开始又在构建中途收到停止指令。
- 后续收到停止后必须明确写出：已停止哪个进程、是否留下旧输出、哪些修改已落盘、哪些未完成；收到普通追问不能把正在进行的主任务静默结束。

## 七、下一会话推荐顺序

1. 只读核对正式目录、工作树和本文件；确认没有活动构建进程。
2. 先处理 `.gitattributes` 与真实 `src/assets/exercises` 的 LFS 状态；验证根目录和 `src` 字节数一致后提交资源规则/资源对象。
3. 完成宏量公式设计并补测试；不要用硬上限，必须让日型差异、热量目标和三大营养素计算规则一致。
4. 运行 profile 专项测试、nutrition 专项测试、全量测试（能跑则跑）、相关 `py_compile` 和 `git diff --check`。
5. 重新启动正式目录预览，验证空挑战卡全宽和性别“女”按钮；结束后关闭预览服务。
6. 使用 UTF-8 环境后台构建 APK；检查内层 ZIP 真实资源和 SHA-256。
7. 提交、推送；最后才用 `gh release upload --clobber` 替换 `v1.2.3`，远端核对大小和 digest。

## 八、禁止事项

- 不要使用临时 worktree 作为验收目录。
- 不要创建重复负责人/开发/测试/UI 会话。
- 不要在宏量公式未闭合前打包或发布。
- 不要只看 APK 文件大小、构建成功日志或文件名数量。
- 不要把当前 71,915,571 字节 APK 上传给用户。
- 不要还原当前真实 LFS 资源、UI 修复或测试修改。
- 不要使用 `git reset --hard`、`git checkout --` 清理工作树。
