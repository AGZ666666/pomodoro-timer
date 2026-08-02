"""番茄钟纯状态机:不依赖任何 GUI,时钟由外部注入,可确定性单测。"""

from enum import Enum


class Phase(Enum):
    FOCUS = "focus"
    SHORT_BREAK = "short_break"
    LONG_BREAK = "long_break"


class Status(Enum):
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"


class TimerCore:
    """计时核心。

    计时原理:记录 end = now + remaining,每次 tick 由 now 反算剩余,
    因此 after() 的抖动不影响精度(无漂移);暂停时暂存剩余秒数,
    恢复时重新设定 end。时钟一律用 time.monotonic() 传入。
    """

    def __init__(self, durations: dict) -> None:
        self._phase = Phase.FOCUS
        self._status = Status.IDLE
        self._rounds = 0  # 已完成专注轮数(用于长休判断)
        self._end = 0.0  # RUNNING 时的结束时间戳
        self._remaining = 0.0  # IDLE/PAUSED 时的剩余秒数
        self.set_durations(durations)
        self._remaining = self.total()  # 初始为当前阶段完整时长

    # ---------- 查询 ----------

    def status(self) -> Status:
        return self._status

    def phase(self) -> Phase:
        return self._phase

    def total(self) -> float:
        """当前阶段的完整时长(秒)。"""
        return self._total_for(self._phase)

    def remaining(self, now: float) -> float:
        """当前阶段剩余秒数。"""
        if self._status is Status.RUNNING:
            return max(0.0, self._end - now)
        return self._remaining

    def completed_focus_rounds(self) -> int:
        """本轮长休周期内已完成的专注轮数(0..rounds_before_long_break)。"""
        return self._rounds

    # ---------- 配置 ----------

    def set_durations(self, durations: dict) -> None:
        """热更新时长设置,保留当前阶段与剩余时间。"""
        self._durations = durations
        if self._status is not Status.RUNNING:
            self._remaining = min(self._remaining, self.total())

    def _total_for(self, phase: Phase) -> float:
        d = self._durations
        if phase is Phase.FOCUS:
            return d["focus"] * 60.0
        if phase is Phase.SHORT_BREAK:
            return d["short_break"] * 60.0
        return d["long_break"] * 60.0

    # ---------- 状态转移 ----------

    def start(self, now: float) -> None:
        """IDLE 或 PAUSED → RUNNING。"""
        if self._status is Status.RUNNING:
            return
        self._remaining = self.remaining(now)
        if self._remaining <= 0.0:
            self._remaining = self.total()
        self._end = now + self._remaining
        self._status = Status.RUNNING

    def pause(self, now: float) -> None:
        """RUNNING → PAUSED,暂存剩余秒数。"""
        if self._status is not Status.RUNNING:
            return
        self._remaining = self.remaining(now)
        self._status = Status.PAUSED

    def reset(self) -> None:
        """任意状态 → IDLE,剩余恢复当前阶段完整时长(阶段与轮次保留)。"""
        self._status = Status.IDLE
        self._remaining = self.total()

    def skip(self) -> None:
        """按节奏推进到下一阶段并回到 IDLE;不计入专注轮次。"""
        self._phase = self._next_phase(self._phase)
        self._status = Status.IDLE
        self._remaining = self.total()

    def tick(self, now: float) -> Phase | None:
        """推进时钟。到点返回刚完成的阶段并切换节奏(回到 IDLE);未到点返回 None。"""
        if self._status is not Status.RUNNING or now < self._end:
            return None
        # 到点,记录本次完成的阶段
        done = self._phase
        # 推进节奏:专注完成轮次 +1;进长休时清零轮次
        if done is Phase.FOCUS:
            self._rounds += 1
        next_phase = self._next_phase(done)
        if next_phase is Phase.LONG_BREAK:
            self._rounds = 0
        self._phase = next_phase
        self._status = Status.IDLE
        self._remaining = self.total()
        return done

    # ---------- 内部 ----------

    def _next_phase(self, phase: Phase) -> Phase:
        """按节奏求下一阶段(不修改轮次)。"""
        if phase is Phase.FOCUS:
            if self._rounds >= self._durations["rounds_before_long_break"]:
                return Phase.LONG_BREAK
            return Phase.SHORT_BREAK
        return Phase.FOCUS
