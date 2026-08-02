"""系统托盘:pystray + PIL 程序绘番茄图标。

pystray 在 Windows 上以守护线程运行 icon.run();
托盘菜单回调运行在 pystray 线程,所有 UI 操作一律经 root.after(0, fn) 编组。
菜单文案/勾选读取的是 app 的简单属性(主线程维护,托盘线程只读,GIL 下安全)。
"""

import threading

import pystray
from PIL import Image, ImageDraw

from timer_core import Status


def _tomato_icon(size: int = 64) -> Image.Image:
    """程序绘制番茄图标:红圆 + 绿叶(零资源文件)。"""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    # 番茄主体
    d.ellipse((size * 0.12, size * 0.25, size * 0.88, size * 0.95), fill="#e74c3c")
    # 高光
    d.ellipse((size * 0.22, size * 0.32, size * 0.45, size * 0.50), fill="#f1948a")
    # 绿叶(三片星形)
    d.polygon(
        [
            (size * 0.50, size * 0.30), (size * 0.58, size * 0.10),
            (size * 0.60, size * 0.28), (size * 0.74, size * 0.14),
            (size * 0.68, size * 0.32), (size * 0.84, size * 0.26),
            (size * 0.66, size * 0.38), (size * 0.50, size * 0.34),
        ],
        fill="#27ae60",
    )
    return img


class TrayController:
    """封装托盘生命周期;失败(无托盘环境)时 create 返回 None,应用退化为关窗即退出。"""

    def __init__(self, app) -> None:
        self.app = app
        self.icon = pystray.Icon(
            "pomodoro-timer",
            _tomato_icon(),
            "番茄钟",
            menu=pystray.Menu(
                pystray.MenuItem(
                    lambda item: "显示窗口" if self.app.hidden else "隐藏窗口",
                    lambda: self._marshal(
                        self.app.show_from_tray if self.app.hidden else self.app.hide_to_tray
                    ),
                ),
                pystray.MenuItem(
                    lambda item: "暂停" if self._running() else "开始",
                    lambda: self._marshal(self.app._on_start_pause),
                ),
                pystray.MenuItem(
                    "置顶显示",
                    lambda: self._marshal(self.app._on_topmost_toggle),
                    checked=lambda item: self.app.cfg["always_on_top"],
                ),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("退出", lambda: self._marshal(self.app._real_quit)),
            ),
        )

    def _running(self) -> bool:
        return self.app.core.status() is Status.RUNNING

    def _marshal(self, fn) -> None:
        """把托盘线程中的调用编组回 tkinter 主线程。"""
        self.app.root.after(0, fn)

    def notify(self, title: str, message: str) -> None:
        try:
            self.icon.notify(message, title)
        except Exception:
            pass

    def stop(self) -> None:
        try:
            self.icon.stop()
        except Exception:
            pass

    def run(self) -> None:
        threading.Thread(target=self.icon.run, daemon=True).start()


def create(app) -> TrayController | None:
    """创建托盘(须在 CTk root 创建之后);失败返回 None。"""
    try:
        tc = TrayController(app)
        tc.run()
        return tc
    except Exception:
        return None
