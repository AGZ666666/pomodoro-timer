# 番茄钟 (Pomodoro Timer)

Windows 桌面番茄钟,Python + customtkinter。

## 功能

- 标准番茄钟循环:专注 25 分钟 → 短休 5 分钟,每 4 轮专注后长休 15 分钟
- 开始 / 暂停 / 重置 / 跳过
- 圆形进度环 + 轮次圆点(●●○○)+ 阶段配色(专注红 / 短休绿 / 长休蓝)
- 设置:专注/短休/长休时长、长休间隔轮数、提示音开关、音量、自动开始下一轮
- 系统托盘(关闭窗口即最小化到托盘)、窗口置顶
- 完成提醒:提示音 + 置顶弹窗 + 托盘气泡

## 运行(开发模式)

```bat
py -m pip install -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple/
py main.py
```

注意:本机 `python` 别名是 Microsoft Store 桩,须用 `py` 命令。

## 打包 exe

```bat
build.bat
```

或手动:

```bat
py -m PyInstaller --noconfirm --clean --noconsole --onedir --name 番茄钟 ^
  --collect-all customtkinter --collect-submodules pystray --hidden-import pystray._win32 ^
  main.py
```

产物:`dist\番茄钟\番茄钟.exe`,整个目录拷贝即可分发。

## 测试

```bat
cd pomodoro
py -m unittest discover -s tests -v
```

## 数据位置

- 配置:`%APPDATA%\PomodoroTimer\config.json`(损坏时自动回退默认值)
- 铃声:`%APPDATA%\PomodoroTimer\sounds\`(按音量自动生成,无需素材文件)

## 已知行为

- 笔记本休眠唤醒后,若计时已到点会立即触发完成提醒(monotonic 计时计入休眠)
- 跳过专注不会计入长休轮次
