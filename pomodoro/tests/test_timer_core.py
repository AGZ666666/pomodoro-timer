"""timer_core 状态机单元测试:注入确定性时钟,不涉及任何 GUI。"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from timer_core import Phase, Status, TimerCore

DUR = {
    "focus": 25,
    "short_break": 5,
    "long_break": 15,
    "rounds_before_long_break": 4,
}


class TestTimerCore(unittest.TestCase):
    def test_initial_state(self):
        c = TimerCore(DUR)
        self.assertIs(c.status(), Status.IDLE)
        self.assertIs(c.phase(), Phase.FOCUS)
        self.assertEqual(c.total(), 25 * 60)
        self.assertEqual(c.remaining(0.0), 25 * 60)
        self.assertEqual(c.completed_focus_rounds(), 0)

    def test_start_pause_resume_preserves_remaining(self):
        c = TimerCore(DUR)
        c.start(now=0.0)
        self.assertIs(c.status(), Status.RUNNING)
        # 运行 100 秒后暂停
        self.assertAlmostEqual(c.remaining(100.0), 1400.0)
        c.pause(now=100.0)
        self.assertIs(c.status(), Status.PAUSED)
        self.assertAlmostEqual(c.remaining(999.0), 1400.0)  # 暂停期间剩余不变
        # 恢复:再次经过 100 秒,剩余应为 1300
        c.start(now=100.0)
        self.assertAlmostEqual(c.remaining(200.0), 1300.0)

    def test_no_drift_over_many_ticks(self):
        c = TimerCore({**DUR, "focus": 1})
        c.start(now=0.0)
        evs = []
        # 每秒 tick 一次,共 90 秒,期间无抖动累计
        for t in range(90):
            ev = c.tick(now=float(t))
            if ev:
                evs.append(ev)
        self.assertEqual(len(evs), 1)
        self.assertIs(evs[0], Phase.FOCUS)
        self.assertIs(c.status(), Status.IDLE)
        self.assertIs(c.phase(), Phase.SHORT_BREAK)

    def test_completion_fires_exactly_once(self):
        c = TimerCore(DUR)
        c.start(now=0.0)
        self.assertIsNone(c.tick(now=1499.0))
        ev = c.tick(now=1500.0)
        self.assertIs(ev, Phase.FOCUS)
        self.assertIsNone(c.tick(now=1501.0))  # 已 IDLE,不再触发
        self.assertIsNone(c.tick(now=99999.0))

    def test_cadence_focus_short_break(self):
        c = TimerCore(DUR)
        # 专注 25min 完成 → 短休
        c.start(now=0.0)
        ev = c.tick(now=1500.0)
        self.assertIs(ev, Phase.FOCUS)
        self.assertIs(c.phase(), Phase.SHORT_BREAK)
        self.assertEqual(c.total(), 5 * 60)
        # 短休完成 → 专注
        c.start(now=1500.0)
        ev = c.tick(now=1800.0)
        self.assertIs(ev, Phase.SHORT_BREAK)
        self.assertIs(c.phase(), Phase.FOCUS)

    def test_fourth_focus_leads_to_long_break_and_resets_rounds(self):
        c = TimerCore(DUR)
        for i in range(4):
            self.assertEqual(c.completed_focus_rounds(), i)
            c.start(now=0.0)
            ev = c.tick(now=1500.0)
            self.assertIs(ev, Phase.FOCUS)
            if i < 3:
                self.assertIs(c.phase(), Phase.SHORT_BREAK)
                c.start(now=1500.0)
                c.tick(now=1800.0)  # 休息结束
        self.assertIs(c.phase(), Phase.LONG_BREAK)
        self.assertEqual(c.completed_focus_rounds(), 0)  # 进长休后轮次清零
        # 长休结束 → 专注
        c.start(now=0.0)
        ev = c.tick(now=900.0)
        self.assertIs(ev, Phase.LONG_BREAK)
        self.assertIs(c.phase(), Phase.FOCUS)

    def test_skip_advances_phase_without_round_count(self):
        c = TimerCore(DUR)
        c.start(now=0.0)
        c.skip()
        self.assertIs(c.status(), Status.IDLE)
        self.assertIs(c.phase(), Phase.SHORT_BREAK)
        self.assertEqual(c.completed_focus_rounds(), 0)
        c.skip()
        self.assertIs(c.phase(), Phase.FOCUS)

    def test_reset_restores_full_duration_keeps_phase(self):
        c = TimerCore(DUR)
        c.start(now=0.0)
        c.pause(now=600.0)
        c.reset()
        self.assertIs(c.status(), Status.IDLE)
        self.assertEqual(c.remaining(0.0), 25 * 60)
        self.assertIs(c.phase(), Phase.FOCUS)

    def test_set_durations_live_update(self):
        c = TimerCore(DUR)
        c.start(now=0.0)
        c.pause(now=600.0)  # 剩余 900
        c.set_durations({**DUR, "focus": 10})  # 新总长 600,剩余应被钳位到 600
        self.assertAlmostEqual(c.remaining(0.0), 600.0)
        self.assertEqual(c.total(), 600.0)
        # 恢复后按新时长走
        c.start(now=0.0)
        self.assertAlmostEqual(c.remaining(100.0), 500.0)

    def test_start_from_idle_uses_full_duration(self):
        c = TimerCore(DUR)
        c.start(now=0.0)
        self.assertAlmostEqual(c.remaining(0.0), 1500.0)


if __name__ == "__main__":
    unittest.main()
