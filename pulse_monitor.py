"""
Clinical Pulse Monitor - ESP32 + MAX30102
Supports two connection modes:
  1. USB Serial  — plug ESP32 into PC via USB cable
  2. Wi-Fi SSE   — connect over the same Wi-Fi network (no USB needed)

Requirements:
  pip install pyserial requests matplotlib
"""

import threading
import queue
import time
import csv
import os
from datetime import datetime
import tkinter as tk
from tkinter import ttk, font as tkfont
import requests

import matplotlib
matplotlib.use("TkAgg")
import matplotlib.pyplot as plt
import matplotlib.animation as animation
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

try:
    import serial
    import serial.tools.list_ports
    SERIAL_OK = True
except ImportError:
    SERIAL_OK = False

BAUD_RATE  = 115200
MAX_POINTS = 180
UPDATE_MS  = 30

C_BG    = "#0f172a"
C_CARD  = "#1e293b"
C_BORDER= "#334155"
C_RED   = "#f43f5e"
C_TEAL  = "#14b8a6"
C_BLUE  = "#38bdf8"
C_MUTED = "#64748b"
C_TEXT  = "#f1f5f9"
C_WAVE  = "#38bdf8"
C_GREEN = "#10b981"


# ── USB Serial reader thread ───────────────────────────────────────────────
class SerialReader(threading.Thread):
    def __init__(self, port, q):
        super().__init__(daemon=True)
        self.port  = port
        self.q     = q
        self._stop = threading.Event()
        self.ser   = None

    def run(self):
        if not SERIAL_OK:
            self.q.put(("error", "pyserial not installed. Run: pip install pyserial"))
            return
        try:
            self.ser = serial.Serial(self.port, BAUD_RATE, timeout=1)
            time.sleep(0.5)
            self.ser.reset_input_buffer()
            while not self._stop.is_set():
                raw = self.ser.readline().decode("utf-8", errors="ignore").strip()
                if raw.startswith("DATA:"):
                    _parse_and_enqueue(raw[5:], self.q)
        except Exception as e:
            self.q.put(("error", str(e)))

    def stop(self):
        self._stop.set()
        try:
            if self.ser and self.ser.is_open:
                self.ser.close()
        except Exception:
            pass


# ── Wi-Fi SSE reader thread ────────────────────────────────────────────────
class WiFiReader(threading.Thread):
    def __init__(self, ip, q):
        super().__init__(daemon=True)
        self.ip    = ip
        self.q     = q
        self._stop = threading.Event()

    def run(self):
        url = f"http://{self.ip}/events"
        try:
            with requests.get(url, stream=True, timeout=10) as resp:
                resp.raise_for_status()
                for line in resp.iter_lines(decode_unicode=True):
                    if self._stop.is_set():
                        break
                    if line.startswith("data:"):
                        _parse_and_enqueue(line[5:].strip(), self.q)
        except requests.exceptions.ConnectionError:
            self.q.put(("error", f"Cannot reach {url} — check IP and Wi-Fi"))
        except Exception as e:
            self.q.put(("error", str(e)))

    def stop(self):
        self._stop.set()


def _parse_and_enqueue(payload, q):
    parts = payload.split(",")
    if len(parts) == 4:
        try:
            wave  = float(parts[0])
            bpm   = int(parts[1])
            spo2  = int(parts[2])
            ir_dc = float(parts[3])
            q.put(("data", wave, bpm, spo2, ir_dc))
        except ValueError:
            pass


# ── Main GUI ───────────────────────────────────────────────────────────────
class PulseMonitor(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Clinical Pulse Monitor — ESP32 MAX30102")
        self.geometry("960x720")
        self.minsize(780, 580)
        self.configure(bg=C_BG)
        self.resizable(True, True)

        self._wave_buf   = [0.0] * MAX_POINTS
        self._connected  = False
        self._reader     = None
        self._data_q     = queue.Queue()
        self._mode       = tk.StringVar(value="serial")  # "serial" or "wifi"
        self._recording  = False
        self._csv_file   = None
        self._csv_writer = None

        available = list(tkfont.families())
        self._fn = next((f for f in ("Segoe UI", "Inter", "Arial") if f in available),
                        "TkDefaultFont")
        self._build_ui()
        self._refresh_ports()
        self.after(50, self._poll_queue)

    # ── UI construction ────────────────────────────────────────────────────
    def _build_ui(self):
        # Header
        top = tk.Frame(self, bg=C_CARD, height=52)
        top.pack(fill="x")
        top.pack_propagate(False)
        tk.Label(top, text=" MEDICAL MONITOR ", bg="#0c4a6e", fg="#38bdf8",
                 font=(self._fn, 9, "bold"), padx=6).pack(side="left", padx=16, pady=14)
        tk.Label(top, text="Pulse Oximetry and Waveform", bg=C_CARD, fg=C_TEXT,
                 font=(self._fn, 14, "bold")).pack(side="left", padx=8)
        tk.Label(top, text="MAX30102 · ESP32", bg=C_CARD, fg=C_MUTED,
                 font=(self._fn, 10)).pack(side="right", padx=16)

        # Mode selector bar
        mb = tk.Frame(self, bg="#0f2040", height=40)
        mb.pack(fill="x")
        mb.pack_propagate(False)
        tk.Label(mb, text="Mode:", bg="#0f2040", fg=C_MUTED,
                 font=(self._fn, 10)).pack(side="left", padx=(16, 4), pady=8)
        tk.Radiobutton(mb, text="USB Serial", variable=self._mode, value="serial",
                       bg="#0f2040", fg=C_TEXT, selectcolor="#0f2040",
                       activebackground="#0f2040", activeforeground=C_BLUE,
                       font=(self._fn, 10), command=self._on_mode_change
                       ).pack(side="left", padx=8)
        tk.Radiobutton(mb, text="Wi-Fi", variable=self._mode, value="wifi",
                       bg="#0f2040", fg=C_TEXT, selectcolor="#0f2040",
                       activebackground="#0f2040", activeforeground=C_BLUE,
                       font=(self._fn, 10), command=self._on_mode_change
                       ).pack(side="left", padx=4)

        # Connection bar
        cb = tk.Frame(self, bg="#162032", height=46)
        cb.pack(fill="x")
        cb.pack_propagate(False)

        # Serial widgets
        self._serial_frame = tk.Frame(cb, bg="#162032")
        self._serial_frame.pack(side="left", padx=(16, 0))
        tk.Label(self._serial_frame, text="COM Port:", bg="#162032", fg=C_MUTED,
                 font=(self._fn, 11)).pack(side="left", padx=(0, 4))
        self._port_var = tk.StringVar()
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("D.TCombobox", fieldbackground=C_CARD, background=C_CARD,
                        foreground=C_TEXT, selectbackground=C_CARD,
                        selectforeground=C_TEXT, arrowcolor=C_BLUE)
        self._port_combo = ttk.Combobox(self._serial_frame, textvariable=self._port_var,
                                         width=10, style="D.TCombobox", state="readonly",
                                         font=(self._fn, 11))
        self._port_combo.pack(side="left", padx=4, pady=10)
        tk.Button(self._serial_frame, text="↺", bg="#1e3a5f", fg=C_TEXT,
                  font=(self._fn, 12), relief="flat", cursor="hand2",
                  activebackground="#1e4d7a", activeforeground=C_TEXT,
                  command=self._refresh_ports, padx=4).pack(side="left", padx=2)

        # Wi-Fi widgets (hidden by default)
        self._wifi_frame = tk.Frame(cb, bg="#162032")
        tk.Label(self._wifi_frame, text="ESP32 IP:", bg="#162032", fg=C_MUTED,
                 font=(self._fn, 11)).pack(side="left", padx=(0, 4))
        self._ip_var = tk.StringVar(value="192.168.1.100")
        tk.Entry(self._wifi_frame, textvariable=self._ip_var, width=16,
                 bg=C_CARD, fg=C_TEXT, insertbackground=C_TEXT,
                 font=(self._fn, 11), relief="flat").pack(side="left", padx=4, pady=10)

        # Connect button + status
        self._conn_btn = tk.Button(cb, text="Connect", bg="#166534", fg=C_TEXT,
                                    font=(self._fn, 11, "bold"), relief="flat",
                                    cursor="hand2", activebackground="#15803d",
                                    activeforeground=C_TEXT,
                                    command=self._toggle_connection, padx=12)
        self._conn_btn.pack(side="left", padx=12)

        # CSV Record button
        self._rec_btn = tk.Button(cb, text="⏺ Record", bg="#1e293b", fg=C_MUTED,
                                   font=(self._fn, 10, "bold"), relief="flat",
                                   cursor="hand2", activebackground="#7f1d1d",
                                   activeforeground=C_TEXT,
                                   command=self._toggle_record, padx=10)
        self._rec_btn.pack(side="left", padx=4)
        self._dot_lbl = tk.Label(cb, text="●", bg="#162032", fg=C_MUTED,
                                  font=(self._fn, 14))
        self._dot_lbl.pack(side="left", padx=(8, 4))
        self._status_lbl = tk.Label(cb, text="Disconnected", bg="#162032", fg=C_MUTED,
                                     font=(self._fn, 10))
        self._status_lbl.pack(side="left")

        # Metric cards
        cards = tk.Frame(self, bg=C_BG)
        cards.pack(fill="x", padx=16, pady=(14, 0))
        self._bpm_var   = tk.StringVar(value="--")
        self._spo2_var  = tk.StringVar(value="--")
        self._pulse_var = tk.StringVar(value="No Contact")
        self._make_card(cards, "HEART RATE",   self._bpm_var,   "BPM",    C_RED,  0)
        self._make_card(cards, "BLOOD OXYGEN", self._spo2_var,  "% SpO2", C_TEAL, 1)
        self._make_card(cards, "PULSE SIGNAL", self._pulse_var, "",       C_BLUE, 2)
        cards.columnconfigure(0, weight=1)
        cards.columnconfigure(1, weight=1)
        cards.columnconfigure(2, weight=1)

        # Chart
        cf = tk.Frame(self, bg=C_CARD)
        cf.pack(fill="both", expand=True, padx=16, pady=14)
        tk.Label(cf, text="PPG Pulse Waveform", bg=C_CARD, fg=C_MUTED,
                 font=(self._fn, 10, "bold")).pack(anchor="nw", padx=12, pady=(8, 0))

        self._fig, self._ax = plt.subplots(figsize=(9, 3.2))
        self._fig.patch.set_facecolor(C_CARD)
        self._ax.set_facecolor("#111827")
        xs = list(range(MAX_POINTS))
        self._line, = self._ax.plot(xs, self._wave_buf, color=C_WAVE, linewidth=2.2)
        self._ax.set_xlim(0, MAX_POINTS - 1)
        self._ax.set_ylim(-500, 500)
        self._ax.tick_params(colors=C_MUTED, labelsize=9)
        for sp in self._ax.spines.values():
            sp.set_edgecolor(C_BORDER)
        self._ax.set_xlabel("Time", color=C_MUTED, fontsize=9)
        self._ax.set_ylabel("AC Signal", color=C_MUTED, fontsize=9)
        self._ax.grid(True, color="#1e3352", linewidth=0.6, linestyle="--")
        self._fig.tight_layout(pad=1.6)

        canvas = FigureCanvasTkAgg(self._fig, master=cf)
        canvas.draw()
        canvas.get_tk_widget().pack(fill="both", expand=True, padx=8, pady=(4, 10))
        self._anim = animation.FuncAnimation(
            self._fig, self._animate, interval=UPDATE_MS,
            blit=False, cache_frame_data=False)

        self._on_mode_change()

    def _make_card(self, parent, title, var, unit, accent, col):
        card = tk.Frame(parent, bg=C_CARD, highlightbackground=accent, highlightthickness=2)
        card.grid(row=0, column=col, padx=6, sticky="nsew", ipadx=10, ipady=6)
        tk.Label(card, text=title, bg=C_CARD, fg=C_MUTED,
                 font=(self._fn, 9, "bold")).pack(anchor="w", padx=12, pady=(10, 0))
        row = tk.Frame(card, bg=C_CARD)
        row.pack(anchor="w", padx=12, pady=(0, 10))
        tk.Label(row, textvariable=var, bg=C_CARD, fg=accent,
                 font=(self._fn, 42, "bold")).pack(side="left")
        if unit:
            tk.Label(row, text=unit, bg=C_CARD, fg=C_MUTED,
                     font=(self._fn, 12)).pack(side="left", padx=(6, 0), pady=(16, 0))

    # ── Mode toggle ────────────────────────────────────────────────────────
    def _on_mode_change(self):
        if self._connected:
            self._disconnect()
        if self._mode.get() == "serial":
            self._wifi_frame.pack_forget()
            self._serial_frame.pack(side="left", padx=(16, 0))
        else:
            self._serial_frame.pack_forget()
            self._wifi_frame.pack(side="left", padx=(16, 0))

    def _refresh_ports(self):
        if not SERIAL_OK:
            self._port_combo["values"] = ["(install pyserial)"]
            self._port_var.set("(install pyserial)")
            return
        ports = [p.device for p in serial.tools.list_ports.comports()]
        if not ports:
            ports = ["(no ports found)"]
        self._port_combo["values"] = ports
        if self._port_var.get() not in ports:
            self._port_var.set(ports[0])

    # ── Connection management ──────────────────────────────────────────────
    def _toggle_connection(self):
        if self._connected:
            self._disconnect()
        else:
            self._connect()

    def _connect(self):
        if self._reader:
            self._reader.stop()
        self._data_q = queue.Queue()

        if self._mode.get() == "serial":
            port = self._port_var.get()
            if not port or port.startswith("("):
                self._set_status("No valid COM port selected", C_RED)
                return
            self._reader = SerialReader(port, self._data_q)
            label = f"USB · {port} · {BAUD_RATE} baud"
        else:
            ip = self._ip_var.get().strip()
            if not ip:
                self._set_status("Enter ESP32 IP address", C_RED)
                return
            self._reader = WiFiReader(ip, self._data_q)
            label = f"Wi-Fi · http://{ip}/events"

        self._reader.start()
        self._connected = True
        self._conn_btn.configure(text="Disconnect", bg="#7f1d1d", activebackground="#991b1b")
        self._set_status("Connected — " + label, C_GREEN)

    def _disconnect(self):
        if self._reader:
            self._reader.stop()
            self._reader = None
        self._connected = False
        self._conn_btn.configure(text="Connect", bg="#166534", activebackground="#15803d")
        self._set_status("Disconnected", C_MUTED)
        self._bpm_var.set("--")
        self._spo2_var.set("--")
        self._pulse_var.set("No Contact")
        self._stop_recording()

    # ── CSV Recording ──────────────────────────────────────────────────────
    def _toggle_record(self):
        if self._recording:
            self._stop_recording()
        else:
            self._start_recording()

    def _start_recording(self):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        folder = os.path.dirname(os.path.abspath(__file__))
        filename = os.path.join(folder, f"ppg_{timestamp}.csv")
        self._csv_file   = open(filename, "w", newline="")
        self._csv_writer = csv.writer(self._csv_file)
        self._csv_writer.writerow(["timestamp", "wave", "bpm", "spo2", "irDC"])
        self._recording  = True
        self._rec_btn.configure(text="⏹ Stop", bg="#7f1d1d", fg=C_TEXT,
                                 activebackground="#991b1b")
        self._set_status(f"Recording → {os.path.basename(filename)}", C_RED)
        self._current_csv = filename

    def _stop_recording(self):
        if self._csv_file:
            self._csv_file.close()
            self._csv_file   = None
            self._csv_writer = None
        if self._recording:
            self._recording = False
            self._rec_btn.configure(text="⏺ Record", bg="#1e293b", fg=C_MUTED,
                                     activebackground="#7f1d1d")
            self._set_status(f"Saved: {os.path.basename(self._current_csv)}", C_GREEN)

    def _set_status(self, msg, color):
        self._status_lbl.configure(text=msg, fg=color)
        self._dot_lbl.configure(fg=color)

    # ── Data polling ───────────────────────────────────────────────────────
    def _poll_queue(self):
        try:
            while True:
                item = self._data_q.get_nowait()
                if item[0] == "data":
                    _, wave, bpm, spo2, ir_dc = item
                    self._wave_buf.pop(0)
                    self._wave_buf.append(wave)
                    nc = ir_dc < 10000
                    self._bpm_var.set("--" if (nc or bpm < 30) else str(bpm))
                    self._spo2_var.set("--" if (nc or spo2 < 70) else str(spo2))
                    self._pulse_var.set("No Contact" if nc else
                                        ("Active Pulse" if bpm > 0 else "Detecting..."))
                    # Write to CSV if recording
                    if self._recording and self._csv_writer:
                        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
                        self._csv_writer.writerow([ts, round(wave, 2), bpm, spo2, int(ir_dc)])
                elif item[0] == "error":
                    self._set_status(item[1], C_RED)
                    self._connected = False
                    self._conn_btn.configure(text="Connect", bg="#166534",
                                              activebackground="#15803d")
        except queue.Empty:
            pass
        self.after(50, self._poll_queue)

    # ── Chart animation ────────────────────────────────────────────────────
    def _animate(self, _f):
        ys = list(self._wave_buf)
        xs = list(range(len(ys)))
        self._line.set_data(xs, ys)
        mn, mx = min(ys), max(ys)
        pad = max(abs(mx - mn) * 0.25, 60)
        self._ax.set_ylim(mn - pad, mx + pad)
        for c in self._ax.collections:
            c.remove()
        self._ax.fill_between(xs, ys, alpha=0.13, color=C_WAVE)
        return (self._line,)

    def on_close(self):
        if self._reader:
            self._reader.stop()
        self._stop_recording()
        plt.close("all")
        self.destroy()


if __name__ == "__main__":
    app = PulseMonitor()
    app.protocol("WM_DELETE_WINDOW", app.on_close)
    app.mainloop()
