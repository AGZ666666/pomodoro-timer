"""番茄钟入口:DPI 感知、装配、托盘生命周期。"""

import ctypes
import sys

import customtkinter as ctk

import config
import sound
import tray
from app import PomodoroApp
from timer_core import TimerCore


def _set_dpi_awareness() -> None:
    """建窗前开启 HiDPI 感知,避免文字模糊(失败时忽略)。"""
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def main() -> None:
    _set_dpi_awareness()

    cfg = config.load()
    # 轻拟物为统一浅色配色,固定 light 主题(theme 配置不再影响外观)
    ctk.set_appearance_mode("light")

    core = TimerCore(config.durations(cfg))

    # 预生成音量对应的铃声,避免完成提醒路径上的首次生成阻塞
    try:
        sound.ensure_chime(cfg["volume"])
    except Exception:
        pass

    root = ctk.CTk()
    app = PomodoroApp(root, cfg, core)

    # 托盘须在 root 创建后装配;失败则退化为关窗即退出
    app.tray = tray.create(app)

    root.mainloop()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback

        # 无控制台环境(打包版)下用消息框展示错误
        msg = traceback.format_exc()
        try:
            ctypes.windll.user32.MessageBoxW(None, msg, "番茄钟启动失败", 0x10)
        except Exception:
            pass
        sys.exit(1)
