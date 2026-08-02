# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概况

**始终使用简体中文回复**(项目所有界面、注释、文档均为中文)。

Windows 桌面番茄钟(Python + customtkinter),界面与注释均为简体中文。仓库根为 `D:\新建文件夹`,代码在 `pomodoro/` 子目录,该目录是 git 仓库根之外的应用目录——在 `pomodoro/` 内以扁平模块(非包)方式 import(`import config` 等),兼容 `py main.py` 与 PyInstaller。

## 常用命令

```bat
REM 安装依赖(本机直连 PyPI 会 SSL 断连,一律用阿里云镜像)
py -m pip install -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple/

REM 运行(注意:必须用 py,本机 python 别名是 MS Store 桩)
cd pomodoro && py main.py

REM 全部测试
cd pomodoro && py -m unittest discover -s tests -v

REM 单个测试
cd pomodoro && py -m unittest test_timer_core.TestTimerCore.test_skip_advances_phase_without_round_count -v

REM 打包 exe(dist\番茄钟\番茄钟.exe,整目录拷贝即分发)
build.bat
```

打包关键参数(缺失会静默失败或启动崩溃):`--onedir --noconsole --collect-all customtkinter --collect-submodules pystray --hidden-import pystray._win32`。

## 架构要点

- **timer_core.py — 纯状态机,无任何 GUI 依赖**。计时原理:`end = now + remaining`,每次 tick 由传入的 now 反算剩余 → `after()` 抖动不累计漂移;暂停暂存剩余,恢复重设 end。时钟一律 `time.monotonic()` 外部注入。`tick(now)` 到点返回刚完成的 `Phase`(且只触发一次)并推进节奏回到 IDLE,由调用方决定是否 `start()`。跳过不计轮次;进长休后轮次清零。测试用确定性假时钟,不碰 GUI。
- **app.py — 主窗口**。tick 循环是单条 `after(200ms)` 链,仅在 RUNNING 时存在(`_sync_tick_loop` 保证恰好一个调度);隐藏到托盘时跳过渲染。`_render()` 只在 `(phase, status)` 变化时重配按钮/标签/圆点,时间与进度环每 tick 更新。构造函数注入 `now=time.monotonic` 便于测试。完成流程顺序固定:声音 → 从托盘恢复窗口 → 置顶弹窗(单例,重建前先 destroy)→ 托盘气泡 → 按 `auto_start_next` 自动开始。
- **tray.py — 托盘线程安全规则**。pystray `icon.run()` 在 daemon 线程,菜单回调也跑在该线程,**所有 UI 操作必须经 `root.after(0, fn)` 编组**(`_marshal`),tkinter 非线程安全。托盘创建失败时 `create()` 返回 None,应用退化为"关窗即退出"。托盘须在 CTk root 创建之后装配(main.py 中)。
- **sound.py — 音量烘焙进 WAV**。winsound 无音量 API,音量经生成时的 PCM 幅度缩放实现;铃声按音量缓存(`chime_v{int(vol*100)}.wav`,幂等)。`winsound.PlaySound(..., SND_ASYNC | SND_NODEFAULT)` 异步播放不阻塞 UI。写入 `%APPDATA%\PomodoroTimer\sounds\`(不放在 exe 旁,避免只读目录问题)。
- **config.py — 配置读写**。JSON 存 `%APPDATA%\PomodoroTimer\config.json`,加载与默认值合并、损坏回退默认值(绝不抛异常);保存用临时文件 + `os.replace` 原子写。`config.durations()` 是配置键 → TimerCore 时长键的**唯一映射处**,新增时长设置必须改这里。
- **updater.py + version.py — 检查更新**(参考 electron-updater 的 GitHub Releases provider)。`APP_VERSION` 在 version.py,发布新版时改它并打 GitHub tag(vX.Y.Z)。`check_update()`:有新版本返回 `{"version","url"}`,已最新返回 None,网络/解析失败**抛异常**由调用方决定提示还是静默(启动 3s 后自动检查一律静默;手动按钮才弹窗)。网络请求先走环境代理再兜底 `127.0.0.1:7897`;私有仓库需在配置里填 `github_token`。
- **main.py — 装配顺序有依赖**:DPI 感知 → 主题 → 加载配置 → TimerCore → CTk root → PomodoroApp(UI 内挂 WM_DELETE_WINDOW)→ **tray.create(root 之后)** → mainloop。打包版无控制台,启动异常用 `MessageBoxW` 弹出。

## 已知行为(勿当 bug "修复")

- 计时基于 `time.monotonic`,计入系统休眠——笔记本休眠唤醒后若已到点会立即触发完成提醒。
- 跳过专注不计入长休轮次。
- 仓库根 `D:\新建文件夹` 含非 ASCII 字符,Python/PyInstaller 可处理;若某工具报错,拷到 `C:\pomodoro` 再试。

## 数据位置

- 配置:`%APPDATA%\PomodoroTimer\config.json`(无 APPDATA 时回退项目旁 `.config/`)
- 铃声:`%APPDATA%\PomodoroTimer\sounds\`(程序生成,零素材文件)

## 环境事实

- 网络工具(gh、pip 等)走代理 `127.0.0.1:7897`;gh CLI 在 `C:\Program Files\GitHub CLI\gh.exe`。
- Git 仓库根就是 `D:\新建文件夹` 本身(含 pomodoro 子目录),远程为 GitHub 私有仓库 `AGZ666666/pomodoro-timer`。
