# ESP32 + MAX30102 — Clinical Pulse Monitor
## Complete Setup Guide: PlatformIO → Upload → Python Dashboard

---

## 📁 Project Structure

```
heart/
├── pulse_monitor.py        ← Python desktop GUI (run this to view live data)
├── requirements.txt        ← Python dependencies
├── README.md               ← This file
└── test/                   ← PlatformIO ESP32 firmware project
    ├── platformio.ini      ← Board & library config
    └── src/
        └── main.cpp        ← ESP32 firmware (reads MAX30102, sends over USB)
```

---

## 🔌 Hardware Wiring

| MAX30102 Pin | ESP32 Pin |
|---|---|
| VIN | 3.3V |
| GND | GND |
| SDA | GPIO 21 |
| SCL | GPIO 22 |

> ⚠️ **Do NOT connect SDA to D2 (GPIO2) or D15 (GPIO15)** — these are ESP32 strapping pins and will block flashing.

Keep wire length **under 30 cm** between sensor and ESP32.

---

## ⚙️ Part 1 — ESP32 Firmware Setup (PlatformIO)

### Step 1 — Install VS Code + PlatformIO

1. Download and install [VS Code](https://code.visualstudio.com/)
2. Open VS Code → Extensions (Ctrl+Shift+X) → Search **PlatformIO IDE** → Install
3. Restart VS Code

### Step 2 — Open the Firmware Project

1. In VS Code, click the **PlatformIO Home** icon (ant icon in sidebar)
2. Click **Open Project**
3. Browse to `c:\Users\amitr\Desktop\heart\test` → Click **Open**

### Step 3 — Install the Library

PlatformIO will automatically install the **SparkFun MAX3010x** library listed in `platformio.ini` on first build. No manual steps needed.

### Step 4 — Build the Firmware

- Click the **✓ Build** button (bottom toolbar) or press `Ctrl+Alt+B`
- Wait for: `[SUCCESS]`

### Step 5 — Upload to ESP32

1. Plug in your ESP32 via USB
2. Click the **→ Upload** button (bottom toolbar) or press `Ctrl+Alt+U`
3. If upload fails with "Wrong boot mode":
   - **Hold the BOOT button** on the ESP32 while clicking Upload
   - Release after "Connecting..." appears

### Step 6 — Verify with Serial Monitor

- Click the **🔌 Serial Monitor** icon in PlatformIO
- Set baud rate to **115200**
- Place finger on sensor — you should see:
  ```
  === USB Pulse Monitor Ready ===
  Sensor OK — streaming DATA: to Python app
  DATA:12.3,0,0,45231
  Beat! BPM=73.2
  DATA:22.1,73,97,46500
  ```
- ✅ If you see `DATA:` lines → firmware is working
- ❌ Close Serial Monitor before running Python app (they share the same COM port)

---

## 🐍 Part 2 — Python Dashboard Setup

### Step 1 — Install Python

Download Python 3.10+ from https://www.python.org/downloads/

> During install: check **"Add Python to PATH"**

Verify in PowerShell:
```powershell
python --version
```

### Step 2 — Create Virtual Environment

Open **PowerShell** and run:

```powershell
cd c:\Users\amitr\Desktop\heart

# Create virtual environment
python -m venv venv

# Activate it (Windows PowerShell)
.\venv\Scripts\Activate.ps1
```

> If you get a "scripts disabled" error, run this first:
> ```powershell
> Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
> ```
> Then re-run `.\venv\Scripts\Activate.ps1`

Your prompt should now show `(venv)`:
```
(venv) PS C:\Users\amitr\Desktop\heart>
```

### Step 3 — Install Dependencies

With the virtual environment active:

```powershell
pip install -r requirements.txt
```

Expected output:
```
Successfully installed pyserial-3.5 matplotlib-3.9.2
```

### Step 4 — Run the Dashboard

```powershell
python pulse_monitor.py
```

---

## 🖥️ Using the Dashboard

1. A GUI window opens
2. Select your **COM port** from the dropdown (e.g. `COM4`)
   - If unsure: Device Manager → Ports (COM & LPT)
3. Click **Connect**
4. Status bar turns green: `Connected - COM4 - 115200 baud`
5. Place finger firmly (but gently) on the MAX30102 sensor
6. Wait ~5 seconds for BPM to stabilize

### Dashboard Readings

| Reading | Normal Range | Notes |
|---|---|---|
| Heart Rate | 60–100 BPM | Takes 4–5 beats to calculate |
| Blood Oxygen | 95–100 % | Hold still for accuracy |
| Pulse Signal | Active Pulse | Shows "No Contact" if finger absent |
| PPG Waveform | Smooth peaks | Each peak = one heartbeat |

---

## 🔧 Troubleshooting

| Problem | Fix |
|---|---|
| `ERROR: MAX30102 not found!` | Check wiring — SDA→21, SCL→22, VIN→3.3V |
| Upload fails "Wrong boot mode" | Hold BOOT button during upload |
| COM port not in dropdown | Click **Refresh** in the Python app |
| `No module named serial` | Run `pip install -r requirements.txt` in active venv |
| BPM shows `--` | Press finger more firmly; wait 10 seconds |
| SpO2 shows `--` | Hold completely still; takes ~10 seconds |
| Python app + Serial Monitor both open | Close PlatformIO Serial Monitor first |

---

## 📡 Data Format (For Researchers)

The ESP32 sends one line every 20 ms over USB Serial at 115200 baud:

```
DATA:<wave>,<bpm>,<spo2>,<irDC>
```

| Field | Type | Description |
|---|---|---|
| `wave` | float | Filtered AC PPG signal (bandpass 0.5–3.5 Hz) |
| `bpm` | int | Average heart rate over last 4 beats |
| `spo2` | int | Blood oxygen % (estimated from Red/IR ratio) |
| `irDC` | long | Raw IR DC baseline (finger contact quality) |

To log raw data to CSV for offline analysis:
```python
import serial, csv, time
ser = serial.Serial('COM4', 115200)
with open('ppg_data.csv', 'w', newline='') as f:
    w = csv.writer(f)
    w.writerow(['timestamp', 'wave', 'bpm', 'spo2', 'irDC'])
    while True:
        line = ser.readline().decode().strip()
        if line.startswith('DATA:'):
            parts = line[5:].split(',')
            w.writerow([time.time()] + parts)
```

---

## 🔬 For PhD Research Use

- The PPG waveform (`wave`) is the primary signal for analysis
- `irDC > 50000` confirms solid sensor contact
- For neck placement: increase LED brightness in `main.cpp`:
  ```cpp
  particleSensor.setup(0x3F, 8, 2, 200, 411, 4096);
  ```
- Validate BPM against a medical reference (Polar H10, ECG) using Bland-Altman analysis
- Raw waveform can be post-processed with Pan-Tompkins or Elgendi algorithm for research-grade peak detection

---

## 📋 Quick Reference

```powershell
# Every time you want to run the dashboard:
cd c:\Users\amitr\Desktop\heart
.\venv\Scripts\Activate.ps1
python pulse_monitor.py
```
