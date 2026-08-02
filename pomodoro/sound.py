"""提示音:wave+math 程序化生成琶音 WAV,winsound 异步播放。

音量通过生成时的 PCM 幅度缩放实现(winsound 无音量控制 API);
文件名内嵌音量值,音量变更时按需重新生成,幂等且开销极小。
"""

import array
import math
import wave
from pathlib import Path

import winsound

import config

SAMPLE_RATE = 22050
NOTE_SECONDS = 0.4
# C5-E5-G5-C6 上行琶音
NOTES_HZ = (523.25, 659.25, 783.99, 1046.50)


def chime_path(volume: float) -> Path:
    """按音量取铃声文件路径(可能尚未生成)。"""
    v = max(0.0, min(1.0, volume))
    return config.config_dir() / "sounds" / f"chime_v{int(round(v * 100))}.wav"


def _generate(path: Path, volume: float) -> None:
    """生成单声道 16bit 22050Hz WAV:四个音符琶音,指数衰减包络。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    n = int(SAMPLE_RATE * NOTE_SECONDS)
    samples = array.array("h")
    for note_hz in NOTES_HZ:
        for i in range(n):
            t = i / SAMPLE_RATE
            # 指数衰减包络:0.35s 内衰减到约 8%
            samples.append(
                int(math.sin(2.0 * math.pi * note_hz * t) * math.exp(-t * 7.0) * volume * 32767.0)
            )
    with wave.open(str(path), "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(SAMPLE_RATE)
        f.writeframes(samples.tobytes())


def ensure_chime(volume: float) -> Path:
    """确保音量对应的铃声文件存在,返回其路径。"""
    path = chime_path(volume)
    if not path.exists():
        _generate(path, volume)
    return path


def play(volume: float) -> None:
    """异步播放铃声(不阻塞 UI);失败时静默忽略。"""
    try:
        path = ensure_chime(volume)
        winsound.PlaySound(
            str(path),
            winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT,
        )
    except (OSError, RuntimeError):
        pass


if __name__ == "__main__":
    # 手工测试:生成 0.5 音量铃声并播放
    import time

    play(0.5)
    time.sleep(2.5)
    print("播放完成:", chime_path(0.5))
