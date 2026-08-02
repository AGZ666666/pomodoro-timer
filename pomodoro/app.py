"""番茄钟主窗口:CTk 界面、环形进度、tick 循环、设置对话框、完成弹窗。"""

import time
import tkinter as tk

import customtkinter as ctk

import config
import sound
from timer_core import Phase, Status, TimerCore

# 各阶段主题色:专注红 / 短休绿 / 长休蓝
PHASE_COLORS = {
    Phase.FOCUS: "#e74c3c",
    Phase.SHORT_BREAK: "#2ecc71",
    Phase.LONG_BREAK: "#3498db",
}
PHASE_LABELS = {
    Phase.FOCUS: "专注",
    Phase.SHORT_BREAK: "短休息",
    Phase.LONG_BREAK: "长休息",
}
# 其余界面色:二元组为 (亮色, 暗色)
UI_COLORS = {
    "ring_base": ("#d6d6d6", "#3a3a3a"),
    "time_text": ("#1a1a1a", "#e5e5e5"),
    "dot_inactive": "#9a9a9a",
    "btn_start": ("#e74c3c", "#c0392b"),
    "btn_pause": ("#f39c12", "#e67e22"),
    "btn_resume": ("#27ae60", "#2ecc71"),
    "error": "#e74c3c",
}

FONT_FAMILY = "Microsoft YaHei UI"
TICK_MS = 200
RING_FULL_SWEEP = -359.9  # tk 全圆 arc 不渲染,需小于 360 的扫角


def _center_on(win, parent) -> None:
    """把 Toplevel 窗口居中于父窗口。"""
    win.update_idletasks()
    x = parent.winfo_x() + (parent.winfo_width() - win.winfo_width()) // 2
    y = parent.winfo_y() + (parent.winfo_height() - win.winfo_height()) // 2
    win.geometry(f"+{max(0, x)}+{max(0, y)}")


class PomodoroApp:
    def __init__(self, root: ctk.CTk, cfg: dict, core: TimerCore,
                 now=time.monotonic) -> None:
        self.root = root
        self.cfg = cfg
        self.core = core
        self._now = now  # 时钟注入:测试可传假时钟
        self.tray = None  # 由 main 装配;非 None 时关闭按钮隐藏到托盘
        self.hidden = False  # 是否隐藏到托盘(托盘线程只读此标志)
        self._after_id = None
        self._popup = None
        self._last = (None, None)  # 上次渲染的 (phase, status),避免重复 configure

        self._dark = ctk.get_appearance_mode().lower() == "dark"
        self._frame_bg = self._theme_frame_bg()

        root.title("番茄钟")
        root.geometry("360x470")
        root.resizable(False, False)

        self._build_ui()
        self._apply_always_on_top(self.cfg["always_on_top"], save=False)
        root.protocol("WM_DELETE_WINDOW", self._on_close)
        self._sync_tick_loop()
        self._render()

    def _theme_frame_bg(self) -> str:
        """CTkFrame 主题底色(环形 Canvas 与窗口同色)。"""
        fg = ctk.ThemeManager.theme["CTkFrame"]["fg_color"]
        return fg[1] if self._dark else fg[0]

    # ---------- 界面搭建 ----------

    def _build_ui(self) -> None:
        pad = {"padx": 16, "pady": 4}

        # 阶段标签
        self.phase_label = ctk.CTkLabel(
            self.root,
            text="",
            font=ctk.CTkFont(family=FONT_FAMILY, size=20, weight="bold"),
        )
        self.phase_label.pack(pady=(18, 0))

        # 环形进度 + 环内时间
        ring_wrap = ctk.CTkFrame(self.root, fg_color="transparent")
        ring_wrap.pack(pady=(10, 0))
        self.canvas = tk.Canvas(
            ring_wrap,
            width=170,
            height=170,
            highlightthickness=0,
            bg=self._frame_bg,
        )
        self.canvas.pack()
        self._ring_base = self.canvas.create_arc(
            10, 10, 160, 160, start=90, extent=RING_FULL_SWEEP, style="arc",
            width=9, outline=UI_COLORS["ring_base"][int(self._dark)],
        )
        self._ring_progress = self.canvas.create_arc(
            10, 10, 160, 160, start=90, extent=0, style="arc",
            width=9, outline=PHASE_COLORS[Phase.FOCUS],
        )
        self._time_item = self.canvas.create_text(
            85, 85, text="25:00",
            font=(FONT_FAMILY, 34, "bold"), fill=UI_COLORS["time_text"][int(self._dark)],
        )

        # 轮次圆点
        self.dots_frame = ctk.CTkFrame(self.root, fg_color="transparent")
        self.dots_frame.pack(pady=(8, 0))
        self._dots = []
        self._rebuild_dots(self.cfg["rounds_before_long_break"])

        # 控制按钮
        btn_row = ctk.CTkFrame(self.root, fg_color="transparent")
        btn_row.pack(pady=(16, 0))
        self.start_btn = ctk.CTkButton(
            btn_row, text="开始", width=110, height=38,
            font=ctk.CTkFont(family=FONT_FAMILY, size=15, weight="bold"),
            command=self._on_start_pause,
        )
        self.start_btn.pack(side="left", padx=5)
        self.reset_btn = ctk.CTkButton(
            btn_row, text="重置", width=70, height=38,
            font=ctk.CTkFont(family=FONT_FAMILY, size=14),
            command=self._on_reset,
        )
        self.reset_btn.pack(side="left", padx=5)
        self.skip_btn = ctk.CTkButton(
            btn_row, text="跳过", width=70, height=38,
            font=ctk.CTkFont(family=FONT_FAMILY, size=14),
            command=self._on_skip,
        )
        self.skip_btn.pack(side="left", padx=5)

        # 设置按钮 + 置顶勾选
        bottom_row = ctk.CTkFrame(self.root, fg_color="transparent")
        bottom_row.pack(pady=(14, 14))
        self.settings_btn = ctk.CTkButton(
            bottom_row, text="设置", width=70, height=32,
            font=ctk.CTkFont(family=FONT_FAMILY, size=13),
            command=self._open_settings,
        )
        self.settings_btn.pack(side="left", padx=6)
        self.topmost_var = ctk.BooleanVar(value=self.cfg["always_on_top"])
        self.topmost_box = ctk.CTkCheckBox(
            bottom_row, text="窗口置顶", variable=self.topmost_var,
            font=ctk.CTkFont(family=FONT_FAMILY, size=13),
            command=self._on_topmost_toggle,
        )
        self.topmost_box.pack(side="left", padx=6)

    def _rebuild_dots(self, count: int) -> None:
        """按长休间隔轮数重建圆点行(设置变更后调用)。"""
        for lbl in self._dots:
            lbl.destroy()
        self._dots = [
            ctk.CTkLabel(self.dots_frame, text="●", font=ctk.CTkFont(family=FONT_FAMILY, size=16))
            for _ in range(count)
        ]
        for lbl in self._dots:
            lbl.pack(side="left", padx=4)
        self._last = (None, None)  # 强制重渲染

    # ---------- 显示更新 ----------

    def _render(self) -> None:
        """把 core 状态渲染到界面;仅时间/进度环每 tick 更新,其余按需重配。"""
        phase = self.core.phase()
        status = self.core.status()

        # 系统主题下 OS 亮暗翻转时刷新 Canvas 底色与静态色
        dark = ctk.get_appearance_mode().lower() == "dark"
        if dark != self._dark:
            self._dark = dark
            self._frame_bg = self._theme_frame_bg()
            self.canvas.configure(bg=self._frame_bg)
            self.canvas.itemconfig(self._ring_base, outline=UI_COLORS["ring_base"][int(dark)])
            self.canvas.itemconfig(self._time_item, fill=UI_COLORS["time_text"][int(dark)])

        # 阶段/状态相关项:仅在状态切换时重配
        if (phase, status) != self._last:
            self._last = (phase, status)
            done = self.core.completed_focus_rounds()
            self.phase_label.configure(text=PHASE_LABELS[phase], text_color=PHASE_COLORS[phase])
            self.canvas.itemconfig(self._ring_progress, outline=PHASE_COLORS[phase])
            for i, lbl in enumerate(self._dots):
                lbl.configure(
                    text_color=PHASE_COLORS[phase] if i < done else UI_COLORS["dot_inactive"]
                )
            if status is Status.RUNNING:
                fg, hover = UI_COLORS["btn_pause"]
                self.start_btn.configure(text="暂停", fg_color=fg, hover_color=hover)
            elif status is Status.PAUSED:
                fg, hover = UI_COLORS["btn_resume"]
                self.start_btn.configure(text="继续", fg_color=fg, hover_color=hover)
            else:
                fg, hover = UI_COLORS["btn_start"]
                self.start_btn.configure(text="开始", fg_color=fg, hover_color=hover)

        # 每 tick 必变:时间与进度环
        remaining = int(self.core.remaining(self._now()))
        total = self.core.total()
        frac = 1.0 - (remaining / total) if total > 0 else 0.0
        self.canvas.itemconfig(self._ring_progress, extent=RING_FULL_SWEEP * frac)
        self.canvas.itemconfig(self._time_item, text=self._fmt(remaining))

    @staticmethod
    def _fmt(seconds: int) -> str:
        seconds = max(0, seconds)
        return f"{seconds // 60:02d}:{seconds % 60:02d}"

    # ---------- tick 循环 ----------

    def _sync_tick_loop(self) -> None:
        """确保恰好存在一个 tick 调度:运行中则调度,否则取消。"""
        if self._after_id is not None:
            try:
                self.root.after_cancel(self._after_id)
            except Exception:
                pass
            self._after_id = None
        if self.core.status() is Status.RUNNING:
            self._after_id = self.root.after(TICK_MS, self._tick)

    def _tick(self) -> None:
        self._after_id = None
        now = self._now()
        phase = self.core.tick(now)
        if phase is not None:
            self._on_complete(phase, now)
        elif self.root.state() != "withdrawn":
            self._render()  # 隐藏到托盘时跳过渲染,恢复/完成时再渲染
        self._sync_tick_loop()

    # ---------- 按钮动作 ----------

    def _on_start_pause(self) -> None:
        now = self._now()
        if self.core.status() is Status.RUNNING:
            self.core.pause(now)
        else:
            self.core.start(now)
        self._render()
        self._sync_tick_loop()

    def _on_reset(self) -> None:
        self.core.reset()
        self._render()
        self._sync_tick_loop()

    def _on_skip(self) -> None:
        self.core.skip()
        self._render()
        self._sync_tick_loop()

    def _on_topmost_toggle(self) -> None:
        self._apply_always_on_top(bool(self.topmost_var.get()))

    def _apply_always_on_top(self, on: bool, save: bool = True) -> None:
        self.cfg["always_on_top"] = on
        self.root.attributes("-topmost", bool(on))
        if self.topmost_var.get() != on:
            self.topmost_var.set(on)
        if save:
            config.save(self.cfg)

    # ---------- 完成流程 ----------

    def _on_complete(self, phase: Phase, now: float) -> None:
        # 1. 声音
        if self.cfg["sound_enabled"]:
            sound.play(self.cfg["volume"])
        # 2. 若隐藏到托盘,恢复窗口
        self.show_from_tray()
        # 3. 置顶弹窗(单例,防堆叠)
        self._show_popup(phase)
        # 4. 托盘气泡
        if self.tray is not None:
            try:
                self.tray.notify(*self._notify_text(phase))
            except Exception:
                pass
        # 5. 自动开始下一轮
        if self.cfg["auto_start_next"]:
            self.core.start(now)
        self._render()
        self._sync_tick_loop()

    def _notify_text(self, phase: Phase) -> tuple:
        if phase is Phase.FOCUS:
            return "专注结束", "该休息啦"
        return "休息结束", "开始下一轮专注吧"

    def _show_popup(self, phase: Phase) -> None:
        if self._popup is not None and self._popup.winfo_exists():
            self._popup.destroy()
        popup = ctk.CTkToplevel(self.root)
        self._popup = popup
        popup.title("提示")
        popup.attributes("-topmost", True)
        popup.resizable(False, False)
        popup.grab_set()  # 模态:需要点确定

        if phase is Phase.FOCUS:
            title = "专注结束!"
            next_phase = self.core.phase()
            minutes = int(self.core.total() // 60)
            if next_phase is Phase.LONG_BREAK:
                sub = f"开始长休息 {minutes} 分钟"
            else:
                sub = f"开始短休息 {minutes} 分钟"
        else:
            title = "休息结束!"
            sub = "开始下一轮专注"
        ctk.CTkLabel(
            popup, text=title,
            font=ctk.CTkFont(family=FONT_FAMILY, size=26, weight="bold"),
            text_color=PHASE_COLORS[phase],
        ).pack(padx=40, pady=(24, 4))
        ctk.CTkLabel(
            popup, text=sub,
            font=ctk.CTkFont(family=FONT_FAMILY, size=14),
        ).pack(padx=40, pady=(0, 8))
        ctk.CTkButton(
            popup, text="确定", width=120, height=34,
            font=ctk.CTkFont(family=FONT_FAMILY, size=14),
            command=lambda: (popup.grab_release(), popup.destroy()),
        ).pack(pady=(8, 22))

        _center_on(popup, self.root)

    # ---------- 设置对话框 ----------

    def _open_settings(self) -> None:
        SettingsDialog(self)

    # ---------- 托盘协作 ----------

    def show_from_tray(self) -> None:
        self.hidden = False
        self.root.deiconify()
        self.root.lift()

    def hide_to_tray(self) -> None:
        self.hidden = True
        self.root.withdraw()

    def _on_close(self) -> None:
        """点 X:有托盘则隐藏到托盘,否则退出。"""
        if self.tray is not None:
            self.hide_to_tray()
        else:
            self._real_quit()

    def _real_quit(self) -> None:
        if self.tray is not None:
            try:
                self.tray.stop()
            except Exception:
                pass
        self.root.destroy()


class SettingsDialog:
    """设置对话框:时长/轮次/声音/音量/自动开始。"""

    def __init__(self, app: PomodoroApp) -> None:
        self.app = app
        self.cfg = app.cfg
        win = ctk.CTkToplevel(app.root)
        self.win = win
        win.title("设置")
        win.resizable(False, False)
        win.transient(app.root)
        win.grab_set()

        pad = {"padx": 18, "pady": 5}
        entries = {}
        labels = [
            ("focus", "专注时长(分钟)"),
            ("short_break", "短休息时长(分钟)"),
            ("long_break", "长休息时长(分钟)"),
            ("rounds_before_long_break", "长休息间隔(轮)"),
        ]
        for key, label in labels:
            row = ctk.CTkFrame(win, fg_color="transparent")
            row.pack(fill="x", **pad)
            ctk.CTkLabel(
                row, text=label,
                font=ctk.CTkFont(family=FONT_FAMILY, size=13),
                width=150, anchor="w",
            ).pack(side="left")
            var = ctk.StringVar(value=str(self.cfg[key]))
            entry = ctk.CTkEntry(
                row, textvariable=var, width=80,
                font=ctk.CTkFont(family=FONT_FAMILY, size=13),
            )
            entry.pack(side="right")
            entries[key] = var
        self.entries = entries

        self.sound_var = ctk.BooleanVar(value=self.cfg["sound_enabled"])
        ctk.CTkCheckBox(
            win, text="提示声音", variable=self.sound_var,
            font=ctk.CTkFont(family=FONT_FAMILY, size=13),
        ).pack(anchor="w", **pad)

        self.volume_var = ctk.DoubleVar(value=self.cfg["volume"] * 100)
        vol_row = ctk.CTkFrame(win, fg_color="transparent")
        vol_row.pack(fill="x", **pad)
        ctk.CTkLabel(
            vol_row, text="音量", width=150, anchor="w",
            font=ctk.CTkFont(family=FONT_FAMILY, size=13),
        ).pack(side="left")
        slider = ctk.CTkSlider(
            vol_row, from_=0, to=100, variable=self.volume_var, width=120,
            command=self._on_volume,
        )
        slider.pack(side="left", padx=(0, 8))
        self.vol_label = ctk.CTkLabel(
            vol_row, text=f"{int(self.volume_var.get())}%", width=40,
            font=ctk.CTkFont(family=FONT_FAMILY, size=12),
        )
        self.vol_label.pack(side="left")

        self.auto_var = ctk.BooleanVar(value=self.cfg["auto_start_next"])
        ctk.CTkCheckBox(
            win, text="自动开始下一轮", variable=self.auto_var,
            font=ctk.CTkFont(family=FONT_FAMILY, size=13),
        ).pack(anchor="w", **pad)

        btn_row = ctk.CTkFrame(win, fg_color="transparent")
        btn_row.pack(pady=(10, 16))
        ctk.CTkButton(
            btn_row, text="取消", width=90,
            font=ctk.CTkFont(family=FONT_FAMILY, size=13),
            command=self._close,
        ).pack(side="left", padx=8)
        ctk.CTkButton(
            btn_row, text="保存", width=90,
            font=ctk.CTkFont(family=FONT_FAMILY, size=13),
            command=self._save,
        ).pack(side="left", padx=8)

        _center_on(win, app.root)

    def _on_volume(self, value: float) -> None:
        self.vol_label.configure(text=f"{int(value)}%")

    def _save(self) -> None:
        try:
            focus = self._parse_int(self.entries["focus"], 1, 120)
            short = self._parse_int(self.entries["short_break"], 1, 60)
            long_ = self._parse_int(self.entries["long_break"], 1, 90)
            rounds = self._parse_int(self.entries["rounds_before_long_break"], 2, 8)
        except ValueError as e:
            self._error(str(e))
            return
        volume = float(self.volume_var.get()) / 100.0
        old_rounds = self.cfg["rounds_before_long_break"]
        self.cfg.update({
            "focus_minutes": focus,
            "short_break_minutes": short,
            "long_break_minutes": long_,
            "rounds_before_long_break": rounds,
            "sound_enabled": bool(self.sound_var.get()),
            "volume": volume,
            "auto_start_next": bool(self.auto_var.get()),
        })
        self.app.core.set_durations(config.durations(self.cfg))
        # 音量变更时预生成铃声,避免完成提醒路径上的首次生成阻塞
        sound.ensure_chime(volume)
        if rounds != old_rounds:
            self.app._rebuild_dots(rounds)
        config.save(self.cfg)
        self.app._render()
        self.app._sync_tick_loop()
        self._close()

    @staticmethod
    def _parse_int(var, lo: int, hi: int) -> int:
        try:
            v = int(var.get())
        except ValueError:
            raise ValueError(f"请输入 {lo}-{hi} 之间的整数")
        if not (lo <= v <= hi):
            raise ValueError(f"请输入 {lo}-{hi} 之间的整数")
        return v

    def _error(self, msg: str) -> None:
        ctk.CTkLabel(
            self.win, text=msg, text_color=UI_COLORS["error"],
            font=ctk.CTkFont(family=FONT_FAMILY, size=12),
        ).pack(pady=(0, 6))

    def _close(self) -> None:
        try:
            self.win.grab_release()
        except Exception:
            pass
        self.win.destroy()
