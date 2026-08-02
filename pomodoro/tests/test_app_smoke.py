"""UI 冒烟测试:真实 CTk 窗口上断言控件状态与 tick 行为(会短暂闪现窗口)。

用注入的假时钟驱动 PomodoroApp,消除真实时间带来的断言抖动。
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import customtkinter as ctk

import config
from app import PHASE_COLORS, PomodoroApp
from timer_core import Phase, Status, TimerCore


class FakeClock:
    """可手动拨动的时钟,替换 time.monotonic。"""

    def __init__(self) -> None:
        self.value = 0.0

    def __call__(self) -> float:
        return self.value


class TestAppSmoke(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        ctk.set_appearance_mode("dark")
        cls.cfg = dict(config.DEFAULT_CONFIG)
        cls.clock = FakeClock()
        cls.root = ctk.CTk()
        cls.app = PomodoroApp(cls.root, cls.cfg, TimerCore(config.durations(cls.cfg)),
                              now=cls.clock)
        cls.root.update()

    @classmethod
    def tearDownClass(cls):
        cls.root.destroy()

    def setUp(self):
        # 每个测试独立重置:销毁弹窗、重建 core、取消回调、重渲染
        if self.app._popup is not None and self.app._popup.winfo_exists():
            self.app._popup.destroy()
        self.app._popup = None
        self.clock.value = 0.0
        self.app.core = TimerCore(config.durations(self.cfg))
        self.app._sync_tick_loop()
        self.app._render()
        self.root.update()

    def test_window_title(self):
        self.assertEqual(self.root.title(), "番茄钟")

    def test_initial_render(self):
        self.assertEqual(self.app.phase_label.cget("text"), "专注")
        self.assertEqual(self.app.start_btn.text, "开始")
        self.assertEqual(
            self.app.clock_canvas.itemcget(self.app._time_item, "text"), "25:00"
        )

    def test_start_then_tick_updates_time_and_button(self):
        self.app._on_start_pause()  # 时钟 0 开始 → 结束于 1500
        self.root.update()
        self.assertEqual(self.app.start_btn.text, "暂停")
        self.clock.value = 1498.0
        self.app._tick()
        self.root.update()
        self.assertEqual(
            self.app.clock_canvas.itemcget(self.app._time_item, "text"), "00:02"
        )
        # 暂停回退
        self.app._on_start_pause()
        self.root.update()
        self.assertEqual(self.app.start_btn.text, "继续")

    def test_completion_shows_popup_and_advances_phase(self):
        # 时钟拨到专注结束点(auto_start_next 默认开启)
        self.app._on_start_pause()
        self.clock.value = 1500.0
        self.app._tick()
        self.root.update()
        self.assertIsNotNone(self.app._popup)
        self.assertTrue(self.app._popup.winfo_exists())
        self.assertIs(self.app.core.phase(), Phase.SHORT_BREAK)
        self.assertIs(self.app.core.status(), Status.RUNNING)  # 自动开始下一轮

    def test_always_on_top_toggle(self):
        self.app._apply_always_on_top(True)
        self.assertEqual(self.root.attributes("-topmost"), 1)
        self.app._apply_always_on_top(False)
        self.assertEqual(self.root.attributes("-topmost"), 0)

    def test_dots_reflect_rounds(self):
        # 完成一次专注 → 轮次圆点第 1 个内圆变为阶段色
        self.app._on_start_pause()
        self.clock.value = 1500.0
        self.app._tick()
        self.root.update()
        self.assertEqual(self.app.core.completed_focus_rounds(), 1)
        self.assertEqual(
            self.app.dots_canvas.itemcget(self.app._dot_items[0][1], "fill"),
            PHASE_COLORS[Phase.SHORT_BREAK],
        )


if __name__ == "__main__":
    unittest.main()
