# ESP32 + MAX30102 — Clinical Pulse Monitor
## Complete Setup Guide: PlatformIO → Upload → Python Dashboard

---

## 📁 Project Structure

```
heart/
├── pulse_monitor.py        ← Python desktop GUI (run this to view live data)
├── requirements.txt        ← Python dependencies
├── README.md               ← This file
└── heart/                   ← PlatformIO ESP32 firmware project
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
3. Browse to `c:\Users\amitr\Desktop\heart\heart` → Click **Open**

### Step 3 — Install the Library

PlatformIO will automatically install the **SparkFun MAX3010x** library listed in `platformio.ini` on first build. No manual steps needed.

### Step 3b — Configure Wi-Fi Credentials (Optional for Wireless Mode)

If you plan to stream live data wirelessly over Wi-Fi:
1. Open [`heart/src/main.cpp`](file:///c:/Users/amitr/Desktop/heart/heart/src/main.cpp)
2. Locate lines 20–21:
   ```cpp
   // ── Wi-Fi credentials ──────────────────────────────────────────────────────
   const char* WIFI_SSID = "YOUR_WIFI_SSID";
   const char* WIFI_PASS = "YOUR_WIFI_PASSWORD";
   ```
3. Replace `"YOUR_WIFI_SSID"` and `"YOUR_WIFI_PASSWORD"` with your 2.4 GHz Wi-Fi router or mobile hotspot details.
4. Save the file (`Ctrl+S`).

> ℹ️ *Note: ESP32 only connects to **2.4 GHz** Wi-Fi networks (not 5 GHz).*

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
- You should see:
  ```text
  === ESP32 Pulse Monitor (Text Mode) ===
  Connecting to Wi-Fi.....
  Wi-Fi connected! IP: 192.168.1.150
  >>> Python Wi-Fi URL: http://192.168.1.150/events <<<
  Heart Rate: 72 BPM | SpO2: 98 % | Wave: 12.3 | IR DC: 45231
  ```
- ✅ Note the **IP address** printed (e.g. `192.168.1.150`) if you wish to use Wi-Fi mode.
- ❌ **Important:** Close the PlatformIO Serial Monitor before opening the Python app when using USB mode.

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
Successfully installed pyserial-3.5 matplotlib-3.9.2 requests-2.32.3
```

### Step 4 — Run the Dashboard

```powershell
python pulse_monitor.py
```

---

## 🖥️ Using the Dashboard

You can use the dashboard in either **USB Serial Mode** or **Wireless Wi-Fi Mode**:

### Mode A: USB Serial Mode (Default)
1. Select the **USB Serial** radio button.
2. Choose your **COM Port** from the dropdown (e.g. `COM4` or `COM5`).
   - If not listed, click **↺** to refresh.
3. Click **Connect**.

### Mode B: Wireless Wi-Fi Mode
1. Select the **Wi-Fi** radio button at the top bar.
2. Enter the **ESP32 IP address** (e.g. `192.168.1.150` — shown in Serial Monitor during ESP32 boot).
3. Click **Connect** (connects directly to `http://<IP>/events` via SSE).

---

### Dashboard Readings & Features

| Reading | Normal Range | Notes |
|---|---|---|
| Heart Rate | 60–100 BPM | Calculated over recent detected beats |
| Blood Oxygen | 95–100 % | Hold still for steady reading |
| Pulse Signal | Active Pulse | Shows "No Contact" if sensor detached |
| PPG Waveform | Smooth peaks | Starts from the left ($x=0$) on white background |
| ⏺ Record | Text File Log | Records session with timestamps to `ppg_<timestamp>.txt` |

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

The ESP32 sends formatted text over USB Serial (at 115200 baud) and Wi-Fi SSE (`/events`):

```text
Heart Rate: <bpm> BPM | SpO2: <spo2> % | Wave: <wave> | IR DC: <irDC>
```

| Field | Type | Description |
|---|---|---|
| `Heart Rate` | int / text | Average heart rate over recent detected beats (`--` if detecting) |
| `SpO2` | int / text | Blood oxygen % calculated from Red/IR AC/DC ratio |
| `Wave` | float | Filtered pulsatile PPG AC signal (centered at 0) |
| `IR DC` | long | IR baseline amplitude (finger/carotid contact quality) |

To log raw data to a text file using Python:
```python
import serial, time
ser = serial.Serial('COM5', 115200)
with open('ppg_log.txt', 'w', encoding='utf-8') as f:
    while True:
        line = ser.readline().decode('utf-8', errors='ignore').strip()
        if line:
            f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {line}\n")
            f.flush()
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
