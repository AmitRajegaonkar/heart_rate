/*
 * ESP32 + MAX30102 — Dual Mode: USB Serial + Wi-Fi SSE
 * -----------------------------------------------------
 * Streams DATA: over USB (for Python app via Serial)
 * AND serves live waveform via Wi-Fi SSE at http://<IP>/events
 * (for Python app via Wi-Fi, or any browser)
 *
 * Wiring:
 *   VIN  → 3.3 V   SDA → GPIO 21   SCL → GPIO 22   GND → GND
 */

#include <Arduino.h>
#include <Wire.h>
#include <WiFi.h>
#include <WebServer.h>
#include "MAX30105.h"
#include "heartRate.h"

// ── Wi-Fi credentials ──────────────────────────────────────────────────────
const char* WIFI_SSID = "7ii_2";
const char* WIFI_PASS = "16988444";

// ── I2C pins ───────────────────────────────────────────────────────────────
#define SDA_PIN 21
#define SCL_PIN 22

// ── Neck sensing thresholds ────────────────────────────────────────────────
#define CONTACT_THRESHOLD 12000
#define RESET_THRESHOLD    4000

// ── Globals ────────────────────────────────────────────────────────────────
MAX30105  particleSensor;
WebServer server(80);
WiFiClient sseClient;
bool       sseActive = false;

// ── Medical PPG DSP Filters (High-Pass DC Blocker + 2-Stage Low-Pass) ──────
struct PPGFilter {
  float dcAlpha; // DC blocker coefficient (~0.94 for ~0.4 Hz high-pass at 25Hz)
  float lpAlpha; // Low-pass coefficient (~0.45 for ~4.0 Hz low-pass at 25Hz)
  float w;
  float lp1;
  float lp2;

  void init(float highPassCutoffAlpha = 0.94f, float lowPassAlpha = 0.45f) {
    dcAlpha = highPassCutoffAlpha;
    lpAlpha = lowPassAlpha;
    reset();
  }

  float process(float x) {
    // 1. DC-Removal (High-Pass Filter removes slow breathing baseline wander)
    float curr_w = x + dcAlpha * w;
    float hp = curr_w - w;
    w = curr_w;

    // 2. Cascaded 2-Stage Low-Pass (Removes muscle tremors & 50/60Hz noise)
    lp1 = lp1 * (1.0f - lpAlpha) + hp * lpAlpha;
    lp2 = lp2 * (1.0f - lpAlpha) + lp1 * lpAlpha;
    return lp2;
  }

  void reset() {
    w   = 0.0f;
    lp1 = 0.0f;
    lp2 = 0.0f;
  }
};

PPGFilter irFilter;
PPGFilter redFilter;

// Heart Rate
const byte RATE_SIZE = 6;
byte  rates[RATE_SIZE];
byte  rateSpot = 0;
long  lastBeat = 0;
int   beatAvg  = 0;

// DC levels for SpO2 & contact tracking
double irDC  = 0, redDC = 0;
double filteredIR = 0, filteredRed = 0;

// SpO2
long  minRed = 999999, maxRed = 0;
long  minIR  = 999999, maxIR  = 0;
float spo2Val = 0;

// ── SSE Handlers ───────────────────────────────────────────────────────────
void handleEvents() {
  sseClient = server.client();
  sseClient.print(
    "HTTP/1.1 200 OK\r\n"
    "Content-Type: text/event-stream\r\n"
    "Cache-Control: no-cache\r\n"
    "Connection: keep-alive\r\n"
    "Access-Control-Allow-Origin: *\r\n"
    "\r\n"
  );
  sseActive = true;
}

void handleRoot() {
  server.send(200, "text/plain",
    "ESP32 MAX30102 Pulse Monitor\n"
    "Connect Python app to: http://" + WiFi.localIP().toString() + "/events\n"
    "Or use USB Serial at 115200 baud.\n"
  );
}

// ── Setup ──────────────────────────────────────────────────────────────────
void setup() {
  Serial.begin(115200);
  delay(400);
  Serial.println("\n=== Dual Mode: USB + Wi-Fi (Stabilized Baseline) ===");

  irFilter.init(0.94f, 0.45f);
  redFilter.init(0.94f, 0.45f);

  Wire.begin(SDA_PIN, SCL_PIN);
  Wire.setClock(100000);

  if (!particleSensor.begin(Wire, I2C_SPEED_STANDARD)) {
    Serial.println("ERROR: MAX30102 not found!");
    while (true) { delay(1000); }
  }

  // ── NECK / CAROTID optimised settings ─────────────────────────────────
  // 0x3F (~12mA) is correct for neck — thick tissue absorbs most IR light
  // so irDC stays in 15,000–50,000 range (well below ADC ceiling of 262143).
  // Sample average = 8  → smooths out neck muscle motion artefacts
  // Sample rate   = 200 Hz → effective FIFO rate = 25 Hz
  // Pulse width   = 411 us → maximum integration = best SNR for weak signal
  particleSensor.setup(0x3F, 8, 2, 200, 411, 4096);
  particleSensor.setPulseAmplitudeRed(0x3F);  // ~12 mA Red
  particleSensor.setPulseAmplitudeIR(0x3F);   // ~12 mA IR

  // Connect to Wi-Fi
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  Serial.print("Connecting to Wi-Fi");
  int attempts = 0;
  while (WiFi.status() != WL_CONNECTED && attempts < 20) {
    delay(500); Serial.print("."); attempts++;
  }
  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("\nWi-Fi connected! IP: " + WiFi.localIP().toString());
    Serial.println(">>> Python Wi-Fi URL: http://" + WiFi.localIP().toString() + "/events <<<");
  } else {
    Serial.println("\n!!! Wi-Fi FAILED — check SSID/password and 2.4GHz band !!!");
    Serial.println("USB Serial mode still active.");
  }

  server.on("/", HTTP_GET, handleRoot);
  server.on("/events", HTTP_GET, handleEvents);
  server.begin();

  Serial.println("USB Serial also active at 115200 baud.");
  Serial.println("Ready.");
}

// ── Loop ───────────────────────────────────────────────────────────────────
void loop() {
  server.handleClient();

  // Drain FIFO
  particleSensor.check();
  while (particleSensor.available()) {
    long irRaw  = particleSensor.getFIFOIR();
    long redRaw = particleSensor.getFIFORed();
    particleSensor.nextSample();

    if (irRaw > CONTACT_THRESHOLD) {
      // Slow exponential moving average for DC baseline (used for SpO2 & contact)
      // Slow time constant (~3s) so it does NOT follow or distort individual heart pulses
      irDC  = irDC  * 0.985 + (double)irRaw  * 0.015;
      redDC = redDC * 0.985 + (double)redRaw * 0.015;

      // Apply High-Pass (DC Blocker) + 2-Stage Low-Pass Filter
      filteredIR  = irFilter.process((float)irRaw);
      filteredRed = redFilter.process((float)redRaw);

      if (redRaw < minRed) minRed = redRaw;
      if (redRaw > maxRed) maxRed = redRaw;
      if (irRaw  < minIR)  minIR  = irRaw;
      if (irRaw  > maxIR)  maxIR  = irRaw;

      if (checkForBeat(irRaw)) {
        unsigned long now = millis();
        if (lastBeat != 0) {
          float bpm = 60000.0f / (float)(now - lastBeat);
          if (bpm >= 35.0f && bpm <= 200.0f) {
            rates[rateSpot++] = (byte)bpm;
            rateSpot %= RATE_SIZE;
            int sum = 0, count = 0;
            for (byte x = 0; x < RATE_SIZE; x++) {
              if (rates[x] > 0) { sum += rates[x]; count++; }
            }
            if (count > 0) beatAvg = sum / count;
          }
        }
        lastBeat = now;
      }

    } else {
      if (irRaw < RESET_THRESHOLD) {
        beatAvg = 0; lastBeat = 0; spo2Val = 0;
        irDC = 0; redDC = 0;
        filteredIR = 0; filteredRed = 0;
        irFilter.reset();
        redFilter.reset();
        for (byte i = 0; i < RATE_SIZE; i++) rates[i] = 0;
      }
    }
  }

  // SpO2 every 3s
  static unsigned long lastSpO2Time = 0;
  if (millis() - lastSpO2Time > 3000 && irDC > 0 && redDC > 0) {
    lastSpO2Time = millis();
    double redAC = maxRed - minRed;
    double irAC  = maxIR  - minIR;
    minRed = 999999; maxRed = 0;
    minIR  = 999999; maxIR  = 0;
    if (irAC > 50 && redAC > 20) {
      double R    = (redAC / redDC) / (irAC / irDC);
      double calc = 104.0 - 17.0 * R;
      if (calc >= 85.0 && calc <= 100.0) {
        spo2Val = (spo2Val < 1.0) ? calc : (spo2Val * 0.8 + calc * 0.2);
      }
    }
  }

  // Send data every 20ms — both USB Serial and Wi-Fi SSE
  static unsigned long lastSend = 0;
  if (millis() - lastSend >= 20) {
    lastSend = millis();

    // Format: DATA:wave,bpm,spo2,irDC
    String payload = String(filteredIR, 1) + "," +
                     String(beatAvg)       + "," +
                     String((int)spo2Val)  + "," +
                     String((long)irDC);

    // USB Serial
    Serial.print("DATA:"); Serial.println(payload);

    // Wi-Fi SSE
    if (sseActive && sseClient.connected()) {
      sseClient.print("data: " + payload + "\r\n\r\n");
    } else {
      sseActive = false;
    }
  }

  // Print IP every 10 seconds so you can always find it in Serial Monitor
  static unsigned long lastIPPrint = 0;
  if (millis() - lastIPPrint >= 10000) {
    lastIPPrint = millis();
    if (WiFi.status() == WL_CONNECTED) {
      Serial.println(">>> IP: " + WiFi.localIP().toString() + " | http://" + WiFi.localIP().toString() + "/events <<<");
    } else {
      Serial.println("!!! Wi-Fi disconnected — check router !!!");
    }
  }
}

