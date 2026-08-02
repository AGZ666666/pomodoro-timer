"""检查更新:查询 GitHub Releases 最新版本(参考 electron-updater 的 GitHub provider)。

约定:查询成功且确实有新版本才返回结果;已是最新返回 None;
网络/解析失败抛异常,由调用方决定提示还是静默(自动检查一律静默)。
"""

import json
import re
import urllib.error
import urllib.request

REPO = "AGZ666666/pomodoro-timer"
REQUEST_TIMEOUT = 6.0
USER_AGENT = "PomodoroTimer-Updater/1.0"
# 本机网络工具普遍走 Clash 代理;无环境代理时用它兜底
FALLBACK_PROXY = "http://127.0.0.1:7897"


def parse_version(s: str) -> tuple:
    """把 'v1.2.3-beta' 解析为 (1, 2, 3),忽略预发布后缀;无法解析返回 (0, 0, 0)。"""
    m = re.match(r"[vV]?(\d+)(?:\.(\d+))?(?:\.(\d+))?", s or "")
    if not m:
        return (0, 0, 0)
    return tuple(int(g or 0) for g in m.groups())


def is_newer(latest: str, current: str) -> bool:
    return parse_version(latest) > parse_version(current)


def _fetch(url: str, token: str = "") -> bytes:
    """先按 urllib 默认(读环境变量代理)请求,失败则尝试本机 Clash 代理兜底。"""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as r:
            return r.read()
    except Exception:
        proxy = urllib.request.ProxyHandler({"http": FALLBACK_PROXY, "https": FALLBACK_PROXY})
        opener = urllib.request.build_opener(proxy)
        with opener.open(req, timeout=REQUEST_TIMEOUT) as r:
            return r.read()


def check_update(current: str, repo: str = REPO, token: str = "") -> dict | None:
    """查询最新 Release。

    返回 {"version": "1.1.0", "url": ".../releases/tag/v1.1.0"} 表示有新版本;
    None 表示已是最新(或仓库尚无 Release);
    网络/解析失败抛异常(私有仓库 401 亦在此列)。
    """
    url = f"https://api.github.com/repos/{repo}/releases/latest"
    raw = _fetch(url, token=token)
    data = json.loads(raw.decode("utf-8"))
    latest = data.get("tag_name", "")
    if not latest or not is_newer(latest, current):
        return None
    return {"version": latest.lstrip("vV"), "url": data.get("html_url", "")}
