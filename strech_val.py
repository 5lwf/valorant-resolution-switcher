"""
Valorant Auto Resolution Switcher — GUI Edition
Windows 11 | Manual Start/Stop

Requirements:
    pip install psutil pywin32

Run: python valorant_res_switcher_gui.py
"""

import customtkinter as ctk
import ctypes
import os
import psutil
import threading
import time
from datetime import datetime

# ── Configuration ──────────────────────────────────────────────────────────────
GAME_RES   = (1080, 1080)
NORMAL_RES = (1920, 1080)
POLL_SEC   = 0.5
VALORANT_PROCS = {"VALORANT-Win64-Shipping.exe", "VALORANT.exe"}
VALORANT_LOG = os.path.join(
    os.environ.get("LOCALAPPDATA", ""), "VALORANT", "Saved", "Logs", "ShooterGame.log"
)
# ───────────────────────────────────────────────────────────────────────────────

# ── Windows Resolution API ─────────────────────────────────────────────────────
CCDEVICENAME  = 32
CFORMNAME     = 32
DM_PELSWIDTH  = 0x00080000
DM_PELSHEIGHT = 0x00100000
CDS_UPDATEREGISTRY = 0x00000001
DISP_CHANGE_SUCCESSFUL = 0
MONITORINFOF_PRIMARY = 1

class DEVMODE(ctypes.Structure):
    _fields_ = [
        ("dmDeviceName",         ctypes.c_wchar * CCDEVICENAME),
        ("dmSpecVersion",        ctypes.c_ushort),
        ("dmDriverVersion",      ctypes.c_ushort),
        ("dmSize",               ctypes.c_ushort),
        ("dmDriverExtra",        ctypes.c_ushort),
        ("dmFields",             ctypes.c_ulong),
        ("dmPositionX",          ctypes.c_long),
        ("dmPositionY",          ctypes.c_long),
        ("dmDisplayOrientation", ctypes.c_ulong),
        ("dmDisplayFixedOutput", ctypes.c_ulong),
        ("dmColor",              ctypes.c_short),
        ("dmDuplex",             ctypes.c_short),
        ("dmYResolution",        ctypes.c_short),
        ("dmTTOption",           ctypes.c_short),
        ("dmCollate",            ctypes.c_short),
        ("dmFormName",           ctypes.c_wchar * CFORMNAME),
        ("dmLogPixels",          ctypes.c_ushort),
        ("dmBitsPerPel",         ctypes.c_ulong),
        ("dmPelsWidth",          ctypes.c_ulong),
        ("dmPelsHeight",         ctypes.c_ulong),
        ("dmDisplayFlags",       ctypes.c_ulong),
        ("dmDisplayFrequency",   ctypes.c_ulong),
        ("dmICMMethod",          ctypes.c_ulong),
        ("dmICMIntent",          ctypes.c_ulong),
        ("dmMediaType",          ctypes.c_ulong),
        ("dmDitherType",         ctypes.c_ulong),
        ("dmReserved1",          ctypes.c_ulong),
        ("dmReserved2",          ctypes.c_ulong),
        ("dmPanningWidth",       ctypes.c_ulong),
        ("dmPanningHeight",      ctypes.c_ulong),
    ]

def set_resolution(width: int, height: int) -> bool:
    dm = DEVMODE()
    dm.dmSize       = ctypes.sizeof(DEVMODE)
    dm.dmPelsWidth  = width
    dm.dmPelsHeight = height
    dm.dmFields     = DM_PELSWIDTH | DM_PELSHEIGHT
    result = ctypes.windll.user32.ChangeDisplaySettingsW(ctypes.byref(dm), CDS_UPDATEREGISTRY)
    return result == DISP_CHANGE_SUCCESSFUL

def get_current_resolution() -> tuple:
    user32 = ctypes.windll.user32
    return user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)

def get_secondary_work_area():
    """Return the work area of the first non-primary monitor, if available."""
    monitors = []

    class RECT(ctypes.Structure):
        _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                    ("right", ctypes.c_long), ("bottom", ctypes.c_long)]

    class MONITORINFO(ctypes.Structure):
        _fields_ = [("cbSize", ctypes.c_ulong), ("rcMonitor", RECT),
                    ("rcWork", RECT), ("dwFlags", ctypes.c_ulong)]

    callback_type = ctypes.WINFUNCTYPE(
        ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p,
        ctypes.POINTER(RECT), ctypes.c_ssize_t
    )

    def collect_monitor(handle, _dc, _rect, _data):
        info = MONITORINFO()
        info.cbSize = ctypes.sizeof(MONITORINFO)
        if ctypes.windll.user32.GetMonitorInfoW(handle, ctypes.byref(info)):
            work = info.rcWork
            monitors.append((
                bool(info.dwFlags & MONITORINFOF_PRIMARY),
                work.left, work.top, work.right, work.bottom,
            ))
        return 1

    callback = callback_type(collect_monitor)
    ctypes.windll.user32.EnumDisplayMonitors(None, None, callback, 0)
    return next((monitor[1:] for monitor in monitors if not monitor[0]), None)

def valorant_running() -> bool:
    for proc in psutil.process_iter(["name"]):
        try:
            if proc.info["name"] in VALORANT_PROCS:
                return True
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    return False

def valorant_is_foreground() -> bool:
    """Return True only when the currently focused window belongs to VALORANT."""
    try:
        window = ctypes.windll.user32.GetForegroundWindow()
        if not window:
            return False
        process_id = ctypes.c_ulong()
        ctypes.windll.user32.GetWindowThreadProcessId(window, ctypes.byref(process_id))
        return psutil.Process(process_id.value).name() in VALORANT_PROCS
    except (psutil.NoSuchProcess, psutil.AccessDenied, OSError):
        return False

def valorant_match_active() -> bool:
    """Return True only while VALORANT's game-flow state is InGame."""
    if not valorant_running():
        return False

    try:
        # Reading only the end keeps polling cheap even when the log is large.
        with open(VALORANT_LOG, "rb") as log_file:
            log_file.seek(0, os.SEEK_END)
            size = log_file.tell()
            log_file.seek(max(0, size - 1024 * 1024))
            lines = log_file.read().decode("utf-8", errors="ignore").splitlines()

        marker = "Broadcasting state changed to "
        for line in reversed(lines):
            if marker in line:
                state = line.rsplit(marker, 1)[1].strip()
                return state == "InGame"
    except (OSError, PermissionError):
        pass

    return False
# ───────────────────────────────────────────────────────────────────────────────


class App(ctk.CTk):
    BG        = "#11100E"
    SURFACE   = "#1C1A17"
    SURFACE2  = "#29251F"
    BORDER    = "#3B352D"
    ACCENT    = "#C98B5A"
    ACCENT_H  = "#E0A06C"
    GREEN     = "#87AD90"
    GREEN_DIM = "#26382B"
    RED       = "#D47C70"
    RED_DIM   = "#3B2623"
    TEXT      = "#F5EEE4"
    MUTED     = "#A99C8D"

    def __init__(self):
        super().__init__()
        ctk.set_appearance_mode("dark")
        self.title("ResSwitch")
        self.resizable(False, False)
        self.configure(fg_color=self.BG)

        # DPI awareness
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass

        self._monitoring  = False
        self._monitor_thr = None
        self._last_state  = None
        self._pending_res = None
        self._log_entries = []

        self._build_ui()
        self._refresh_current_res()

        # Start monitoring immediately when the app is launched.
        self.after(250, self._toggle_watch)

        # Center window
        self.update_idletasks()
        w, h = 480, 650
        secondary = get_secondary_work_area()
        if secondary:
            left, top, right, bottom = secondary
            x = left + ((right - left) - w) // 2
            y = top + ((bottom - top) - h) // 2
        else:
            sw = self.winfo_screenwidth()
            sh = self.winfo_screenheight()
            x, y = (sw - w) // 2, (sh - h) // 2
        self.geometry(f"{w}x{h}{x:+d}{y:+d}")

    # ── UI Construction ────────────────────────────────────────────────────────
    def _build_ui(self):
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=28, pady=24)

        header = ctk.CTkFrame(body, fg_color="transparent", height=60)
        header.pack(fill="x", pady=(0, 20))
        header.pack_propagate(False)
        title_box = ctk.CTkFrame(header, fg_color="transparent")
        title_box.pack(side="left", anchor="w")
        ctk.CTkLabel(title_box, text="RES SWITCH", text_color=self.TEXT,
                     font=ctk.CTkFont("Segoe UI", 25, "bold")).pack(anchor="w")
        ctk.CTkLabel(title_box, text="VALORANT DISPLAY COMPANION", text_color=self.MUTED,
                     font=ctk.CTkFont("Segoe UI", 10, "bold")).pack(anchor="w", pady=(2, 0))
        self._status_lbl = ctk.CTkLabel(
            header, text="  ●  IDLE  ", corner_radius=16,
            fg_color=self.SURFACE2, text_color=self.MUTED,
            font=ctk.CTkFont("Segoe UI", 11, "bold"), height=32
        )
        self._status_lbl.pack(side="right", pady=5)

        hero = ctk.CTkFrame(body, fg_color=self.SURFACE, corner_radius=22,
                            border_width=1, border_color=self.BORDER)
        hero.pack(fill="x", pady=(0, 14))
        ctk.CTkLabel(hero, text="CURRENT RESOLUTION", text_color=self.MUTED,
                     font=ctk.CTkFont("Segoe UI", 10, "bold")).pack(pady=(20, 2))
        self._cur_res_lbl = ctk.CTkLabel(hero, text="...", text_color=self.TEXT,
                                         font=ctk.CTkFont("Segoe UI", 34, "bold"))
        self._cur_res_lbl.pack(pady=(0, 20))

        cards = ctk.CTkFrame(body, fg_color="transparent")
        cards.pack(fill="x", pady=(0, 14))
        cards.grid_columnconfigure((0, 1), weight=1)
        self._card_normal = self._res_card(cards, "DESKTOP", NORMAL_RES, True)
        self._card_normal.grid(row=0, column=0, sticky="ew", padx=(0, 7))
        self._card_game = self._res_card(cards, "IN-GAME", GAME_RES, False)
        self._card_game.grid(row=0, column=1, sticky="ew", padx=(7, 0))

        btn_row = ctk.CTkFrame(body, fg_color="transparent")
        btn_row.pack(fill="x", pady=(0, 14))
        btn_row.grid_columnconfigure((0, 1), weight=1)
        self._btn_game = ctk.CTkButton(
            btn_row, text="GAME MODE", height=46, corner_radius=14,
            fg_color=self.ACCENT, hover_color=self.ACCENT_H, text_color="#17120E",
            font=ctk.CTkFont("Segoe UI", 12, "bold"),
            command=lambda: self._apply_res(GAME_RES, "game")
        )
        self._btn_game.grid(row=0, column=0, sticky="ew", padx=(0, 7))
        self._btn_desk = ctk.CTkButton(
            btn_row, text="DESKTOP", height=46, corner_radius=14,
            fg_color=self.SURFACE2, hover_color=self.BORDER, text_color=self.TEXT,
            font=ctk.CTkFont("Segoe UI", 12, "bold"),
            command=lambda: self._apply_res(NORMAL_RES, "desktop")
        )
        self._btn_desk.grid(row=0, column=1, sticky="ew", padx=(7, 0))

        watch = ctk.CTkFrame(body, fg_color=self.SURFACE, corner_radius=18,
                             border_width=1, border_color=self.BORDER)
        watch.pack(fill="x", pady=(0, 14))
        watch_text = ctk.CTkFrame(watch, fg_color="transparent")
        watch_text.pack(side="left", padx=18, pady=15)
        ctk.CTkLabel(watch_text, text="AUTOMATIC MATCH SWITCHING", text_color=self.TEXT,
                     font=ctk.CTkFont("Segoe UI", 11, "bold")).pack(anchor="w")
        ctk.CTkLabel(watch_text, text="Changes only at match start and end", text_color=self.MUTED,
                     font=ctk.CTkFont("Segoe UI", 10)).pack(anchor="w", pady=(2, 0))
        self._toggle_btn = ctk.CTkButton(
            watch, text="OFF", width=64, height=32, corner_radius=16,
            fg_color=self.RED_DIM, hover_color="#4A302C", text_color=self.RED,
            font=ctk.CTkFont("Segoe UI", 11, "bold"), command=self._toggle_watch
        )
        self._toggle_btn.pack(side="right", padx=16)

        ctk.CTkLabel(body, text="RECENT ACTIVITY", text_color=self.MUTED,
                     font=ctk.CTkFont("Segoe UI", 10, "bold")).pack(anchor="w", padx=3, pady=(0, 6))
        self._log_text = ctk.CTkTextbox(
            body, height=130, corner_radius=18, border_width=1, border_color=self.BORDER,
            fg_color=self.SURFACE, text_color=self.MUTED, scrollbar_button_color=self.BORDER,
            scrollbar_button_hover_color=self.ACCENT, font=ctk.CTkFont("Consolas", 10), wrap="word"
        )
        self._log_text.pack(fill="both", expand=True)
        self._log_text.configure(state="disabled")
        self._log("ResSwitch is ready", "inf")

    def _res_card(self, parent, label, res, active):
        f = ctk.CTkFrame(parent, fg_color=self.SURFACE2 if active else self.SURFACE,
                         corner_radius=18, border_width=1,
                         border_color=self.ACCENT if active else self.BORDER)
        ctk.CTkLabel(f, text=label, text_color=self.MUTED,
                     font=ctk.CTkFont("Segoe UI", 10, "bold")).pack(anchor="w", padx=16, pady=(14, 2))
        ctk.CTkLabel(f, text=f"{res[0]} × {res[1]}", text_color=self.TEXT,
                     font=ctk.CTkFont("Segoe UI", 17, "bold")).pack(anchor="w", padx=16, pady=(0, 14))
        return f

    # ── Actions ────────────────────────────────────────────────────────────────
    def _apply_res(self, res, mode):
        w, h = res
        cur = get_current_resolution()
        if cur == (w, h):
            self._log(f"Already at {w}×{h}", "inf")
            self._refresh_current_res()
            return
        ok = set_resolution(w, h)
        if ok:
            self._log(f"Switched to {w}×{h} ({mode})", "ok")
            self._update_cards(mode)
        else:
            self._log(f"Failed to switch to {w}×{h}", "err")
        self._refresh_current_res()

    def _toggle_watch(self):
        self._monitoring = not self._monitoring
        if self._monitoring:
            self._toggle_btn.configure(text="ON", fg_color=self.GREEN_DIM,
                                       hover_color="#304936", text_color=self.GREEN)
            self._set_status("WATCHING", self.GREEN)
            self._log("Match-state auto-watch enabled", "inf")
            self._last_state = None
            self._monitor_thr = threading.Thread(target=self._watch_loop, daemon=True)
            self._monitor_thr.start()
        else:
            self._toggle_btn.configure(text="OFF", fg_color=self.RED_DIM,
                                       hover_color="#4A302C", text_color=self.RED)
            self._set_status("IDLE", self.MUTED)
            self._log("Auto-watch disabled", "inf")

    def _watch_loop(self):
        while self._monitoring:
            in_match = valorant_match_active()

            # Queue one change at the start/end of a match. Alt-tabbing during
            # the match does not change resolution.
            if in_match != self._last_state:
                self._pending_res = GAME_RES if in_match else NORMAL_RES
                self._last_state = in_match

            # Apply a queued boundary change only while VALORANT is focused,
            # avoiding a disruptive resolution change over another app.
            if self._pending_res and valorant_is_foreground():
                res = self._pending_res
                mode = "game" if res == GAME_RES else "desktop"
                self._pending_res = None
                self.after(0, lambda r=res, m=mode: self._apply_res(r, m))

            time.sleep(POLL_SEC)

    # ── Helpers ────────────────────────────────────────────────────────────────
    def _refresh_current_res(self):
        w, h = get_current_resolution()
        self._cur_res_lbl.configure(text=f"{w} × {h}")

    def _update_cards(self, mode):
        game_bg = self.SURFACE2 if mode == "game" else self.SURFACE
        desk_bg = self.SURFACE2 if mode == "desktop" else self.SURFACE
        self._card_game.configure(fg_color=game_bg, border_color=
                                  self.ACCENT if mode == "game" else self.BORDER)
        self._card_normal.configure(fg_color=desk_bg, border_color=
                                    self.GREEN if mode == "desktop" else self.BORDER)

    def _set_status(self, text, color):
        fill = self.GREEN_DIM if color == self.GREEN else self.SURFACE2
        self._status_lbl.configure(text=f"  ●  {text}  ", text_color=color, fg_color=fill)

    def _log(self, msg, tag="inf"):
        ts  = datetime.now().strftime("%H:%M:%S")
        line = f"[{ts}] {msg}\n"
        self._log_text.configure(state="normal")
        self._log_text.insert("end", line)
        self._log_text.see("end")
        self._log_text.configure(state="disabled")


if __name__ == "__main__":
    app = App()
    app.mainloop()
