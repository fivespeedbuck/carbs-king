# 开发协作总结

## AppState 的临时 UI 状态必须声明映射

- 现象：在“我”页首次展开身体围度时，Flet 页面报错 `profile_circumference_expanded` 并白屏。
- 根因：`AppState` 是受限的映射适配器；`state.get()` 对未声明键可返回默认值，但 `state[key] = value` 会在 `_bindings()` 中触发 `KeyError`。
- 处理：在对应的状态 dataclass 中声明临时 UI 字段，并在 `AppState._bindings()` 添加同名映射；本例使用 `ProfileState.circumference_expanded` 和 `profile_circumference_expanded`。
- 验证：覆盖首次展开、收起、无数据和历史数据；再用真实 Flet 页面点击复验。
- 预防：新增任何 `state["..."]` 写入前，先核对 `AppState._bindings()` 是否已有合法绑定；纯 UI 状态不写入持久化 profile 或 daily record。

## 真实验收必须运行在正式集成目录

- 现象：修复已在 Codex worktree 通过测试，但验收仍复现旧错误。
- 根因：验收预览运行在 `D:\carbs-king`，修复仅存在于临时 worktree，两个目录源码不同。
- 处理：以 `D:\carbs-king` 作为唯一正式集成与最终验收目录；同步时只应用已授权的最小文件差异，保留该目录其他未提交修改。
- 验证：预览前检查目标目录的关键绑定，专项测试和语法检查均在正式目录运行。
- 预防：启动 Flet/Web 验收前记录并核对 cwd；报告中明确开发、集成和验收目录，避免用旧工作树判定修复结果。

## APK 构建前先处理 PowerShell 执行策略拦截

- 现象：PowerShell 的 `AuthorizationManager` 拦截构建脚本，APK 打包进程并未真正启动；直接重复普通命令会持续失败。
- 根因：脚本执行受当前 PowerShell 执行策略限制，而不是 Android 构建本身失败。
- 处理：先确认 `pwsh` 是否可用；脚本被拦截时使用进程级 `powershell -ExecutionPolicy Bypass -File <script>`，不修改系统级执行策略。启动后核验实际构建进程、输出目录和日志，再判断是否重试。
- 验证：记录实际启动命令、构建进程是否出现、失败点和最终结果。
- 预防：该检查只用于项目经理已明确批准的未来构建任务；未经确认，不打包、不发布。

## 小范围 P0 快速路径

- 现象：单点白屏、`KeyError` 或表单按钮失效容易因重复开预览、多 worktree 和多人重复排查而扩大处理时间。
- 根因：小范围 P0 的根因通常集中，但未经约束的并行预览会引入目录、进程和环境差异。
- 处理：只由一名开发负责人直接在 `D:\carbs-king` 做最小修复；一名测试负责人运行相关专项和必要 `py_compile`；一名 UI 负责人仅用已初始化的隔离数据走一条最短真实点击路径。不得新建额外 worktree、重复启动预览或做范围外优化。
- 验证：预览启动和点击验收总时限为 10 分钟。成功时提供截图和结果；失败时立即停止、清理端口，并标记为“环境阻断”上报。只有首次修复失败或根因不清，才升级为复杂 P0 和多负责人并行。
- 预防：预览前确认正式目录、隔离数据和唯一负责人；不连续尝试多种后台启动技巧。

## 2026-07-28 围度展开 P0：开发侧可复现复盘

- 触发条件/前置数据：使用默认 `AppState` 打开“我”页；不依赖已保存围度，空围度数据同样触发。
- 最短复现：点击“查看身体围度” → `profile_controller.toggle_circumference()` 执行 `state["profile_circumference_expanded"] = not expanded` → 页面显示 `The application encountered an error: 'profile_circumference_expanded'`。
- 根因：`state.get("profile_circumference_expanded", False)` 可以返回默认值，但 `AppState.__setitem__()` 仅接受 `_bindings()` 中声明的键；该键没有绑定，首次写入抛出 `KeyError`。
- 修改/检查文件：修改 `src/app_state.py`，在 `ProfileState` 增加不持久化的 `circumference_expanded: bool = False`，并增加映射绑定；修改 `tests/test_profile_macro_and_measurements.py`，覆盖首次展开、收起、空围度与历史围度。只读检查 `src/profile_controller.py` 和 `src/profile_details_views.py`，确认回调和展示路径。
- 执行命令及结果：在 `D:\carbs-king` 运行 `python -m pytest -q tests/test_profile_macro_and_measurements.py`，结果 `8 passed`；运行 `python -m py_compile src/app_state.py src/profile_controller.py src/profile_details_views.py` 成功；`git diff --check` 成功。
- 真实 UI/截图证据：修复前已获得白屏错误文本；修复后真实点击未形成有效功能截图。浏览器预览首屏和初始化个人信息弹窗可渲染，但围度路径被环境异常及首次初始化弹窗阻断，不能作为 P0 修复通过证据。日志目录：`C:\Users\chenyanggggg\AppData\Local\Temp\carbs-king-formal-acceptance-20260728-151624`。
- 环境阻断：首次隔离启动的环境变量拼接失败，未形成隔离且未保存数据；正确隔离重启后浏览器从约 07:17 开始重复报告 `main.dart.wasm` 的泛化 `Exception`，无围度/P0 堆栈或可定位信息。该错误暂不能归因于本次修复。
- 端口与进程清理：已终止本次监听 PID `18352` 和启动链残留 PID `26668`；最终检查 `8765`、`8766`、`18765` 均无 `LISTENING`，未遗留本次 Flet 或 `src\\main.py` 预览进程。
- 提前拦截与恢复步骤：新增任意 `state["..."]` 写入时先补 `AppState._bindings()` 测试；下次 UI 复验需在 `D:\carbs-king`、已初始化的独立 `CARBS_KING_DATA_DIR`、单一预览服务下执行，并先确认浏览器无 `main.dart.wasm` 异常。恢复后按“首次展开、收起、空围度、历史围度”四步点击并保存截图；随后由测试/UI 负责人提供复盘，再创建 `docs/retrospectives/2026-07-28-circumference-expansion-p0.md` 的三方统一文档。

## 个人资料不可用伪默认值驱动计算

- 现象：空资料会被 `to_float(..., 默认值)` 静默替换为具体的体重、体脂、身高、年龄和运动习惯，进而生成看似真实的 BMR、TDEE 与宏量目标。
- 处理：新用户与清空资料使用空字段；营养服务明确返回 `is_ready`、缺失字段和提示信息。资料页、今日页与饮食页在未就绪时只提示完善资料，不生成目标数值或进度条。
- 兼容：已保存或导入的实际资料按原值读取；仅缺失字段使用空值，不迁移或覆盖现有用户数据。
- 验证：完整资料的计算测试需显式提供完整资料；空资料断言目标为空、自动倍数为空且评价为“待完善资料”。
