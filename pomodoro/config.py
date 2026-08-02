"""配置读写:JSON 存于 %APPDATA%\\PomodoroTimer\\config.json。"""

import json
import os
from pathlib import Path

APP_DIR_NAME = "PomodoroTimer"

DEFAULT_CONFIG = {
    "focus_minutes": 25,
    "short_break_minutes": 5,
    "long_break_minutes": 15,
    "rounds_before_long_break": 4,
    "sound_enabled": True,
    "volume": 0.8,
    "auto_start_next": True,
    "always_on_top": False,
    "theme": "system",  # system | light | dark
    "github_token": "",  # 私有仓库检查更新用(GitHub PAT,可留空)
}


def config_dir() -> Path:
    """配置目录:%APPDATA%\\PomodoroTimer(无该变量时回退项目旁 .config)。"""
    base = os.environ.get("APPDATA")
    if base:
        d = Path(base) / APP_DIR_NAME
    else:
        d = Path(__file__).resolve().parent / ".config"
    d.mkdir(parents=True, exist_ok=True)
    return d


def config_path() -> Path:
    return config_dir() / "config.json"


def load() -> dict:
    """读取配置,与默认值合并;损坏或缺失时回退默认值,绝不抛异常。"""
    cfg = dict(DEFAULT_CONFIG)
    try:
        with open(config_path(), "r", encoding="utf-8") as f:
            saved = json.load(f)
        if isinstance(saved, dict):
            cfg.update(saved)
    except (OSError, ValueError):
        pass
    return cfg


def save(cfg: dict) -> None:
    """原子写:临时文件 + os.replace。"""
    path = config_path()
    tmp = path.with_suffix(".json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def durations(cfg: dict) -> dict:
    """把配置键映射为 TimerCore 接受的时长字典(唯一映射处)。"""
    return {
        "focus": cfg["focus_minutes"],
        "short_break": cfg["short_break_minutes"],
        "long_break": cfg["long_break_minutes"],
        "rounds_before_long_break": cfg["rounds_before_long_break"],
    }
