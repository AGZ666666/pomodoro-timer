"""番茄钟主窗口:CTk 界面、拟物时钟、tick 循环、设置对话框、完成弹窗。"""

import math
import time
import tkinter as tk
from functools import lru_cache

import customtkinter as ctk
from PIL import Image, ImageDraw, ImageTk

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

# ---- 拟物钟表配色(钟面固定浅色,不随主题变,如真实时钟) ----
BEZEL_OUTER = "#565b62"     # 表圈暗环
BEZEL_HI = "#eef0f3"        # 表圈高光(左上)
BEZEL_SHADOW = "#2f3338"    # 表圈阴影(右下)
TRACK = "#9a9ea5"           # 进度槽
FACE_CENTER = (255, 255, 255)
FACE_EDGE = (227, 222, 210)
FACE_SHADOW = "#b3ada1"     # 钟面内阴影(下半圈)
TIME_COLOR = "#34383e"      # 时间文字(深灰)
TICK_MIN = "#9a948a"        # 分钟刻度
TICK_HOUR = "#5a554d"       # 整点刻度
DOT_INACTIVE = "#c7c1b6"    # 未完成轮次圆点
DOT_RIM = "#e8e3d8"         # 圆点托底

# 按钮配色 (底色, 悬停, 描边, 高光, 阴影)
BTN_MAIN_IDLE = ("#e74c3c", "#f05c4c", "#a93226", "#ffb8ad", "#8a2218")
BTN_MAIN_RUN = ("#f39c12", "#f7a92e", "#b9770e", "#ffe2a6", "#96700a")
BTN_MAIN_RESUME = ("#27ae60", "#33c06f", "#186a3b", "#a9e9c2", "#144e2e")
BTN_SECONDARY = ("#dcdee3", "#e6e8ec", "#a5a9b0", "#ffffff", "#82878e")
BTN_SECONDARY_FG = "#43464c"

FONT_FAMILY = "Microsoft YaHei UI"
TICK_MS = 200
RING_FULL_SWEEP = -359.9  # tk 全圆 arc 不渲染,需小于 360 的扫角
CLOCK = 250  # 时钟画布边长


@lru_cache(maxsize=4)
def _face_gradient(size: int, face_r: int) -> Image.Image:
    """钟面径向渐变贴图:中心白 → 边缘米灰(逐环填充,一次生成,缓存)。"""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    cx = cy = size // 2
    for r in range(face_r, 0, -2):
        k = (r / face_r) ** 2
        color = tuple(int(FACE_CENTER[i] + (FACE_EDGE[i] - FACE_CENTER[i]) * k) for i in range(3))
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(*color, 255))
    return img


def _center_on(win, parent) -> None:
    """把 Toplevel 窗口居中于父窗口。"""
    win.update_idletasks()
    x = parent.winfo_x() + (parent.winfo_width() - win.winfo_width()) // 2
    y = parent.winfo_y() + (parent.winfo_height() - win.winfo_height()) // 2
    win.geometry(f"+{max(0, x)}+{max(0, y)}")


class SkeuoButton:
    """Canvas 拟物按钮:圆角主体 + 顶部高光 + 底部阴影;悬停提亮,按下凹陷。"""

    def __init__(self, canvas, x, y, w, h, text, palette, fg, font, command) -> None:
        self.canvas = canvas
        self.x, self.y, self.w, self.h = x, y, w, h
        self.r = min(14, h // 3)  # 圆角半径
        self.text = text
        self.palette = palette  # (底色, 悬停, 描边, 高光, 阴影)
        self.fg = fg
        self.font = font
        self.command = command
        self._pressed = False
        self._hover = False
        self._items = []
        self._text_id = None
        self._redraw()

    # ---------- 绘制 ----------

    def _round_rect(self, x0, y0, x1, y1, **kw):
        """平滑多边形圆角矩形。"""
        r = self.r
        pts = [
            x0 + r, y0, x1 - r, y0, x1, y0, x1, y0 + r,
            x1, y1 - r, x1, y1, x1 - r, y1, x0 + r, y1,
            x0, y1, x0, y1 - r, x0, y0 + r, x0, y0,
        ]
        return self.canvas.create_polygon(pts, smooth=True, **kw)

    def _redraw(self) -> None:
        for it in self._items:
            self.canvas.delete(it)
        self._items = []
        c = self.canvas
        x, y, w, h = self.x, self.y, self.w, self.h
        base, hover, border, hi, shadow = self.palette
        fill = hover if self._hover else base
        if self._pressed:
            # 凹陷:主体下移 1px,高光移到下边,阴影压上边
            body_y, hi_y, sh_y, ty = y + 1, h - 3, 2, y + h // 2 + 1
        else:
            body_y, hi_y, sh_y, ty = y, 2, h - 3, y + h // 2
        self._items.append(self._round_rect(x, body_y, x + w, body_y + h,
                                            fill=fill, outline=border, width=1))
        # 顶部高光 / 底部阴影细线(浮雕感)
        self._items.append(c.create_line(x + self.r, body_y + hi_y, x + w - self.r,
                                         body_y + hi_y, fill=hi, width=1))
        self._items.append(c.create_line(x + self.r, body_y + sh_y, x + w - self.r,
                                         body_y + sh_y, fill=shadow, width=1))
        self._text_id = c.create_text(x + w // 2, ty, text=self.text,
                                      font=self.font, fill=self.fg)
        self._items.append(self._text_id)
        for it in self._items:
            c.tag_bind(it, "<Enter>", self._on_enter)
            c.tag_bind(it, "<Leave>", self._on_leave)
            c.tag_bind(it, "<Button-1>", self._on_press)
            c.tag_bind(it, "<ButtonRelease-1>", self._on_release)

    # ---------- 事件 ----------

    def _on_enter(self, _e) -> None:
        self._hover = True
        self._redraw()

    def _on_leave(self, _e) -> None:
        self._hover = False
        self._pressed = False
        self._redraw()

    def _on_press(self, _e) -> None:
        self._pressed = True
        self._redraw()

    def _on_release(self, _e) -> None:
        if not self._pressed:
            return
        self._pressed = False
        self._redraw()
        if self._hover:
            self.command()

    # ---------- 动态更新 ----------

    def set_text(self, text: str) -> None:
        self.text = text
        self.canvas.itemconfig(self._text_id, text=text)

    def set_palette(self, palette) -> None:
        self.palette = palette
        self._redraw()


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
        root.geometry("380x520")
        root.resizable(False, False)

        self._build_ui()
        self._apply_always_on_top(self.cfg["always_on_top"], save=False)
        root.protocol("WM_DELETE_WINDOW", self._on_close)
        self._sync_tick_loop()
        self._render()

    def _theme_frame_bg(self) -> str:
        """CTkFrame 主题底色(各 Canvas 与窗口同色,避免方形色块)。"""
        fg = ctk.ThemeManager.theme["CTkFrame"]["fg_color"]
        return fg[1] if self._dark else fg[0]

    # ---------- 界面搭建 ----------

    def _build_ui(self) -> None:
        self._canvases = []

        # 阶段标签
        self.phase_label = ctk.CTkLabel(
            self.root,
            text="",
            font=ctk.CTkFont(family=FONT_FAMILY, size=22, weight="bold"),
        )
        self.phase_label.pack(pady=(16, 4))

        # ---- 拟物时钟 ----
        self.clock_canvas = self._new_canvas(CLOCK, CLOCK)
        self.clock_canvas.pack()
        self._build_clock()

        # ---- 轮次圆点 ----
        self.dots_canvas = self._new_canvas(320, 24)
        self.dots_canvas.pack(pady=(10, 0))
        self._dot_items = []
        self._rebuild_dots(self.cfg["rounds_before_long_break"])

        # ---- 控制按钮(拟物) ----
        self.btns_canvas = self._new_canvas(360, 60)
        self.btns_canvas.pack(pady=(12, 0))
        self.start_btn = SkeuoButton(
            self.btns_canvas, 105, 8, 150, 44, "开始", BTN_MAIN_IDLE,
            "#ffffff", ctk.CTkFont(family=FONT_FAMILY, size=16, weight="bold"),
            self._on_start_pause,
        )
        self.reset_btn = SkeuoButton(
            self.btns_canvas, 25, 12, 70, 36, "重置", BTN_SECONDARY,
            BTN_SECONDARY_FG, ctk.CTkFont(family=FONT_FAMILY, size=13),
            self._on_reset,
        )
        self.skip_btn = SkeuoButton(
            self.btns_canvas, 265, 12, 70, 36, "跳过", BTN_SECONDARY,
            BTN_SECONDARY_FG, ctk.CTkFont(family=FONT_FAMILY, size=13),
            self._on_skip,
        )

        # ---- 底部:设置 + 置顶 ----
        bottom_row = ctk.CTkFrame(self.root, fg_color="transparent")
        bottom_row.pack(pady=(12, 12))
        self.settings_btn = ctk.CTkButton(
            bottom_row, text="设置", width=80, height=30,
            corner_radius=10,
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

    def _new_canvas(self, w: int, h: int) -> tk.Canvas:
        c = tk.Canvas(self.root, width=w, height=h, bg=self._frame_bg, highlightthickness=0)
        self._canvases.append(c)
        return c

    # ---------- 时钟绘制 ----------

    def _build_clock(self) -> None:
        c = self.clock_canvas
        cx = cy = CLOCK // 2
        # 表圈:暗色金属环 + 左上高光 / 右下阴影
        c.create_oval(12, 12, CLOCK - 12, CLOCK - 12, width=10, outline=BEZEL_OUTER)
        c.create_arc(12, 12, CLOCK - 12, CLOCK - 12, start=135, extent=70,
                     style="arc", width=2.5, outline=BEZEL_HI)
        c.create_arc(12, 12, CLOCK - 12, CLOCK - 12, start=315, extent=70,
                     style="arc", width=2.5, outline=BEZEL_SHADOW)
        # 进度槽 + 进度弧
        c.create_oval(22, 22, CLOCK - 22, CLOCK - 22, width=8, outline=TRACK)
        self._progress_arc = c.create_arc(22, 22, CLOCK - 22, CLOCK - 22,
                                          start=90, extent=0, style="arc", width=8,
                                          outline=PHASE_COLORS[Phase.FOCUS])
        # 钟面(径向渐变)+ 内阴影 / 内高光
        face_r = (CLOCK - 60) // 2
        self._face_img = ImageTk.PhotoImage(_face_gradient(CLOCK, face_r))
        c.create_image(0, 0, image=self._face_img, anchor="nw")
        c.create_arc(30, 30, CLOCK - 30, CLOCK - 30, start=15, extent=150,
                     style="arc", width=3, outline=FACE_SHADOW)
        c.create_arc(30, 30, CLOCK - 30, CLOCK - 30, start=195, extent=150,
                     style="arc", width=3, outline="#ffffff")
        # 刻度:60 个分钟刻度 + 12 个整点刻度
        self._draw_ticks(cx, cy)
        # 时间文字 + 小字装饰
        self._time_item = c.create_text(cx, cy - 2, text="25:00",
                                        font=(FONT_FAMILY, 40, "bold"), fill=TIME_COLOR)
        c.create_text(cx, cy + 36, text="POMODORO",
                      font=(FONT_FAMILY, 9), fill="#a49e92")

    def _draw_ticks(self, cx: int, cy: int) -> None:
        c = self.clock_canvas
        for i in range(60):
            ang = math.radians(90 + i * 6)  # 12 点方向起,顺时针
            if i % 5 == 0:  # 整点刻度:长而粗
                r_out, r_in, width, color = 91, 79, 2.5, TICK_HOUR
            else:  # 分钟刻度:短而细
                r_out, r_in, width, color = 88, 82, 1, TICK_MIN
            x1, y1 = cx + r_out * math.cos(ang), cy - r_out * math.sin(ang)
            x2, y2 = cx + r_in * math.cos(ang), cy - r_in * math.sin(ang)
            c.create_line(x1, y1, x2, y2, width=width, fill=color)

    # ---------- 轮次圆点 ----------

    def _draw_dot(self, idx: int, count: int, done: int, phase_color: str) -> list:
        """单个圆点:托底圆环 + 内圆 + 左上高光(拟物)。返回该圆点的画布元素列表。"""
        c = self.dots_canvas
        cx = 160 + (idx - (count - 1) / 2) * 36
        y = 12
        active = idx < done
        fill = phase_color if active else DOT_INACTIVE
        items = [
            c.create_oval(cx - 9, y - 9, cx + 9, y + 9, fill=DOT_RIM, outline=""),
            c.create_oval(cx - 6, y - 6, cx + 6, y + 6, fill=fill, outline=""),
        ]
        if active:
            items.append(c.create_arc(cx - 5, y - 5, cx + 5, y + 5, start=135, extent=100,
                                      style="arc", width=1.5, outline="#ffffff"))
        return items

    def _rebuild_dots(self, count: int) -> None:
        """按长休间隔轮数重建圆点行(设置变更后调用)。"""
        done = self.core.completed_focus_rounds()
        self._draw_dots(done, PHASE_COLORS[self.core.phase()])

    def _draw_dots(self, done: int, phase_color: str) -> None:
        for items in self._dot_items:
            for it in items:
                self.dots_canvas.delete(it)
        self._dot_items = []
        for i in range(self.cfg["rounds_before_long_break"]):
            self._dot_items.append(
                self._draw_dot(i, self.cfg["rounds_before_long_break"], done, phase_color)
            )

    # ---------- 显示更新 ----------

    def _render(self) -> None:
        """把 core 状态渲染到界面;仅时间/进度环每 tick 更新,其余按需重配。"""
        phase = self.core.phase()
        status = self.core.status()

        # 系统主题下 OS 亮暗翻转时刷新各 Canvas 底色
        dark = ctk.get_appearance_mode().lower() == "dark"
        if dark != self._dark:
            self._dark = dark
            self._frame_bg = self._theme_frame_bg()
            for cv in self._canvases:
                cv.configure(bg=self._frame_bg)

        # 阶段/状态相关项:仅在状态切换时重配
        if (phase, status) != self._last:
            self._last = (phase, status)
            done = self.core.completed_focus_rounds()
            self.phase_label.configure(text=PHASE_LABELS[phase], text_color=PHASE_COLORS[phase])
            self.clock_canvas.itemconfig(self._progress_arc, outline=PHASE_COLORS[phase])
            self._draw_dots(done, PHASE_COLORS[phase])
            if status is Status.RUNNING:
                self.start_btn.set_text("暂停")
                self.start_btn.set_palette(BTN_MAIN_RUN)
            elif status is Status.PAUSED:
                self.start_btn.set_text("继续")
                self.start_btn.set_palette(BTN_MAIN_RESUME)
            else:
                self.start_btn.set_text("开始")
                self.start_btn.set_palette(BTN_MAIN_IDLE)

        # 每 tick 必变:进度弧与时间
        remaining = int(self.core.remaining(self._now()))
        total = self.core.total()
        frac = 1.0 - (remaining / total) if total > 0 else 0.0
        self.clock_canvas.itemconfig(self._progress_arc, extent=RING_FULL_SWEEP * frac)
        self.clock_canvas.itemconfig(self._time_item, text=self._fmt(remaining))

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
        # 键必须是配置字典的真实键(focus_minutes 而非 focus)
        labels = [
            ("focus_minutes", "专注时长(分钟)"),
            ("short_break_minutes", "短休息时长(分钟)"),
            ("long_break_minutes", "长休息时长(分钟)"),
            ("rounds_before_long_break", "长休间隔(轮)"),
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
            focus = self._parse_int(self.entries["focus_minutes"], 1, 120)
            short = self._parse_int(self.entries["short_break_minutes"], 1, 60)
            long_ = self._parse_int(self.entries["long_break_minutes"], 1, 90)
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
            self.win, text=msg, text_color=PHASE_COLORS[Phase.FOCUS],
            font=ctk.CTkFont(family=FONT_FAMILY, size=12),
        ).pack(pady=(0, 6))

    def _close(self) -> None:
        try:
            self.win.grab_release()
        except Exception:
            pass
        self.win.destroy()
