"""
VTXT v3.0.0 — Final PySide6 build candidate
Current state:
- Dual independent countdown timers with accurate elapsed-time countdowns
- Timer-finished alarm playback with built-in WAV tones and custom media files
- Clickable, customizable keyboard/mouse hotkey pills
- Overlay pill: always-on-top, draggable, visible while a timer is running
- Overlay settings: visible/hidden, locked/unlocked, size, opacity, and hotkeys
- Timer settings: duration, alarm sound, custom file, volume, and hotkeys
- Save/Cancel behavior for timer and overlay settings
- Settings persistence via %LOCALAPPDATA%\\VTXT\\settings.json
- Runtime icon support via vtxt.ico and header banner support via vtxt_banner.png
"""

import sys
import os
import json
import time
import wave
import math
import struct
import tempfile
import platform
import ctypes
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QFrame, QSlider, QComboBox, QLineEdit,
    QSizePolicy, QStackedWidget, QFileDialog
)
from PySide6.QtCore import Qt, QTimer, QPointF, QUrl
from PySide6.QtGui import QFont, QColor, QPainter, QPen, QIntValidator, QPolygonF, QPixmap, QIcon

try:
    from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
except Exception:
    QAudioOutput = None
    QMediaPlayer = None

# ── Palette ───────────────────────────────────────────────────────────────────
BG_APP      = "#000000"
BG_SURFACE  = "#2e3333"
BG_CARD     = "#1a1d1d"
BG_INPUT    = "#0f1010"
BORDER_DIM  = "#555a5a"
BORDER_MID  = "#606666"
BORDER_HI   = "#707575"
TEXT_PRI    = "#d4d6d6"
TEXT_SEC    = "#7a7c7c"
TEXT_DIM    = "#353838"
TEXT_WARN   = "#f85149"
SEG_ON      = "#b0b4b4"   # brighter seg fill
SEG_WARN    = "#f85149"
SEG_OFF     = "#222525"   # slightly lighter off so it reads
VERSION     = "v3.0.0"
APP_NAME    = "VTXT"
APPDATA_DIR = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), APP_NAME)
SETTINGS_FILE = os.path.join(APPDATA_DIR, "settings.json")
ALARM_SOUND_OPTIONS = ("Default beep", "Soft chime", "Alert high", "Double beep", "Custom file")

STYLE = f"""
QWidget {{
    background-color: {BG_APP};
    color: {TEXT_PRI};
    font-family: "Segoe UI";
    font-size: 13px;
    border: none;
    outline: none;
}}
QLabel {{ background: transparent; border: none; }}
QMainWindow {{ background: {BG_APP}; }}
QPushButton {{
    background-color: {BG_SURFACE};
    color: {TEXT_PRI};
    border: 1px solid {BORDER_MID};
    border-radius: 6px;
    padding: 8px 14px;
    font-size: 13px;
}}
QPushButton:hover  {{ background-color: #383d3d; }}
QPushButton:pressed {{ background-color: #252929; }}
QPushButton#cancel {{
    background-color: {BG_INPUT};
    border: 1px solid #505555;
    color: #7a7c7c;
}}
QPushButton#cancel:hover {{ background-color: #1a1e1e; }}
QPushButton#hk_pill {{
    background-color: {BG_SURFACE};
    color: {TEXT_PRI};
    border: 1px solid #585e5e;
    border-radius: 3px;
    padding: 4px 12px;
    font-size: 12px;
    min-width: 80px;
    text-align: center;
}}
QPushButton#hk_pill:hover {{ border-color: {BORDER_HI}; color: {TEXT_PRI}; }}
QSlider {{ background: transparent; }}
QSlider::groove:horizontal {{
    height: 3px; background: #404545; border-radius: 2px;
}}
QSlider::sub-page:horizontal {{ background: #a0a6a6; border-radius: 2px; }}
QSlider::handle:horizontal {{
    width: 14px; height: 14px; margin: -6px 0;
    border-radius: 7px; background: {TEXT_PRI}; border: 2px solid {BG_APP};
}}
QComboBox {{
    background-color: {BG_CARD}; border: 1px solid #2e3030;
    border-radius: 3px; padding: 5px 10px;
    color: {TEXT_SEC}; font-size: 12px; min-width: 120px;
}}
QComboBox::drop-down {{ border: none; width: 20px; }}
QComboBox QAbstractItemView {{
    background-color: {BG_CARD}; border: 1px solid {BORDER_MID};
    color: {TEXT_SEC}; selection-background-color: {BG_SURFACE};
}}
QLineEdit {{
    background-color: {BG_INPUT}; border: 1px solid {BORDER_HI};
    border-radius: 5px; padding: 10px 18px;
    color: {TEXT_PRI}; font-size: 32px; font-weight: 400;
}}
QLineEdit:focus {{ border-color: #686a6a; }}
QScrollBar:vertical {{ background: transparent; width: 6px; margin: 0; }}
QScrollBar::handle:vertical {{ background: #2a2c2c; border-radius: 3px; min-height: 30px; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
"""


# ── Persistence ───────────────────────────────────────────────────────────────
def get_default_settings():
    return {
        "schema_version": 1,
        "app_name": APP_NAME,
        "timers": {
            "1": {
                "duration": 80,
                "alarm": {"sound": "Default beep", "volume": 45, "custom_file": ""},
                "hotkeys": {"timer1_toggle": "alt", "timer1_reset": "alt+r"},
            },
            "2": {
                "duration": 80,
                "alarm": {"sound": "Default beep", "volume": 45, "custom_file": ""},
                "hotkeys": {"timer2_toggle": "alt+2", "timer2_reset": "alt+t"},
            },
        },
        "overlay": {
            "visible": True,
            "unlocked": True,
            "size": 50,
            "opacity": 60,
            "hotkeys": {"overlay_visible": "alt+o", "overlay_lock": "alt+l"},
        },
    }


def _merge_dict(default, saved):
    if not isinstance(saved, dict):
        return default
    merged = dict(default)
    for key, default_value in default.items():
        if key not in saved:
            continue
        value = saved[key]
        if isinstance(default_value, dict):
            merged[key] = _merge_dict(default_value, value)
        else:
            merged[key] = value
    return merged


def load_app_settings():
    defaults = get_default_settings()
    try:
        if os.path.isfile(SETTINGS_FILE):
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
            return sanitize_app_settings(saved)
    except Exception:
        pass
    return sanitize_app_settings(defaults)


def save_app_settings(settings):
    try:
        os.makedirs(APPDATA_DIR, exist_ok=True)
        safe_settings = sanitize_app_settings(settings)
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(safe_settings, f, indent=2)
        return True
    except Exception:
        return False


def clamp_int(value, default, minimum, maximum):
    try:
        value = int(value)
    except Exception:
        value = default
    return max(minimum, min(maximum, value))


def coerce_bool(value, default=True):
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "on"}:
            return True
        if lowered in {"0", "false", "no", "off"}:
            return False
    return default


def sanitize_app_settings(settings):
    """Return a safe settings structure even if settings.json was edited or corrupted."""
    defaults = get_default_settings()
    settings = settings if isinstance(settings, dict) else {}
    merged = _merge_dict(defaults, settings)

    for num in ("1", "2"):
        timer = merged.get("timers", {}).get(num, {})
        default_timer = defaults["timers"][num]
        timer["duration"] = clamp_int(timer.get("duration", default_timer["duration"]), default_timer["duration"], 1, 5999)

        alarm = timer.get("alarm") if isinstance(timer.get("alarm"), dict) else {}
        sound = str(alarm.get("sound", default_timer["alarm"]["sound"]))
        if sound not in ALARM_SOUND_OPTIONS:
            sound = default_timer["alarm"]["sound"]
        alarm["sound"] = sound
        alarm["volume"] = clamp_int(alarm.get("volume", default_timer["alarm"]["volume"]), default_timer["alarm"]["volume"], 0, 100)
        custom_file = alarm.get("custom_file", "")
        alarm["custom_file"] = custom_file if isinstance(custom_file, str) else ""
        timer["alarm"] = alarm

        hotkeys = timer.get("hotkeys") if isinstance(timer.get("hotkeys"), dict) else {}
        safe_hotkeys = {}
        for action, default_hotkey in default_timer["hotkeys"].items():
            safe_hotkeys[action] = normalize_hotkey(hotkeys.get(action, default_hotkey)) or default_hotkey
        timer["hotkeys"] = safe_hotkeys
        merged["timers"][num] = timer

    overlay = merged.get("overlay") if isinstance(merged.get("overlay"), dict) else {}
    overlay_default = defaults["overlay"]
    overlay["visible"] = coerce_bool(overlay.get("visible", overlay_default["visible"]), overlay_default["visible"])
    overlay["unlocked"] = coerce_bool(overlay.get("unlocked", overlay_default["unlocked"]), overlay_default["unlocked"])
    overlay["size"] = clamp_int(overlay.get("size", overlay_default["size"]), overlay_default["size"], 0, 100)
    overlay["opacity"] = clamp_int(overlay.get("opacity", overlay_default["opacity"]), overlay_default["opacity"], 0, 100)

    overlay_hotkeys = overlay.get("hotkeys") if isinstance(overlay.get("hotkeys"), dict) else {}
    safe_overlay_hotkeys = {}
    for action, default_hotkey in overlay_default["hotkeys"].items():
        safe_overlay_hotkeys[action] = normalize_hotkey(overlay_hotkeys.get(action, default_hotkey)) or default_hotkey
    overlay["hotkeys"] = safe_overlay_hotkeys
    merged["overlay"] = overlay

    merged["schema_version"] = 1
    merged["app_name"] = APP_NAME
    return merged


def resource_path(filename):
    """Resolve bundled assets in dev and PyInstaller builds."""
    candidates = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.append(meipass)
    try:
        candidates.append(os.path.dirname(os.path.abspath(__file__)))
    except Exception:
        pass
    try:
        candidates.append(os.path.dirname(os.path.abspath(sys.argv[0])))
    except Exception:
        pass
    candidates.append(os.getcwd())

    seen = set()
    for base in candidates:
        if not base or base in seen:
            continue
        seen.add(base)
        path = os.path.join(base, filename)
        if os.path.exists(path):
            return path

    fallback_base = candidates[0] if candidates else os.getcwd()
    return os.path.join(fallback_base, filename)


def app_icon():
    path = resource_path("vtxt.ico")
    return QIcon(path) if os.path.exists(path) else QIcon()

# ── Helpers ───────────────────────────────────────────────────────────────────
def hline():
    f = QFrame()
    f.setFrameShape(QFrame.HLine)
    f.setFixedHeight(1)
    f.setStyleSheet(f"background:{BORDER_MID};border:none;")
    return f

def lbl(text, size=13, color=TEXT_PRI, bold=False):
    l = QLabel(text)
    s = f"color:{color};font-size:{size}px;background:transparent;border:none;"
    if bold: s += "font-weight:600;"
    l.setStyleSheet(s)
    return l

def sect_lbl(text):
    l = QLabel(text.upper())
    l.setStyleSheet(
        f"color:#6e7272;font-size:11px;letter-spacing:1.5px;"
        f"font-weight:500;background:transparent;border:none;"
    )
    return l

def sz_label(v):
    if v < 20: return "XS"
    if v < 40: return "S"
    if v < 60: return "M"
    if v < 80: return "L"
    return "XL"

def fmt(secs):
    s = max(0, math.ceil(secs))
    return f"{s//60:02d}:{s%60:02d}"

def parse_time(s):
    s = s.strip()
    if ':' in s:
        parts = s.split(':')
        return int(parts[0]) * 60 + int(parts[1])
    return int(s)

# ── Audio helpers ─────────────────────────────────────────────────────────────
# Adapted from the v2.x timer app, limited to the sound choices already present
# in this UI shell. Built-in sounds are generated as temporary WAV files.
BUILTIN_ALARMS = {
    "Default beep": {"freq": 880, "duration": 0.5, "type": "sine"},
    "Soft chime": {"freq": 523, "duration": 0.8, "type": "sine"},
    "Alert high": {"freq": 1200, "duration": 0.3, "type": "sine"},
    "Double beep": {"freq": 880, "duration": 0.2, "type": "double"},
}


def generate_tone_wav(freq: int, duration: float, tone_type: str, volume: float = 1.0):
    try:
        sample_rate = 44100
        base_amplitude = 16000
        amplitude = int(base_amplitude * max(0.0, min(1.0, volume)))
        samples = []

        if tone_type == "double":
            beep_samples = int(sample_rate * duration)
            gap_samples = int(sample_rate * 0.1)
            for _ in range(2):
                for i in range(beep_samples):
                    t = i / sample_rate
                    envelope = min(1.0, min(i, beep_samples - i) / (sample_rate * 0.02))
                    samples.append(int(amplitude * envelope * math.sin(2 * math.pi * freq * t)))
                samples.extend([0] * gap_samples)
        else:
            num_samples = int(sample_rate * duration)
            fade_samples = max(1, int(sample_rate * 0.05))
            for i in range(num_samples):
                t = i / sample_rate
                if i < fade_samples:
                    envelope = i / fade_samples
                elif i > num_samples - fade_samples:
                    envelope = (num_samples - i) / fade_samples
                else:
                    envelope = 1.0
                samples.append(int(amplitude * envelope * math.sin(2 * math.pi * freq * t)))

        temp_path = os.path.join(
            tempfile.gettempdir(),
            f"vertex_alarm_{tone_type}_{freq}_{int(volume * 100)}.wav"
        )
        with wave.open(temp_path, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            for sample in samples:
                wf.writeframesraw(struct.pack("<h", max(-32768, min(32767, sample))))
        return temp_path
    except Exception:
        return None


def adjust_wav_volume(input_path: str, volume: float):
    try:
        with wave.open(input_path, "rb") as wf:
            params = wf.getparams()
            frames = wf.readframes(params.nframes)

        sample_width = params.sampwidth
        adjusted_frames = bytearray()

        if sample_width == 1:
            for sample_byte in frames:
                sample = sample_byte - 128
                adjusted = max(-128, min(127, int(sample * volume))) + 128
                adjusted_frames.append(adjusted)
        elif sample_width == 2:
            for i in range(0, len(frames), 2):
                sample = struct.unpack("<h", frames[i:i + 2])[0]
                adjusted = max(-32768, min(32767, int(sample * volume)))
                adjusted_frames.extend(struct.pack("<h", adjusted))
        elif sample_width == 3:
            for i in range(0, len(frames), 3):
                b = frames[i:i + 3]
                if len(b) < 3:
                    break
                val = struct.unpack("<i", b + (b"\xff" if b[2] & 0x80 else b"\x00"))[0]
                adjusted = max(-8388608, min(8388607, int(val * volume)))
                adjusted_frames.extend(struct.pack("<i", adjusted)[:3])
        elif sample_width == 4:
            for i in range(0, len(frames), 4):
                sample = struct.unpack("<i", frames[i:i + 4])[0]
                adjusted = max(-2147483648, min(2147483647, int(sample * volume)))
                adjusted_frames.extend(struct.pack("<i", adjusted))
        else:
            return input_path

        temp_path = os.path.join(tempfile.gettempdir(), f"vertex_custom_{int(volume * 100)}.wav")
        with wave.open(temp_path, "wb") as wf:
            wf.setparams(params)
            wf.writeframes(bytes(adjusted_frames))
        return temp_path
    except Exception:
        return input_path


def play_wav_file(path: str) -> bool:
    try:
        import winsound
        winsound.PlaySound(path, winsound.SND_ASYNC | winsound.SND_FILENAME)
        return True
    except Exception:
        return False


def play_system_beep() -> bool:
    try:
        import winsound
        winsound.Beep(880, 600)
        return True
    except Exception:
        try:
            QApplication.beep()
            return True
        except Exception:
            return False


def play_alarm(sound_name: str, custom_path: str = "", volume: float = 0.7) -> bool:
    try:
        if sound_name == "Custom file" and custom_path and os.path.isfile(custom_path):
            # The v2.x playback path is WAV-based. Non-WAV selections are left
            # untouched for now rather than adding a new audio backend.
            if os.path.splitext(custom_path)[1].lower() == ".wav":
                wav_path = adjust_wav_volume(custom_path, volume)
                if wav_path and play_wav_file(wav_path):
                    return True

        config = BUILTIN_ALARMS.get(sound_name)
        if config:
            wav_path = generate_tone_wav(
                config["freq"], config["duration"], config["type"], volume
            )
            if wav_path and play_wav_file(wav_path):
                return True

        return play_system_beep()
    except Exception:
        return play_system_beep()


# ── Passive hotkeys ───────────────────────────────────────────────────────────
# Javelin-conscious design: this hotkey layer only reads Windows key/button
# state. It does not inject input, remap buttons, install drivers, or touch the
# game process. Saved hotkey assignments are restored through normal app
# settings only.
MODIFIER_KEYS = ("ctrl", "alt", "shift")
MOUSE_BUTTONS = {"mouse_left", "mouse_right", "mouse_middle", "mouse_x1", "mouse_x2"}

VK_CODES = {
    "mouse_left": 0x01,
    "mouse_right": 0x02,
    "mouse_middle": 0x04,
    "mouse_x1": 0x05,
    "mouse_x2": 0x06,
    "backspace": 0x08,
    "tab": 0x09,
    "enter": 0x0D,
    "shift": 0x10,
    "ctrl": 0x11,
    "alt": 0x12,
    "pause": 0x13,
    "capslock": 0x14,
    "esc": 0x1B,
    "space": 0x20,
    "pageup": 0x21,
    "pagedown": 0x22,
    "end": 0x23,
    "home": 0x24,
    "left": 0x25,
    "up": 0x26,
    "right": 0x27,
    "down": 0x28,
    "insert": 0x2D,
    "delete": 0x2E,
    "semicolon": 0xBA,
    "equals": 0xBB,
    "comma": 0xBC,
    "minus": 0xBD,
    "period": 0xBE,
    "slash": 0xBF,
    "grave": 0xC0,
    "leftbracket": 0xDB,
    "backslash": 0xDC,
    "rightbracket": 0xDD,
    "quote": 0xDE,
}

for _i in range(10):
    VK_CODES[str(_i)] = 0x30 + _i
for _i, _ch in enumerate("abcdefghijklmnopqrstuvwxyz"):
    VK_CODES[_ch] = 0x41 + _i
for _i in range(1, 13):
    VK_CODES[f"f{_i}"] = 0x70 + (_i - 1)

CAPTURE_SCAN_ORDER = (
    [f"f{i}" for i in range(1, 13)] +
    list("abcdefghijklmnopqrstuvwxyz") +
    [str(i) for i in range(10)] +
    [
        "space", "tab", "enter", "esc", "backspace", "delete", "insert",
        "home", "end", "pageup", "pagedown", "left", "right", "up", "down",
        "mouse_x1", "mouse_x2", "mouse_middle", "mouse_right", "mouse_left",
    ]
)

DISPLAY_NAMES = {
    "ctrl": "Ctrl",
    "alt": "Alt",
    "shift": "Shift",
    "mouse_left": "Mouse Left",
    "mouse_right": "Mouse Right",
    "mouse_middle": "Mouse Middle",
    "mouse_x1": "Mouse X1",
    "mouse_x2": "Mouse X2",
    "space": "Space",
    "tab": "Tab",
    "enter": "Enter",
    "esc": "Esc",
    "backspace": "Backspace",
    "delete": "Delete",
    "insert": "Insert",
    "home": "Home",
    "end": "End",
    "pageup": "Page Up",
    "pagedown": "Page Down",
    "left": "Left",
    "right": "Right",
    "up": "Up",
    "down": "Down",
    "semicolon": ";",
    "equals": "=",
    "comma": ",",
    "minus": "-",
    "period": ".",
    "slash": "/",
    "grave": "`",
    "leftbracket": "[",
    "backslash": "\\",
    "rightbracket": "]",
    "quote": "'",
}

KEY_ALIASES = {
    "control": "ctrl",
    "option": "alt",
    "escape": "esc",
    "return": "enter",
    "pgup": "pageup",
    "pgdn": "pagedown",
    "mouse1": "mouse_left",
    "mouse2": "mouse_right",
    "mouse3": "mouse_middle",
    "mouse4": "mouse_x1",
    "mouse5": "mouse_x2",
}


def _hotkey_supported():
    return platform.system() == "Windows" and hasattr(ctypes, "windll")


def _key_down(name: str) -> bool:
    if not _hotkey_supported():
        return False
    vk = VK_CODES.get(name)
    if vk is None:
        return False
    try:
        return bool(ctypes.windll.user32.GetAsyncKeyState(vk) & 0x8000)
    except Exception:
        return False


def normalize_hotkey(hotkey: str) -> str:
    parts = []
    for raw in str(hotkey or "").lower().replace(" ", "").split("+"):
        if not raw:
            continue
        key = KEY_ALIASES.get(raw, raw)
        if key in VK_CODES and key not in parts:
            parts.append(key)
    mods = [m for m in MODIFIER_KEYS if m in parts]
    rest = [p for p in parts if p not in MODIFIER_KEYS]
    return "+".join(mods + rest)


def hotkey_display(hotkey: str) -> str:
    hk = normalize_hotkey(hotkey)
    if not hk:
        return "None"
    labels = []
    for part in hk.split("+"):
        if len(part) == 1 and part.isalnum():
            labels.append(part.upper())
        elif part.startswith("f") and part[1:].isdigit():
            labels.append(part.upper())
        else:
            labels.append(DISPLAY_NAMES.get(part, part.title()))
    return " + ".join(labels)


def _hotkey_parts(hotkey: str):
    hk = normalize_hotkey(hotkey)
    return [p for p in hk.split("+") if p]


def _is_plain_modifier_hotkey(parts):
    return len(parts) == 1 and parts[0] in MODIFIER_KEYS


class HotkeyPill(QPushButton):
    """Clickable hotkey pill that captures keyboard keys or mouse buttons."""
    _active_capture = None

    def __init__(self, action_name: str, default_hotkey: str, on_changed=None, parent=None):
        super().__init__(parent)
        self._action_name = action_name
        self._hotkey = normalize_hotkey(default_hotkey)
        self._on_changed = on_changed
        self._listening = False
        self._capture_started = 0.0
        self._ignore_click_until = 0.0
        self._pending_mods = []
        self._had_modifier_only = False
        self._timer = QTimer(self)
        self._timer.setInterval(20)
        self._timer.timeout.connect(self._poll_capture)
        self.setObjectName("hk_pill")
        self.setCursor(Qt.PointingHandCursor)
        self.clicked.connect(self._start_capture)
        self.setText(hotkey_display(self._hotkey))

    def hotkey(self):
        return self._hotkey

    def set_hotkey(self, hotkey: str, notify=False):
        self._hotkey = normalize_hotkey(hotkey)
        self.setText(hotkey_display(self._hotkey))
        if notify and self._on_changed:
            self._on_changed(self._action_name, self._hotkey)

    def _start_capture(self):
        if self._listening or time.perf_counter() < self._ignore_click_until:
            return
        if HotkeyPill._active_capture and HotkeyPill._active_capture is not self:
            HotkeyPill._active_capture._cancel_capture()
        HotkeyPill._active_capture = self
        self._listening = True
        self._capture_started = time.perf_counter()
        self._pending_mods = []
        self._had_modifier_only = False
        self.setText("Press key / mouse...")
        self._timer.start()

    def _finish_capture(self, hotkey: str):
        if not self._listening:
            return
        self._timer.stop()
        self._listening = False
        if HotkeyPill._active_capture is self:
            HotkeyPill._active_capture = None
        self._ignore_click_until = time.perf_counter() + 0.25
        self.set_hotkey(hotkey, notify=True)

    def _cancel_capture(self):
        if not self._listening:
            return
        self._timer.stop()
        self._listening = False
        if HotkeyPill._active_capture is self:
            HotkeyPill._active_capture = None
        self.setText(hotkey_display(self._hotkey))

    def _poll_capture(self):
        if not self._listening:
            return
        elapsed = time.perf_counter() - self._capture_started
        if elapsed > 5.0:
            self._cancel_capture()
            return
        if not _hotkey_supported():
            self.setText("Windows only")
            if elapsed > 1.0:
                self._cancel_capture()
            return

        mods = [m for m in MODIFIER_KEYS if _key_down(m)]
        non_mods = []
        for name in CAPTURE_SCAN_ORDER:
            if name in MODIFIER_KEYS:
                continue
            if name == "mouse_left" and elapsed < 0.30:
                # Ignore the click that put the pill into listening mode.
                continue
            if _key_down(name):
                non_mods.append(name)

        if non_mods:
            self._finish_capture("+".join(mods + [non_mods[0]]))
            return

        if mods:
            self._pending_mods = mods
            self._had_modifier_only = True
            return

        if self._had_modifier_only and self._pending_mods:
            self._finish_capture("+".join(self._pending_mods))


class PassiveHotkeyManager:
    """Session-only passive hotkey detector using GetAsyncKeyState."""
    def __init__(self, parent, action_cb, interval_ms=15):
        self._action_cb = action_cb
        self._bindings = {}
        self._was_active = {}
        self._plain_modifier_down = {}
        self._plain_modifier_dirty = {}
        self._suppress_until_release = False
        self._timer = QTimer(parent)
        self._timer.setInterval(interval_ms)
        self._timer.timeout.connect(self._poll)

    def set_bindings(self, bindings: dict):
        normalized = {}
        for action, hotkey in (bindings or {}).items():
            hk = normalize_hotkey(hotkey)
            if hk:
                normalized[action] = hk
        self._bindings = normalized
        self._was_active = {action: False for action in normalized}
        self._plain_modifier_down = {action: False for action in normalized}
        self._plain_modifier_dirty = {action: False for action in normalized}

    def start(self):
        if _hotkey_supported() and self._bindings:
            self._timer.start()

    def stop(self):
        self._timer.stop()

    def refresh(self, bindings: dict):
        was_running = self._timer.isActive()
        self.stop()
        self.set_bindings(bindings)
        if was_running or _hotkey_supported():
            self.start()

    def suppress_until_all_released(self):
        self._suppress_until_release = True

    def _parts_down(self, parts):
        return bool(parts) and all(_key_down(p) for p in parts)

    def _any_non_modifier_down(self):
        for name in CAPTURE_SCAN_ORDER:
            if name not in MODIFIER_KEYS and _key_down(name):
                return True
        return False

    def _poll(self):
        if not _hotkey_supported():
            self.stop()
            return

        # Do not execute hotkey actions while a pill is capturing a new binding.
        if HotkeyPill._active_capture is not None:
            return

        if self._suppress_until_release:
            if any(_key_down(name) for name in list(MODIFIER_KEYS) + list(CAPTURE_SCAN_ORDER)):
                return
            self._suppress_until_release = False

        for action, hotkey in list(self._bindings.items()):
            parts = _hotkey_parts(hotkey)
            if not parts:
                continue

            # Plain modifier hotkeys, such as Alt, fire on a clean tap release.
            # This prevents Alt+R from also triggering an Alt-only binding.
            if _is_plain_modifier_hotkey(parts):
                mod = parts[0]
                down = _key_down(mod)
                if down:
                    if not self._plain_modifier_down.get(action, False):
                        self._plain_modifier_dirty[action] = False
                    if self._any_non_modifier_down():
                        self._plain_modifier_dirty[action] = True
                    self._plain_modifier_down[action] = True
                else:
                    if self._plain_modifier_down.get(action, False):
                        if not self._plain_modifier_dirty.get(action, False):
                            self._action_cb(action)
                    self._plain_modifier_down[action] = False
                    self._plain_modifier_dirty[action] = False
                continue

            active = self._parts_down(parts)
            if active and not self._was_active.get(action, False):
                self._action_cb(action)
            self._was_active[action] = active

def srow(left_w, right_w):
    row = QWidget()
    row.setObjectName("section_row")
    row.setFixedHeight(46)
    row.setStyleSheet("QWidget#section_row { background: transparent; }")
    lay = QHBoxLayout(row)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.addWidget(left_w)
    lay.addStretch()
    lay.addWidget(right_w)
    return row

def slider_row(label_text, default_pct=60, display_fn=None, show_value=True):
    row = QWidget()
    row.setObjectName("section_row")
    row.setFixedHeight(46)
    row.setStyleSheet("QWidget#section_row { background: transparent; }")
    lay = QHBoxLayout(row)
    lay.setContentsMargins(0, 8, 0, 8)
    lay.setSpacing(10)
    l = lbl(label_text, color=TEXT_SEC)
    l.setFixedWidth(56)
    lay.addWidget(l)
    sl = QSlider(Qt.Horizontal)
    sl.setRange(0, 100)
    sl.setValue(default_pct)
    sl.setCursor(Qt.PointingHandCursor)
    lay.addWidget(sl)
    if show_value:
        fn = display_fn or (lambda v: f"{v}%")
        val_l = lbl(fn(default_pct), size=12, color="#6a6c6c")
        val_l.setFixedWidth(34)
        val_l.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        lay.addWidget(val_l)
        sl.valueChanged.connect(lambda v: val_l.setText(fn(v)))
    return row, sl

def make_card(rows):
    card = QWidget()
    card.setObjectName("card")
    card.setStyleSheet(
        f"QWidget#card {{ background:{BG_CARD};border:1px solid {BORDER_DIM};border-radius:6px; }}"
    )
    card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
    lay = QVBoxLayout(card)
    lay.setContentsMargins(16, 0, 16, 0)
    lay.setSpacing(0)
    for i, r in enumerate(rows):
        lay.addWidget(r)
        if i < len(rows) - 1:
            lay.addWidget(hline())
    # Lock card to its exact content height so Qt cannot compress it
    card.setFixedHeight(lay.sizeHint().height())
    return card

# ── Time display ──────────────────────────────────────────────────────────────
class TimeDisplay(QWidget):
    def __init__(self, text="00:00", parent=None):
        super().__init__(parent)
        self._text = text
        self._warn = False
        self.setStyleSheet("background:transparent;")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setFixedHeight(74)

    def set_text(self, t):
        self._text = t
        self.update()

    def set_warning(self, w):
        self._warn = w
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        f = QFont("Consolas")
        f.setPixelSize(64)
        f.setWeight(QFont.Light)
        p.setFont(f)
        p.setPen(QColor(TEXT_WARN if self._warn else TEXT_PRI))
        p.drawText(self.rect(), Qt.AlignCenter, self._text)

# ── Smooth progress bar ───────────────────────────────────────────────────────
class SegBar(QWidget):
    """Solid smooth bar that drains from full to empty as the timer counts down."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(3)
        self.setStyleSheet("background:transparent;")
        self._pct = 1.0   # 0.0 to 1.0
        self._warn = False

    def set_pct(self, pct):
        self._pct = max(0.0, min(1.0, pct))
        self.update()

    def set_warning(self, w):
        self._warn = w
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        # Track
        p.setBrush(QColor(SEG_OFF))
        p.drawRoundedRect(0, 0, self.width(), 3, 1, 1)
        # Fill
        fill_w = int(self.width() * self._pct)
        if fill_w > 0:
            c = QColor(SEG_WARN if self._warn else SEG_ON)
            p.setBrush(c)
            p.drawRoundedRect(0, 0, fill_w, 3, 1, 1)

# ── Timer block — now with live functionality ─────────────────────────────────
class TimerBlock(QWidget):
    def __init__(self, number, settings_cb, overlay_cb=None, finish_cb=None, parent=None):
        super().__init__(parent)
        self._n = number
        self._settings_cb = settings_cb
        self._overlay_cb = overlay_cb
        self._finish_cb = finish_cb
        self._running = False
        self._total = 80   # 1:20 default for both timers
        self._remaining = self._total
        self._last_tick = None
        self._timer = QTimer()
        self._timer.setInterval(100)
        self._timer.timeout.connect(self._tick)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet(
            f"TimerBlock {{ background:{BG_CARD};"
            f"border:1px solid {BORDER_DIM}; border-radius:6px; }}"
        )
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        self._build()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 6, 6, 6)
        lay.setSpacing(0)

        # Digits
        self._time_disp = TimeDisplay(fmt(self._remaining))
        lay.addWidget(self._time_disp)
        lay.addSpacing(4)

        # Seg bar
        self._seg = SegBar()
        lay.addWidget(self._seg)
        lay.addSpacing(6)

        # Buttons
        brow = QHBoxLayout()
        brow.setSpacing(8)
        self._start_btn = QPushButton("Start")
        self._start_btn.setFixedHeight(40)
        self._start_btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._start_btn.setCursor(Qt.PointingHandCursor)
        self._start_btn.clicked.connect(self._toggle)
        brow.addWidget(self._start_btn)

        self._sec_btn = QPushButton("Settings")
        self._sec_btn.setFixedHeight(40)
        self._sec_btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._sec_btn.setCursor(Qt.PointingHandCursor)
        self._sec_btn.clicked.connect(self._action)
        brow.addWidget(self._sec_btn)
        lay.addLayout(brow)

    def _toggle(self):
        self._running = not self._running
        if self._running:
            if self._remaining <= 0:
                self._remaining = self._total
            self._last_tick = time.perf_counter()
            self._timer.start()
            self._start_btn.setText("Stop")
            self._sec_btn.setText("Reset")
            self._refresh()
        else:
            self._timer.stop()
            self._last_tick = None
            self._start_btn.setText("Start")
            self._sec_btn.setText("Settings")
            self._refresh()

    def _action(self):
        if self._running:
            self._timer.stop()
            self._last_tick = None
            self._running = False
            self._remaining = self._total
            self._start_btn.setText("Start")
            self._sec_btn.setText("Settings")
            self._refresh()
        else:
            self._settings_cb(self._n)

    def _tick(self):
        if not self._running:
            return

        now = time.perf_counter()
        if self._last_tick is None:
            self._last_tick = now
            return

        elapsed = now - self._last_tick
        self._last_tick = now
        self._remaining -= elapsed

        finished = False
        if self._remaining <= 0:
            self._remaining = 0
            self._timer.stop()
            self._last_tick = None
            self._running = False
            self._start_btn.setText("Start")
            self._sec_btn.setText("Settings")
            finished = True

        self._refresh()

        if finished and self._finish_cb:
            # Defer the alarm callback until after the UI finishes refreshing.
            QTimer.singleShot(0, self._finish_cb)

    def _refresh(self):
        warn = self._remaining <= 10 and self._remaining > 0 and self._total > 10
        self._time_disp.set_text(fmt(self._remaining))
        self._time_disp.set_warning(warn)
        pct = self._remaining / self._total if self._total > 0 else 0
        self._seg.set_pct(pct)
        self._seg.set_warning(warn)
        if self._overlay_cb:
            self._overlay_cb()

    def get_state(self):
        return {
            'text': fmt(self._remaining),
            'warn': self._remaining <= 10 and self._remaining > 0 and self._total > 10,
            'running': self._running
        }

    def get_total(self):
        return self._total

    def set_total(self, secs):
        secs = clamp_int(secs, 80, 1, 5999)
        was_running = self._running
        if was_running:
            self._timer.stop()
            self._running = False
        self._last_tick = None
        self._total = secs
        self._remaining = secs
        self._start_btn.setText("Start")
        self._sec_btn.setText("Settings")
        self._refresh()

    def toggle_hotkey(self):
        self._toggle()

    def reset_hotkey(self):
        self._timer.stop()
        self._last_tick = None
        self._running = False
        self._remaining = self._total
        self._start_btn.setText("Start")
        self._sec_btn.setText("Settings")
        self._refresh()

# ── Toggle with label ────────────────────────────────────────────────────────
class ToggleLabel(QPushButton):
    """A clickable toggle+label as a single QPushButton — no event routing issues."""
    def __init__(self, on_text="On", off_text="Off", checked=True, parent=None):
        super().__init__(parent)
        self._on_text = on_text
        self._off_text = off_text
        self._on = checked
        self.setCheckable(True)
        self.setChecked(checked)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(34)
        self.setMinimumWidth(110)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        self.setStyleSheet("background:transparent;border:none;text-align:left;padding:0;")
        self.clicked.connect(self._on_click)

    def _on_click(self):
        self._on = not self._on
        self.setChecked(self._on)
        self.update()

    def is_on(self):
        return self._on

    def set_on(self, value):
        self._on = bool(value)
        self.setChecked(self._on)
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        # Draw toggle pill
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#505252") if self._on else QColor("#1e2020"))
        if not self._on:
            p.setPen(QPen(QColor(BORDER_MID), 1))
        p.drawRoundedRect(0, 8, 34, 18, 9, 9)
        # Draw knob
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(TEXT_PRI) if self._on else QColor("#484a4a"))
        p.drawEllipse(19 if self._on else 3, 11, 12, 12)
        # Draw label text
        p.setPen(QColor(TEXT_SEC))
        f = self.font()
        f.setPixelSize(13)
        p.setFont(f)
        p.drawText(42, 0, self.width() - 42, self.height(), Qt.AlignVCenter,
                   self._on_text if self._on else self._off_text)


# ── Overlay settings dropdown ─────────────────────────────────────────────────
class OverlaySettingsDropdown(QWidget):
    def __init__(self, save_cb=None, toggle_cb=None, hotkey_changed_cb=None, parent=None):
        super().__init__(parent)
        self._expanded = False
        self._save_cb = save_cb
        self._toggle_cb = toggle_cb
        self._hotkey_changed_cb = hotkey_changed_cb
        self._edit_snapshot = None
        self._build()

    def _build(self):
        self._lay = QVBoxLayout(self)
        self._lay.setContentsMargins(0, 0, 0, 0)
        self._lay.setSpacing(8)

        self._btn = QPushButton("Overlay settings")
        self._btn.setFixedHeight(40)
        self._btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._btn.setCursor(Qt.PointingHandCursor)
        self._btn.clicked.connect(self._toggle)
        self._lay.addWidget(self._btn)

        self._drop = QWidget()
        self._drop.setVisible(False)
        self._drop.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        dlay = QVBoxLayout(self._drop)
        dlay.setContentsMargins(0, 0, 0, 0)
        dlay.setSpacing(8)

        self._vis_toggle = ToggleLabel("Visible", "Hidden", True)
        self._vis_toggle.clicked.connect(self._on_toggle_changed)
        self._hk_vis = HotkeyPill("overlay_visible", "alt+o", self._hotkey_changed_cb)

        self._lock_toggle = ToggleLabel("Unlocked", "Locked", True)
        self._lock_toggle.clicked.connect(self._on_toggle_changed)
        self._hk_lock = HotkeyPill("overlay_lock", "alt+l", self._hotkey_changed_cb)

        sz_r, self._sz_sl = slider_row("Size", 50, sz_label, show_value=False)
        op_r, self._op_sl = slider_row("Opacity", 60, show_value=False)
        self._sz_sl.valueChanged.connect(self._on_slider_changed)
        self._op_sl.valueChanged.connect(self._on_slider_changed)

        dlay.addWidget(make_card([
            srow(self._vis_toggle,  self._hk_vis),
            srow(self._lock_toggle, self._hk_lock),
            sz_r, op_r,
        ]))

        brow = QHBoxLayout()
        brow.setSpacing(8)
        cancel = QPushButton("Cancel")
        cancel.setObjectName("cancel")
        cancel.setFixedHeight(40)
        cancel.setCursor(Qt.PointingHandCursor)
        cancel.clicked.connect(self._cancel)
        save = QPushButton("Save")
        save.setFixedHeight(40)
        save.setCursor(Qt.PointingHandCursor)
        save.clicked.connect(self._save)
        brow.addWidget(cancel)
        brow.addWidget(save)
        dlay.addLayout(brow)
        self._lay.addWidget(self._drop)

    def _on_toggle_changed(self):
        """Toggles take effect immediately."""
        if self._toggle_cb:
            self._toggle_cb(
                self._vis_toggle.is_on(),
                self._lock_toggle.is_on()
            )

    def _on_slider_changed(self):
        """Sliders take effect immediately."""
        if self._toggle_cb:
            self._toggle_cb(
                self._vis_toggle.is_on(),
                self._lock_toggle.is_on(),
                self._sz_sl.value(),
                self._op_sl.value()
            )

    def _save(self):
        self.save_changes()

    def hotkey_bindings(self):
        return {
            "overlay_visible": self._hk_vis.hotkey(),
            "overlay_lock": self._hk_lock.hotkey(),
        }

    def get_settings(self, committed_only=False):
        if committed_only and self._edit_snapshot is not None:
            return self._edit_snapshot
        return self._snapshot_state()

    def set_settings(self, settings):
        self._restore_state(settings or {})

    def _snapshot_state(self):
        return {
            "visible": self._vis_toggle.is_on(),
            "unlocked": self._lock_toggle.is_on(),
            "size": self._sz_sl.value(),
            "opacity": self._op_sl.value(),
            "hotkeys": self.hotkey_bindings(),
        }

    def _apply_current_state(self):
        if self._toggle_cb:
            self._toggle_cb(
                self._vis_toggle.is_on(),
                self._lock_toggle.is_on(),
                self._sz_sl.value(),
                self._op_sl.value()
            )

    def _restore_state(self, state):
        if not state:
            return

        # Avoid slider valueChanged spam while restoring both values as one state.
        old_sz_blocked = self._sz_sl.blockSignals(True)
        old_op_blocked = self._op_sl.blockSignals(True)
        try:
            self._vis_toggle.set_on(coerce_bool(state.get("visible", True), True))
            self._lock_toggle.set_on(coerce_bool(state.get("unlocked", True), True))
            self._sz_sl.setValue(clamp_int(state.get("size", 50), 50, 0, 100))
            self._op_sl.setValue(clamp_int(state.get("opacity", 60), 60, 0, 100))
            hotkeys = state.get("hotkeys", {})
            self._hk_vis.set_hotkey(hotkeys.get("overlay_visible", self._hk_vis.hotkey()))
            self._hk_lock.set_hotkey(hotkeys.get("overlay_lock", self._hk_lock.hotkey()))
        finally:
            self._sz_sl.blockSignals(old_sz_blocked)
            self._op_sl.blockSignals(old_op_blocked)

        self._apply_current_state()
        if self._hotkey_changed_cb:
            self._hotkey_changed_cb("overlay_settings_restore", "")

    def begin_edit(self):
        self._edit_snapshot = self._snapshot_state()

    def save_changes(self):
        if self._save_cb:
            self._save_cb(
                self._vis_toggle.is_on(),
                self._lock_toggle.is_on(),
                self._sz_sl.value(),
                self._op_sl.value()
            )
        if self._hotkey_changed_cb:
            self._hotkey_changed_cb("overlay_settings_save", "")
        self._edit_snapshot = None
        self._close_dropdown()

    def cancel_changes(self):
        if self._edit_snapshot is not None:
            self._restore_state(self._edit_snapshot)
        self._edit_snapshot = None
        self._close_dropdown()

    def toggle_visibility_hotkey(self):
        self._vis_toggle.set_on(not self._vis_toggle.is_on())
        self._on_toggle_changed()

    def toggle_lock_hotkey(self):
        self._lock_toggle.set_on(not self._lock_toggle.is_on())
        self._on_toggle_changed()

    def is_expanded(self):
        return self._expanded

    def _toggle(self):
        self._expanded = True
        self._btn.setVisible(False)
        self._drop.setVisible(True)

    def _close_dropdown(self):
        self._expanded = False
        self._drop.setVisible(False)
        self._btn.setVisible(True)

    def _cancel(self):
        self.cancel_changes()

# ── Duration editor ───────────────────────────────────────────────────────────
class DurationEditor(QWidget):
    """Duration card with Edit/Done mode toggle and MM/SS editable text fields."""
    def __init__(self, default="1:20", on_set=None, parent=None):
        super().__init__(parent)
        self._secs = parse_time(default)
        self._on_set = on_set
        self._editing = False
        self._lay = QVBoxLayout(self)
        self._lay.setContentsMargins(0, 0, 0, 0)
        self._lay.setSpacing(0)
        self._build()
        self._set_mode(False)

    def _mm(self): return self._secs // 60
    def _ss(self): return self._secs % 60
    def _fmt_display(self):
        return f"{self._secs // 60}:{self._secs % 60:02d}"

    def get_seconds(self):
        if self._editing:
            self.commit_inputs()
        return self._secs

    def set_seconds(self, secs, notify=False):
        self._secs = clamp_int(secs, 80, 1, 5999)
        self._mm_input.setText(f"{self._mm():02d}")
        self._ss_input.setText(f"{self._ss():02d}")
        self._display_lbl.setText(self._fmt_display())
        if notify and self._on_set:
            self._on_set(self._secs)

    def commit_inputs(self):
        self._on_mm_committed()
        self._on_ss_committed()

    def _build(self):
        card = QWidget()
        card.setStyleSheet(
            f"background:{BG_CARD};border:1px solid {BORDER_DIM};border-radius:6px;"
        )
        card.setFixedHeight(68)
        clay = QHBoxLayout(card)
        clay.setContentsMargins(18, 0, 18, 0)
        clay.setSpacing(0)

        # Display label (display mode)
        self._display_lbl = QLabel(self._fmt_display())
        self._display_lbl.setStyleSheet(
            f"color:{TEXT_PRI};font-size:28px;background:transparent;border:none;"
        )
        clay.addWidget(self._display_lbl)

        # Input fields (edit mode)
        self._inputs = self._build_inputs()
        clay.addWidget(self._inputs)

        clay.addStretch()

        # Edit/Done toggle button
        self._toggle_btn = QPushButton("Edit")
        self._toggle_btn.setFixedSize(64, 34)
        self._toggle_btn.setCursor(Qt.PointingHandCursor)
        self._toggle_btn.setStyleSheet(f"""
            QPushButton {{
                background: {BG_SURFACE};
                border: 1px solid {BORDER_MID};
                color: {TEXT_PRI};
                border-radius: 5px;
                padding: 0;
                font-size: 12px;
            }}
            QPushButton:hover {{
                background: #383d3d;
                color: {TEXT_PRI};
                border-color: {BORDER_HI};
            }}
            QPushButton:pressed {{
                background: #252929;
            }}
        """)
        self._toggle_btn.clicked.connect(self._toggle_mode)
        clay.addWidget(self._toggle_btn)

        self._lay.addWidget(card)

    def _build_inputs(self):
        wrap = QWidget()
        wrap.setStyleSheet("background:transparent;border:none;")
        wlay = QHBoxLayout(wrap)
        wlay.setContentsMargins(0, 0, 0, 0)
        wlay.setSpacing(0)

        # MM input — 0..99
        self._mm_input = self._make_input(
            f"{self._mm():02d}",
            QIntValidator(0, 99, self),
            self._on_mm_committed,
        )
        wlay.addWidget(self._mm_input)

        # Colon separator
        colon = QLabel(":")
        colon.setStyleSheet(
            f"color:{TEXT_PRI};font-size:24px;"
            f"background:transparent;border:none;padding:0 8px;"
        )
        wlay.addWidget(colon)

        # SS input — 0..59
        self._ss_input = self._make_input(
            f"{self._ss():02d}",
            QIntValidator(0, 59, self),
            self._on_ss_committed,
        )
        wlay.addWidget(self._ss_input)

        return wrap

    def _make_input(self, text, validator, on_commit):
        inp = QLineEdit(text)
        inp.setValidator(validator)
        inp.setFixedSize(52, 34)
        inp.setAlignment(Qt.AlignCenter)
        inp.setMaxLength(2)
        inp.setStyleSheet(f"""
            QLineEdit {{
                background: {BG_INPUT};
                border: 1px solid {BORDER_MID};
                border-radius: 4px;
                color: {TEXT_PRI};
                font-size: 22px;
                padding: 0;
            }}
            QLineEdit:focus {{
                border-color: {BORDER_HI};
            }}
        """)
        inp.editingFinished.connect(on_commit)
        inp.returnPressed.connect(self._exit_edit)
        return inp

    def _on_mm_committed(self):
        txt = self._mm_input.text().strip()
        try:
            new_mm = int(txt) if txt else 0
        except ValueError:
            new_mm = self._mm()
        new_mm = max(0, min(99, new_mm))
        self._secs = new_mm * 60 + self._ss()
        self._mm_input.setText(f"{new_mm:02d}")
        if self._on_set:
            self._on_set(self._secs)

    def _on_ss_committed(self):
        txt = self._ss_input.text().strip()
        try:
            new_ss = int(txt) if txt else 0
        except ValueError:
            new_ss = self._ss()
        new_ss = max(0, min(59, new_ss))
        self._secs = self._mm() * 60 + new_ss
        self._ss_input.setText(f"{new_ss:02d}")
        if self._on_set:
            self._on_set(self._secs)

    def _toggle_mode(self):
        if self._editing:
            self._exit_edit()
        else:
            self._enter_edit()

    def _enter_edit(self):
        self._set_mode(True)
        self._mm_input.setFocus()
        self._mm_input.selectAll()

    def _exit_edit(self):
        # Force-commit both fields in case Done was clicked before blur
        self.commit_inputs()
        self._set_mode(False)

    def _set_mode(self, editing):
        self._editing = editing
        if editing:
            self._display_lbl.hide()
            self._mm_input.setText(f"{self._mm():02d}")
            self._ss_input.setText(f"{self._ss():02d}")
            self._inputs.show()
            self._toggle_btn.setText("Done")
        else:
            self._inputs.hide()
            self._display_lbl.setText(self._fmt_display())
            self._display_lbl.show()
            self._toggle_btn.setText("Edit")

# ── Combo box with custom chevron ────────────────────────────────────────────
class StyledComboBox(QComboBox):
    """QComboBox with a custom-painted chevron indicator. Flips when popup is open."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self._popup_open = False

    def showPopup(self):
        self._popup_open = True
        self.update()
        super().showPopup()

    def hidePopup(self):
        self._popup_open = False
        self.update()
        super().hidePopup()

    def paintEvent(self, e):
        super().paintEvent(e)
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        cx = self.width() - 12
        cy = self.height() // 2
        pen = QPen(QColor(TEXT_SEC), 1.4, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
        p.setPen(pen)
        if self._popup_open:
            # Up chevron
            p.drawLine(cx - 4, cy + 2, cx, cy - 2)
            p.drawLine(cx, cy - 2, cx + 4, cy + 2)
        else:
            # Down chevron
            p.drawLine(cx - 4, cy - 2, cx, cy + 2)
            p.drawLine(cx, cy + 2, cx + 4, cy - 2)
        p.end()


# ── Speaker icon (volume row indicator) ──────────────────────────────────────
class SpeakerIcon(QWidget):
    """Small custom-painted speaker icon for the volume row."""
    def __init__(self, color=None, parent=None):
        super().__init__(parent)
        self._color = QColor(color) if color else QColor(TEXT_SEC)
        self.setFixedSize(18, 14)
        self.setStyleSheet("background:transparent;")

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        # Speaker body + cone
        p.setPen(Qt.NoPen)
        p.setBrush(self._color)
        speaker = QPolygonF([
            QPointF(2, 5),
            QPointF(5, 5),
            QPointF(9, 2),
            QPointF(9, 12),
            QPointF(5, 9),
            QPointF(2, 9),
        ])
        p.drawPolygon(speaker)
        # Sound waves
        p.setPen(QPen(self._color, 1.2))
        p.setBrush(Qt.NoBrush)
        p.drawArc(10, 4, 3, 6, -50 * 16, 100 * 16)
        p.drawArc(13, 2, 4, 10, -50 * 16, 100 * 16)


# ── Alarm card ───────────────────────────────────────────────────────────────
class AlarmCard(QWidget):
    """Alarm settings card: Sound (with preview button), optional file picker, Volume."""
    SOUND_OPTIONS = list(ALARM_SOUND_OPTIONS)

    def __init__(self, on_layout_changed=None, parent=None):
        super().__init__(parent)
        self._sound = "Default beep"
        self._volume = 45
        self._custom_file = None
        self._on_layout_changed = on_layout_changed
        self._audio_output = None
        self._media_player = None
        if QAudioOutput is not None and QMediaPlayer is not None:
            self._audio_output = QAudioOutput(self)
            self._media_player = QMediaPlayer(self)
            self._media_player.setAudioOutput(self._audio_output)
        # Custom QWidget subclasses don't paint the stylesheet background by
        # default — this flag tells Qt to honor the background-color/border
        # rules in setStyleSheet below.
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setObjectName("alarm_card")
        self.setStyleSheet(
            f"QWidget#alarm_card {{ background:{BG_CARD};border:1px solid {BORDER_DIM};border-radius:6px; }}"
        )
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._build()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 0, 16, 0)
        lay.setSpacing(0)

        # Sound row
        lay.addWidget(self._build_sound_row())

        # Divider
        lay.addWidget(hline())

        # File row (hidden unless "Custom file" selected)
        self._file_row = self._build_file_row()
        self._file_row.setVisible(False)
        self._div_after_file = hline()
        self._div_after_file.setVisible(False)
        lay.addWidget(self._file_row)
        lay.addWidget(self._div_after_file)

        # Volume row
        lay.addWidget(self._build_volume_row())

    def _build_sound_row(self):
        row = QWidget()
        row.setObjectName("section_row")
        row.setFixedHeight(46)
        row.setStyleSheet("QWidget#section_row { background: transparent; }")
        lay = QHBoxLayout(row)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)

        l = lbl("Sound", color=TEXT_SEC)
        lay.addWidget(l)
        lay.addStretch()

        # Sound combo
        self._combo = StyledComboBox()
        for s in self.SOUND_OPTIONS:
            self._combo.addItem(s)
        # Center-align dropdown items
        for i in range(self._combo.count()):
            self._combo.setItemData(i, Qt.AlignCenter, Qt.TextAlignmentRole)
        self._combo.setStyleSheet(self._combo_style())
        self._combo.currentTextChanged.connect(self._on_sound_changed)
        lay.addWidget(self._combo)

        # Test preview button
        test_btn = QPushButton("Test")
        test_btn.setFixedSize(56, 28)
        test_btn.setCursor(Qt.PointingHandCursor)
        test_btn.setToolTip("Preview sound")
        test_btn.setStyleSheet(f"""
            QPushButton {{
                background: {BG_SURFACE};
                border: 1px solid {BORDER_MID};
                color: {TEXT_PRI};
                border-radius: 4px;
                padding: 0 12px;
                font-size: 11px;
            }}
            QPushButton:hover {{
                background: #383d3d;
                color: {TEXT_PRI};
                border-color: {BORDER_HI};
            }}
            QPushButton:pressed {{
                background: #252929;
            }}
        """)
        test_btn.clicked.connect(self._preview_sound)
        lay.addWidget(test_btn)

        return row

    def _combo_style(self):
        return f"""
            QComboBox {{
                background-color: {BG_SURFACE};
                border: 1px solid {BORDER_MID};
                border-radius: 3px;
                padding: 4px 24px 4px 10px;
                color: {TEXT_PRI};
                font-size: 12px;
                min-width: 95px;
                max-width: 105px;
            }}
            QComboBox:hover {{
                background-color: #383d3d;
                border-color: {BORDER_HI};
                color: {TEXT_PRI};
            }}
            QComboBox::drop-down {{
                border: none;
                width: 24px;
            }}
            QComboBox::down-arrow {{
                image: none;
                width: 0;
                height: 0;
            }}
            QComboBox QAbstractItemView {{
                background-color: {BG_SURFACE};
                border: 1px solid {BORDER_HI};
                border-radius: 5px;
                color: {TEXT_PRI};
                outline: none;
                padding: 4px;
            }}
            QComboBox QAbstractItemView::item {{
                padding: 6px 12px;
                border: 1px solid {BORDER_MID};
                border-radius: 3px;
                min-height: 22px;
                color: {TEXT_PRI};
                margin: 2px 0;
            }}
            QComboBox QAbstractItemView::item:hover {{
                background-color: #404545;
                color: {TEXT_PRI};
                border-color: {BORDER_HI};
            }}
            QComboBox QAbstractItemView::item:selected {{
                background-color: #404545;
                color: {TEXT_PRI};
                border-color: {BORDER_HI};
            }}
        """

    def _build_file_row(self):
        row = QWidget()
        row.setObjectName("section_row")
        row.setFixedHeight(46)
        row.setStyleSheet("QWidget#section_row { background: transparent; }")
        lay = QHBoxLayout(row)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)

        l = lbl("File", color=TEXT_SEC)
        lay.addWidget(l)
        lay.addStretch()

        # Path display
        self._file_path_lbl = QLabel("No file selected")
        self._file_path_lbl.setStyleSheet(
            f"color:#5a5e5e;font-size:12px;background:transparent;"
            f"border:none;font-style:italic;"
        )
        self._file_path_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        lay.addWidget(self._file_path_lbl)

        # Browse button
        browse_btn = QPushButton("Browse...")
        browse_btn.setFixedHeight(28)
        browse_btn.setCursor(Qt.PointingHandCursor)
        browse_btn.setStyleSheet(f"""
            QPushButton {{
                background: {BG_SURFACE};
                border: 1px solid {BORDER_MID};
                color: {TEXT_PRI};
                border-radius: 4px;
                padding: 0 12px;
                font-size: 11px;
            }}
            QPushButton:hover {{
                background: #383d3d;
                color: {TEXT_PRI};
                border-color: {BORDER_HI};
            }}
        """)
        browse_btn.clicked.connect(self._browse_file)
        lay.addWidget(browse_btn)

        return row

    def _build_volume_row(self):
        row = QWidget()
        row.setObjectName("section_row")
        row.setFixedHeight(46)
        row.setStyleSheet("QWidget#section_row { background: transparent; }")
        lay = QHBoxLayout(row)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)

        # Speaker icon (replaces the "Volume" label)
        icon = SpeakerIcon()
        lay.addWidget(icon)
        lay.addSpacing(6)

        # Slider
        sl = QSlider(Qt.Horizontal)
        sl.setRange(0, 100)
        sl.setValue(self._volume)
        sl.setCursor(Qt.PointingHandCursor)
        self._volume_slider = sl
        lay.addWidget(sl)

        # Value display
        self._volume_label = lbl(f"{self._volume}%", size=12, color="#6a6c6c")
        self._volume_label.setFixedWidth(34)
        self._volume_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        sl.valueChanged.connect(lambda v: self._volume_label.setText(f"{v}%"))
        sl.valueChanged.connect(self._on_volume_changed)
        lay.addWidget(self._volume_label)

        return row

    def get_settings(self):
        return {
            "sound": self._sound,
            "volume": self._volume,
            "custom_file": self._custom_file or "",
        }

    def set_settings(self, settings):
        settings = settings or {}
        self._sound = str(settings.get("sound", "Default beep"))
        if self._sound not in self.SOUND_OPTIONS:
            self._sound = "Default beep"
        self._volume = clamp_int(settings.get("volume", 45), 45, 0, 100)
        custom_file = settings.get("custom_file")
        self._custom_file = custom_file if isinstance(custom_file, str) and custom_file else None

        idx = self._combo.findText(self._sound)
        if idx >= 0:
            self._combo.blockSignals(True)
            self._combo.setCurrentIndex(idx)
            self._combo.blockSignals(False)

        self._volume_slider.blockSignals(True)
        self._volume_slider.setValue(self._volume)
        self._volume_slider.blockSignals(False)
        self._volume_label.setText(f"{self._volume}%")

        self._refresh_file_label()
        is_custom = (self._sound == "Custom file")
        self._file_row.setVisible(is_custom)
        self._div_after_file.setVisible(is_custom)
        self.updateGeometry()
        if self._on_layout_changed:
            QTimer.singleShot(0, self._on_layout_changed)

    def _refresh_file_label(self):
        if self._custom_file:
            filename = os.path.basename(self._custom_file)
            if len(filename) > 28:
                filename = filename[:25] + "..."
            self._file_path_lbl.setText(filename)
            self._file_path_lbl.setStyleSheet(
                f"color:{TEXT_SEC};font-size:12px;background:transparent;border:none;"
            )
        else:
            self._file_path_lbl.setText("No file selected")
            self._file_path_lbl.setStyleSheet(
                f"color:#5a5e5e;font-size:12px;background:transparent;"
                f"border:none;font-style:italic;"
            )

    def _on_sound_changed(self, text):
        self._sound = text
        is_custom = (text == "Custom file")
        self._file_row.setVisible(is_custom)
        self._div_after_file.setVisible(is_custom)
        self.updateGeometry()
        # Defer window resize until layout has propagated
        if self._on_layout_changed:
            QTimer.singleShot(0, self._on_layout_changed)

    def _on_volume_changed(self, v):
        self._volume = v

    def _preview_sound(self):
        self.play_current_alarm()

    def play_current_alarm(self):
        if self._sound == "Custom file":
            return self._play_custom_file()

        return play_alarm(
            self._sound,
            self._custom_file or "",
            self._volume / 100.0
        )

    def _play_custom_file(self):
        if not self._custom_file or not os.path.isfile(self._custom_file):
            return play_system_beep()

        # Use QtMultimedia for custom files so MP3/OGG/FLAC can play without
        # changing the built-in generated WAV alarm path. Keep these objects on
        # self so playback is not garbage-collected immediately.
        if self._media_player is not None and self._audio_output is not None:
            volume = max(0.0, min(1.0, self._volume / 100.0))
            self._audio_output.setVolume(volume)
            self._media_player.stop()
            self._media_player.setSource(QUrl.fromLocalFile(os.path.abspath(self._custom_file)))
            self._media_player.play()
            return True

        # Fallback path: the old app's winsound route supports WAV files only.
        if os.path.splitext(self._custom_file)[1].lower() == ".wav":
            return play_alarm("Custom file", self._custom_file, self._volume / 100.0)

        return False

    def _browse_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select audio file",
            "",
            "Audio files (*.wav *.mp3 *.ogg *.flac);;All files (*)"
        )
        if path:
            self._custom_file = path
            self._refresh_file_label()


# ── Timer settings page ───────────────────────────────────────────────────────
class TimerSettingsPage(QWidget):
    def __init__(self, num, back_cb, set_duration_cb=None, on_layout_changed=None, hotkey_changed_cb=None, save_cb=None, parent=None):
        super().__init__(parent)
        self._num = num
        self._back_cb = back_cb
        self._set_dur = set_duration_cb
        self._on_layout_changed = on_layout_changed
        self._hotkey_changed_cb = hotkey_changed_cb
        self._save_cb = save_cb
        self._edit_snapshot = None
        self._build()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        content = QWidget()
        content.setObjectName("settings_content")
        content.setStyleSheet(
            f"QWidget#settings_content {{ background:{BG_APP}; }}"
        )
        clay = QVBoxLayout(content)
        clay.setContentsMargins(8, 8, 8, 8)
        clay.setSpacing(0)

        # DURATION header row — section label on left, timer identifier on right
        dur_header = QHBoxLayout()
        dur_header.setContentsMargins(0, 0, 0, 0)
        dur_header.setSpacing(0)
        dur_header.addWidget(sect_lbl("Duration"))
        dur_header.addStretch()
        dur_header.addWidget(sect_lbl(f"Timer {self._num}"))
        clay.addLayout(dur_header)
        clay.addSpacing(8)
        default = "1:20"  # both timers default to 1:20
        self._duration_editor = DurationEditor(default, on_set=None)
        clay.addWidget(self._duration_editor)
        clay.addSpacing(8)

        clay.addWidget(sect_lbl("Alarm"))
        clay.addSpacing(8)
        self._alarm_card = AlarmCard(on_layout_changed=self._on_layout_changed)
        clay.addWidget(self._alarm_card)
        clay.addSpacing(8)

        clay.addWidget(sect_lbl("Hotkeys"))
        clay.addSpacing(8)
        start_action = f"timer{self._num}_toggle"
        reset_action = f"timer{self._num}_reset"
        ss = "alt"     if self._num == 1 else "alt+2"
        rs = "alt+r"   if self._num == 1 else "alt+t"
        self._hk_start = HotkeyPill(start_action, ss, self._hotkey_changed_cb)
        self._hk_reset = HotkeyPill(reset_action, rs, self._hotkey_changed_cb)
        clay.addWidget(make_card([
            srow(lbl("Start / Stop", color=TEXT_SEC), self._hk_start),
            srow(lbl("Reset",        color=TEXT_SEC), self._hk_reset),
        ]))

        # Save / Cancel button row
        clay.addSpacing(8)
        brow = QHBoxLayout()
        brow.setSpacing(8)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setObjectName("cancel")
        cancel_btn.setFixedHeight(40)
        cancel_btn.setCursor(Qt.PointingHandCursor)
        cancel_btn.clicked.connect(self.cancel_changes)
        save_btn = QPushButton("Save")
        save_btn.setFixedHeight(40)
        save_btn.setCursor(Qt.PointingHandCursor)
        save_btn.clicked.connect(self.save_changes)
        brow.addWidget(cancel_btn)
        brow.addWidget(save_btn)
        clay.addLayout(brow)

        lay.addWidget(content)

    def set_duration_seconds(self, secs):
        self._duration_editor.set_seconds(secs)

    def get_duration_seconds(self):
        return self._duration_editor.get_seconds()

    def _snapshot_state(self):
        return {
            "duration": clamp_int(self._duration_editor.get_seconds(), 80, 1, 5999),
            "alarm": self._alarm_card.get_settings(),
            "hotkeys": self.hotkey_bindings(),
        }

    def begin_edit(self):
        self._edit_snapshot = self._snapshot_state()

    def _restore_state(self, state):
        if not state:
            return
        self._duration_editor.set_seconds(state.get("duration", 80))
        self._alarm_card.set_settings(state.get("alarm", {}))
        hotkeys = state.get("hotkeys", {})
        self._hk_start.set_hotkey(hotkeys.get(f"timer{self._num}_toggle", self._hk_start.hotkey()))
        self._hk_reset.set_hotkey(hotkeys.get(f"timer{self._num}_reset", self._hk_reset.hotkey()))
        if self._hotkey_changed_cb:
            self._hotkey_changed_cb("timer_settings_restore", "")

    def cancel_changes(self):
        if self._edit_snapshot is not None:
            self._restore_state(self._edit_snapshot)
        self._edit_snapshot = None
        self._back_cb()

    def save_changes(self):
        secs = clamp_int(self._duration_editor.get_seconds(), 80, 1, 5999)
        self._duration_editor.set_seconds(secs)
        if self._set_dur:
            self._set_dur(secs)
        if self._hotkey_changed_cb:
            self._hotkey_changed_cb("timer_settings_save", "")
        self._edit_snapshot = None
        if self._save_cb:
            self._save_cb()
        self._back_cb()

    def hotkey_bindings(self):
        return {
            f"timer{self._num}_toggle": self._hk_start.hotkey(),
            f"timer{self._num}_reset": self._hk_reset.hotkey(),
        }

    def get_settings(self, committed_only=False):
        if committed_only and self._edit_snapshot is not None:
            return self._edit_snapshot
        return self._snapshot_state()

    def set_settings(self, settings):
        settings = settings or {}
        duration = clamp_int(settings.get("duration", 80), 80, 1, 5999)
        self._duration_editor.set_seconds(duration)
        self._alarm_card.set_settings(settings.get("alarm", {}))
        hotkeys = settings.get("hotkeys", {})
        self._hk_start.set_hotkey(hotkeys.get(f"timer{self._num}_toggle", self._hk_start.hotkey()))
        self._hk_reset.set_hotkey(hotkeys.get(f"timer{self._num}_reset", self._hk_reset.hotkey()))

    def play_alarm(self):
        return self._alarm_card.play_current_alarm()


# ── Overlay pill ──────────────────────────────────────────────────────────────
class OverlayPill(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(
            Qt.FramelessWindowHint |
            Qt.WindowStaysOnTopHint |
            Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self._locked = False
        self._bg_alpha = 150
        self._drag_pos = None
        self._t1_warn = False
        self._t2_warn = False
        self._build()
        self.adjustSize()

    def _build(self):
        lay = QHBoxLayout(self)
        lay.setContentsMargins(16, 9, 16, 9)
        lay.setSpacing(12)
        f = QFont("Consolas")
        f.setPixelSize(20)
        f.setWeight(QFont.Light)
        self._t1 = QLabel("01:20")
        self._t1.setFont(f)
        self._t1.setStyleSheet(f"color:{TEXT_PRI};background:transparent;")
        div = QFrame()
        div.setFrameShape(QFrame.VLine)
        div.setFixedSize(1, 16)
        div.setStyleSheet("background:rgba(255,255,255,40);border:none;")
        self._t2 = QLabel("01:20")
        self._t2.setFont(f)
        self._t2.setStyleSheet(f"color:{TEXT_DIM};background:transparent;")
        lay.addWidget(self._t1)
        lay.addWidget(div, 0, Qt.AlignVCenter)
        lay.addWidget(self._t2)

    def update_times(self, t1_text, t1_running, t1_warn, t2_text, t2_running, t2_warn, user_hidden=False):
        self._t1_warn = t1_warn
        self._t2_warn = t2_warn
        self._t1.setText(t1_text)
        self._t2.setText(t2_text)
        c1 = TEXT_WARN if t1_warn else (TEXT_PRI if t1_running else TEXT_DIM)
        c2 = TEXT_WARN if t2_warn else (TEXT_PRI if t2_running else TEXT_DIM)
        self._t1.setStyleSheet(f"color:{c1};background:transparent;")
        self._t2.setStyleSheet(f"color:{c2};background:transparent;")
        # Show only when a timer is running AND user hasn't hidden it
        if (t1_running or t2_running) and not user_hidden:
            self.show()
        else:
            self.hide()
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setBrush(QColor(0, 0, 0, self._bg_alpha))
        warn = self._t1_warn or self._t2_warn
        border_color = QColor(248, 81, 73, 100) if warn else QColor(255, 255, 255, 24)
        p.setPen(QPen(border_color, 1))
        p.drawRoundedRect(1, 1, self.width()-2, self.height()-2, 16, 16)

    def mousePressEvent(self, e):
        if not self._locked and e.button() == Qt.LeftButton:
            self._drag_pos = e.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, e):
        if not self._locked and e.buttons() == Qt.LeftButton and self._drag_pos:
            self.move(e.globalPosition().toPoint() - self._drag_pos)

    def mouseReleaseEvent(self, e):
        self._drag_pos = None

# ── Header banner ─────────────────────────────────────────────────────────────
class HeaderBanner(QWidget):
    """Small left-aligned logo header. Loads vtxt_banner.png from the script's
    directory, scales it to a compact width, and pins it to the left edge with
    padding that matches the page content margin. If the file isn't found, the
    widget collapses to zero height (no banner shown)."""
    LOGO_WIDTH = 80           # display width of the scaled logo (cropped image: 572x154)
    LEFT_PAD = 8              # aligns logo with card outer edge (border)
    VPAD_TOP = 10             # padding above the logo (gives breathing room from title bar)
    VPAD_BOT = 8              # padding below the logo (matches inter-card spacing)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setObjectName("header_banner")
        self.setStyleSheet(
            f"QWidget#header_banner {{ background: {BG_APP}; border: none; }}"
        )

        lay = QHBoxLayout(self)
        lay.setContentsMargins(self.LEFT_PAD, self.VPAD_TOP, self.LEFT_PAD, self.VPAD_BOT)
        lay.setSpacing(0)

        # Locate banner relative to this script or the PyInstaller bundle.
        banner_path = resource_path("vtxt_banner.png")

        if os.path.exists(banner_path):
            pixmap = QPixmap(banner_path)
            if not pixmap.isNull():
                scaled = pixmap.scaledToWidth(self.LOGO_WIDTH, Qt.SmoothTransformation)
                logo = QLabel()
                logo.setPixmap(scaled)
                logo.setFixedSize(scaled.size())
                logo.setStyleSheet("background: transparent; border: none;")
                lay.addWidget(logo, 0, Qt.AlignVCenter | Qt.AlignLeft)
                lay.addStretch(1)
                self.setFixedHeight(scaled.height() + self.VPAD_TOP + self.VPAD_BOT)
                return

        # Fallback — no banner found, collapse to 0 height
        self.setFixedHeight(0)


# ── Main window ───────────────────────────────────────────────────────────────
class VertexTimer(QMainWindow):
    WIDTH = 342               # window width — 326px card width + 8px on each side

    def __init__(self):
        super().__init__()
        icon = app_icon()
        if not icon.isNull():
            self.setWindowIcon(icon)
        self.setWindowTitle(APP_NAME)
        self.setFixedWidth(self.WIDTH)
        self.setStyleSheet(STYLE)
        self._banner = HeaderBanner()
        self._stack = QStackedWidget()
        container = QWidget()
        container.setObjectName("main_container")
        container.setStyleSheet(
            f"QWidget#main_container {{ background: {BG_APP}; }}"
        )
        clay = QVBoxLayout(container)
        clay.setContentsMargins(0, 0, 0, 0)
        clay.setSpacing(0)
        clay.addWidget(self._banner)
        clay.addWidget(self._stack)
        self.setCentralWidget(container)
        self._overlay = OverlayPill()
        self._user_hidden = False
        self._user_locked = False
        self._settings = load_app_settings()
        self._timer_settings_pages = {}
        self._hotkey_manager = None
        self._build_main()
        self._build_settings(1)
        self._build_settings(2)
        self._apply_loaded_settings()
        self._stack.setCurrentIndex(0)
        self._overlay.move(60, 60)
        self._overlay.hide()  # shown only when a timer runs
        self._hotkey_manager = PassiveHotkeyManager(self, self._handle_hotkey_action)
        self._hotkey_manager.set_bindings(self._collect_hotkey_bindings())
        self._hotkey_manager.start()
        # Measure and lock height after layout renders
        QTimer.singleShot(0, self._init_collapsed_height)

    def _snap_to_content(self):
        """Resize window to fit current page content + banner."""
        self.setMinimumHeight(0)
        self.setMaximumHeight(16777215)
        page_height = self._stack.currentWidget().sizeHint().height()
        banner_height = self._banner.height()
        self.setFixedWidth(self.WIDTH)
        self.setFixedHeight(page_height + banner_height)

    def _init_collapsed_height(self):
        """Lock main page height after first layout pass."""
        page_height = self._stack.widget(0).sizeHint().height()
        banner_height = self._banner.height()
        self._collapsed_height = page_height + banner_height
        self.setFixedWidth(self.WIDTH)
        self.setFixedHeight(self._collapsed_height)
        self._wire_dropdown_buttons()

    def _wire_dropdown_buttons(self):
        """Wire overlay dropdown expand/collapse to window resize without bypassing Save/Cancel."""
        self._ov_drop._btn.clicked.disconnect()
        self._ov_drop._btn.clicked.connect(self._expand_ov)
        for btn in self._ov_drop._drop.findChildren(QPushButton):
            if btn.text() == "Cancel":
                btn.clicked.disconnect()
                btn.clicked.connect(self._cancel_ov_settings)
            elif btn.text() == "Save":
                btn.clicked.disconnect()
                btn.clicked.connect(self._save_ov_settings)

    def _expand_ov(self):
        self._ov_drop.begin_edit()
        self._ov_drop._toggle()
        self._ov_wrap.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        self.setMinimumHeight(0)
        self.setMaximumHeight(16777215)
        QTimer.singleShot(0, self._snap_to_content)

    def _save_ov_settings(self):
        self._ov_drop.save_changes()
        self._ov_wrap.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        self.setFixedHeight(self._collapsed_height)

    def _cancel_ov_settings(self):
        self._ov_drop.cancel_changes()
        self._ov_wrap.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        self.setFixedHeight(self._collapsed_height)

    def _collapse_ov(self):
        self._cancel_ov_settings()

    def _apply_toggle(self, visible, unlocked, size_pct=None, opacity_pct=None):
        """Called immediately when a toggle or slider changes."""
        self._user_hidden = not visible
        self._user_locked = not unlocked
        self._overlay._locked = not unlocked
        s1 = self._t1.get_state()
        s2 = self._t2.get_state()
        if visible and (s1['running'] or s2['running']):
            self._overlay.show()
        else:
            self._overlay.hide()
        if size_pct is not None:
            self._apply_overlay_size(size_pct)
        if opacity_pct is not None:
            self._apply_overlay_opacity(opacity_pct)

    def _apply_overlay_size(self, size_pct):
        size_pct = clamp_int(size_pct, 50, 0, 100)
        sizes = [14, 16, 19, 22, 26]
        idx = min(4, size_pct * 5 // 100)
        px = sizes[idx]
        f = self._overlay._t1.font()
        f.setPixelSize(px)
        self._overlay._t1.setFont(f)
        self._overlay._t2.setFont(f)
        self._overlay.adjustSize()

    def _apply_overlay_opacity(self, opacity_pct):
        opacity_pct = clamp_int(opacity_pct, 60, 0, 100)
        self._overlay._bg_alpha = int(opacity_pct / 100 * 255)
        self._overlay.update()

    def _apply_overlay_settings(self, visible, unlocked, size_pct, opacity_pct):
        """Commit overlay settings for the current session and settings.json."""
        self._save_settings()

    def _nav(self, idx):
        self._stack.setCurrentIndex(idx)
        # Unlock height constraints and snap to the current page's content.
        # This handles both directions correctly — including the case where
        # the user left the overlay dropdown expanded on the main page,
        # navigated to settings, and came back: the main page now reports a
        # taller sizeHint and the window grows to fit it.
        self.setMinimumHeight(0)
        self.setMaximumHeight(16777215)
        QTimer.singleShot(0, self._snap_to_content)

    def _open_settings(self, num):
        page = self._timer_settings_pages.get(num)
        block = self._t1 if num == 1 else self._t2
        if page is not None:
            page.set_duration_seconds(block.get_total())
            page.begin_edit()
        self._nav(num)

    def _update_overlay(self):
        s1 = self._t1.get_state()
        s2 = self._t2.get_state()
        self._overlay.update_times(
            s1['text'], s1['running'], s1['warn'],
            s2['text'], s2['running'], s2['warn'],
            self._user_hidden
        )

    def _collect_hotkey_bindings(self):
        bindings = {}
        if hasattr(self, "_ov_drop"):
            bindings.update(self._ov_drop.hotkey_bindings())
        for page in getattr(self, "_timer_settings_pages", {}).values():
            bindings.update(page.hotkey_bindings())
        return bindings

    def _on_hotkey_changed(self, action_name, hotkey):
        if self._hotkey_manager is not None:
            self._hotkey_manager.refresh(self._collect_hotkey_bindings())
            self._hotkey_manager.suppress_until_all_released()

    def _handle_hotkey_action(self, action_name):
        if action_name == "timer1_toggle":
            self._t1.toggle_hotkey()
        elif action_name == "timer1_reset":
            self._t1.reset_hotkey()
        elif action_name == "timer2_toggle":
            self._t2.toggle_hotkey()
        elif action_name == "timer2_reset":
            self._t2.reset_hotkey()
        elif action_name == "overlay_visible":
            self._ov_drop.toggle_visibility_hotkey()
        elif action_name == "overlay_lock":
            self._ov_drop.toggle_lock_hotkey()

    def closeEvent(self, event):
        self._save_settings()
        if self._hotkey_manager is not None:
            self._hotkey_manager.stop()
        try:
            self._overlay.close()
        except Exception:
            pass
        super().closeEvent(event)

    def _build_main(self):
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(8, 0, 8, 0)
        lay.setSpacing(0)

        self._t1 = TimerBlock(1, self._open_settings, self._update_overlay, finish_cb=lambda: self._play_timer_alarm(1))
        self._t2 = TimerBlock(2, self._open_settings, self._update_overlay, finish_cb=lambda: self._play_timer_alarm(2))

        lay.addWidget(self._t1)
        lay.addSpacing(8)
        lay.addWidget(self._t2)

        ov_wrap = QWidget()
        ov_wrap.setObjectName("ov_wrap")
        ov_wrap.setStyleSheet(f"QWidget#ov_wrap {{ background:{BG_APP}; }}")
        ov_lay = QVBoxLayout(ov_wrap)
        ov_lay.setContentsMargins(0, 8, 0, 8)
        self._ov_drop = OverlaySettingsDropdown(save_cb=self._apply_overlay_settings, toggle_cb=self._apply_toggle, hotkey_changed_cb=self._on_hotkey_changed)
        ov_lay.addWidget(self._ov_drop)
        ov_wrap.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        lay.addWidget(ov_wrap)
        self._ov_wrap = ov_wrap

        self._stack.addWidget(page)

    def _play_timer_alarm(self, num):
        page = self._timer_settings_pages.get(num)
        if page is not None:
            page.play_alarm()

    def _collect_settings(self, committed_only=False):
        settings = get_default_settings()
        for num, page in self._timer_settings_pages.items():
            key = str(num)
            settings["timers"][key] = page.get_settings(committed_only=committed_only)
        if hasattr(self, "_ov_drop"):
            settings["overlay"] = self._ov_drop.get_settings(committed_only=committed_only)
        return settings

    def _save_settings(self):
        self._settings = self._collect_settings(committed_only=True)
        return save_app_settings(self._settings)

    def _apply_loaded_settings(self):
        settings = sanitize_app_settings(self._settings or get_default_settings())
        timers = settings.get("timers", {})
        for num in (1, 2):
            page = self._timer_settings_pages.get(num)
            block = self._t1 if num == 1 else self._t2
            timer_settings = timers.get(str(num), {})
            if page is not None:
                page.set_settings(timer_settings)
            duration = clamp_int(timer_settings.get("duration", 80), 80, 1, 5999)
            block.set_total(duration)

        overlay_settings = settings.get("overlay", {})
        if hasattr(self, "_ov_drop"):
            self._ov_drop.set_settings(overlay_settings)

    def _build_settings(self, num):
        block = self._t1 if num == 1 else self._t2
        page = TimerSettingsPage(
            num,
            back_cb=lambda: self._nav(0),
            set_duration_cb=block.set_total,
            on_layout_changed=self._snap_to_content,
            hotkey_changed_cb=self._on_hotkey_changed,
            save_cb=self._save_settings,
        )
        page.set_duration_seconds(block.get_total())
        self._timer_settings_pages[num] = page
        self._stack.addWidget(page)

# ── Entry ─────────────────────────────────────────────────────────────────────
def main():
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    icon = app_icon()
    if not icon.isNull():
        app.setWindowIcon(icon)
    win = VertexTimer()
    win.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
