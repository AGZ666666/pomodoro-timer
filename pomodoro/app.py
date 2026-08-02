"""番茄钟主窗口:CTk 界面、拟物时钟、tick 循环、设置对话框、完成弹窗。"""

import math
import time
import tkinter as tk

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
FACE_HI = "#ffffff"         # 钟面内高光(上半圈)
FACE_SHADOW = "#b3ada1"     # 钟面内阴影(下半圈)
TIME_COLOR = "#34383e"      # 时间文字(深灰)
TICK_MIN = "#9a948a"        # 分钟刻度
TICK_HOUR = "#5a554d"       # 整点刻度
DOT_INACTIVE = "#c7c1b6"    # 未完成轮次圆点
DOT_RIM = "#e8e3d8"         # 圆点托底

# 按钮配色 (底色, 悬停, 描边, 高光, 阴影);开始按钮基色复用阶段红,单一来源
BTN_MAIN_IDLE = (PHASE_COLORS[Phase.FOCUS], "#f05c4c", "#a93226", "#ffb8ad", "#8a2218")
BTN_MAIN_RUN = ("#f39c12", "#f7a92e", "#b9770e", "#ffe2a6", "#96700a")
BTN_MAIN_RESUME = ("#27ae60", "#33c06f", "#186a3b", "#a9e9c2", "#144e2e")
BTN_SECONDARY = ("#dcdee3", "#e6e8ec", "#a5a9b0", "#ffffff", "#82878e")
BTN_SECONDARY_FG = "#43464c"
ERROR_COLOR = "#e74c3c"

# 状态 → 主按钮 (文案, 配色) 查表驱动
BTN_STATES = {
    Status.RUNNING: ("暂停", BTN_MAIN_RUN),
    Status.PAUSED: ("继续", BTN_MAIN_RESUME),
    Status.IDLE: ("开始", BTN_MAIN_IDLE),
}

FONT_FAMILY = "Microsoft YaHei UI"
TICK_MS = 200
RING_FULL_SWEEP = -359.9  # tk 全圆 arc 不渲染,需小于 360 的扫角
CLOCK = 250  # 时钟画布边长


def _face_gradient(size: int, face_r: int) -> Image.Image:
    """钟面径向渐变贴图:中心白 → 边缘米灰。逐环描边(2px 环带)而非整圆填充。"""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    cx = cy = size // 2
    for r in range(face_r, 0, -2):
        k = (r / face_r) ** 2
        color = tuple(int(FACE_CENTER[i] + (FACE_EDGE[i] - FACE_CENTER[i]) * k) for i in range(3))
        d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=(*color, 255), width=2)
    return img


def _center_on(win, parent) -> None:
    """把 Toplevel 窗口居中于父窗口。"""
    win.update_idletasks()
    x = parent.winfo_x() + (parent.winfo_width() - win.winfo_width()) // 2
    y = parent.winfo_y() + (parent.winfo_height() - win.winfo_height()) // 2
    win.geometry(f"+{max(0, x)}+{max(0, y)}")


class SkeuoButton:
    """Canvas 拟物按钮:圆角主体 + 顶部高光 + 底部阴影;悬停提亮,按下凹陷。

    几何在构造时创建一次(共享 tag 统一绑定事件),状态变化只做
    itemconfig/coords 增量更新,不重建画布对象。
    """

    def __init__(self, canvas, x, y, w, h, text, palette, fg, font, command) -> None:
        self.canvas = canvas
        self.x, self.y, self.w, self.h = x, y, w, h
        self.r = min(14, h // 3)  # 圆角半径
        self.text = text
        self.palette = palette  # (底色, 悬停, 描边, 高光, 阴影)
        self.fg = fg
        self.font = font
        self.command = command
        self._state = 0  # 0 常态 / 1 悬停 / 2 按下
        self._body = None
        self._hi_line = None
        self._sh_line = None
        self._text_id = None

        tag = f"skeuo-{id(self)}"
        c = self.canvas
        x0, y0, x1, y1 = x, y, x + w, y + h
        self._body = self._round_rect(x0, y0, x1, y1,
                                      fill=palette[0], outline=palette[2], width=1,
                                      tags=tag)
        self._hi_line = c.create_line(x0 + self.r, y0 + 2, x1 - self.r, y0 + 2,
                                      fill=palette[3], width=1, tags=tag)
        self._sh_line = c.create_line(x0 + self.r, y1 - 3, x1 - self.r, y1 - 3,
                                      fill=palette[4], width=1, tags=tag)
        self._text_id = c.create_text(x0 + w // 2, y0 + h // 2, text=text,
                                      font=font, fill=fg, tags=tag)
        # 事件只对 tag 绑定一次,重绘不再需要重绑
        c.tag_bind(tag, "<Enter>", self._on_enter)
        c.tag_bind(tag, "<Leave>", self._on_leave)
        c.tag_bind(tag, "<Button-1>", self._on_press)
        c.tag_bind(tag, "<ButtonRelease-1>", self._on_release)

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

    def _sync(self) -> None:
        """按当前状态增量更新:颜色走 itemconfig,1px 位移走 coords。"""
        c = self.canvas
        x, y, w, h = self.x, self.y, self.w, self.h
        base, hover, border, hi, shadow = self.palette
        pressed = self._state == 2
        dy = 1 if pressed else 0
        # 主体:按下时整体下移 1px
        pts = self._round_pts(x, y + dy, x + w, y + dy + h)
        c.coords(self._body, *pts)
        c.itemconfig(self._body,
                     fill=hover if self._state == 1 else base, outline=border)
        # 浮雕线:按下时高光移到下边、阴影压上边(凹陷)
        hi_y = h - 3 if pressed else 2
        sh_y = 2 if pressed else h - 3
        c.coords(self._hi_line, x + self.r, y + hi_y + dy, x + w - self.r, y + hi_y + dy)
        c.coords(self._sh_line, x + self.r, y + sh_y + dy, x + w - self.r, y + sh_y + dy)
        c.itemconfig(self._hi_line, fill=hi)
        c.itemconfig(self._sh_line, fill=shadow)
        # 文字同步位移
        c.coords(self._text_id, x + w // 2, y + h // 2 + dy)

    def _round_pts(self, x0, y0, x1, y1) -> tuple:
        r = self.r
        return (
            x0 + r, y0, x1 - r, y0, x1, y0, x1, y0 + r,
            x1, y1 - r, x1, y1, x1 - r, y1, x0 + r, y1,
            x0, y1, x0, y1 - r, x0, y0 + r, x0, y0,
        )

    # ---------- 事件 ----------

    def _on_enter(self, _e) -> None:
        if self._state == 0:
            self._state = 1
            self._sync()

    def _on_leave(self, _e) -> None:
        self._state = 0
        self._sync()

    def _on_press(self, _e) -> None:
        self._state = 2
        self._sync()

    def _on_release(self, _e) -> None:
        if self._state != 2:
            return  # 按下期间已拖出(leave 已把状态归零)
        self._state = 1  # 鼠标仍在按钮上
        self._sync()
        self.command()

    # ---------- 动态更新 ----------

    def set_state(self, text: str, palette) -> None:
        """一次更新文案与配色(内部一次增量同步,不重建)。"""
        self.text = text
        self.palette = palette
        self.canvas.itemconfig(self._text_id, text=text)
        self._sync()


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
                     style="arc", width=3, outline=FACE_HI)
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

    def _build_dots(self, count: int, done: int, phase_color: str) -> None:
        """创建轮次圆点行(每点 3 个元素:托底环/内圆/高光弧),并按当前状态着色。"""
        for items in self._dot_items:
            for it in items:
                self.dots_canvas.delete(it)
        self._dot_items = []
        c = self.dots_canvas
        for i in range(count):
            cx = 160 + (i - (count - 1) / 2) * 36
            y = 12
            inner = c.create_oval(cx - 6, y - 6, cx + 6, y + 6, outline="")
            hi = c.create_arc(cx - 5, y - 5, cx + 5, y + 5, start=135, extent=100,
                              style="arc", width=1.5, outline="#ffffff", state="hidden")
            self._dot_items.append([
                c.create_oval(cx - 9, y - 9, cx + 9, y + 9, fill=DOT_RIM, outline=""),
                inner,
                hi,
            ])
        self._update_dots(done, phase_color)

    def _update_dots(self, done: int, phase_color: str) -> None:
        """只做着色:内圆变色、高光弧显隐(不重建几何)。"""
        for i, (_, inner, hi) in enumerate(self._dot_items):
            active = i < done
            self.dots_canvas.itemconfig(inner, fill=phase_color if active else DOT_INACTIVE)
            self.dots_canvas.itemconfig(hi, state="normal" if active else "hidden")

    def _rebuild_dots(self, count: int) -> None:
        """设置变更(轮数变化)时重建圆点行几何。"""
        self._build_dots(count, self.core.completed_focus_rounds(),
                         PHASE_COLORS[self.core.phase()])

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
            self._update_dots(done, PHASE_COLORS[phase])
            text, palette = BTN_STATES[status]
            self.start_btn.set_state(text, palette)

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
            self.win, text=msg, text_color=ERROR_COLOR,
            font=ctk.CTkFont(family=FONT_FAMILY, size=12),
        ).pack(pady=(0, 6))

    def _close(self) -> None:
        try:
            self.win.grab_release()
        except Exception:
            pass
        self.win.destroy()
