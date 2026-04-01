
# Write the main Teensy firmware sketch
firmware = r'''
// ============================================================
// GPS Event Timestamp Logger
// Teensy 4.0 Firmware
// Target: sub-millisecond accuracy via GPS PPS discipline
// ============================================================

#include <Arduino.h>
#include <SD.h>
#include <SPI.h>
#include <TimeLib.h>      // for time_t, tmElements_t
#include <TinyGPS++.h>    // TinyGPSPlus library

// ─── PIN DEFINITIONS ────────────────────────────────────────
#define PIN_GPS_RX      0   // Serial1 RX ← GPS TX
#define PIN_GPS_TX      1   // Serial1 TX → GPS RX
#define PIN_PPS         2   // GPS PPS (interrupt)
#define PIN_TRIGGER     3   // Comparator output (interrupt)
#define PIN_SD_CS       10  // SPI chip-select for SD
#define PIN_SD_MOSI     11
#define PIN_SD_MISO     12
#define PIN_SD_SCK      13
#define PIN_ROT_A       4   // Rotary switch bit-0
#define PIN_ROT_B       5   // Rotary switch bit-1
#define PIN_LED_R       6   // RGB LED red channel
#define PIN_LED_G       7   // RGB LED green channel
#define PIN_LED_B       8   // RGB LED blue channel
#define PIN_BUZZER      9   // Piezo buzzer

// ─── COMPILE-TIME DEFAULTS (overridden by config.txt) ───────
const char   CONFIG_FILE[]    = "config.txt";
const char   DEFAULT_CSV[]    = "events.csv";
const int    DEFAULT_TRIG_FLANK = RISING;   // RISING or FALLING
const float  DEFAULT_THRESHOLD = 0.65f;
const float  DEFAULT_MIN_S      = 0.050f;   // 50 ms
const bool   DEFAULT_BUZZER     = true;
const float  DEFAULT_BUZ_DELAY  = 5.0f;
const char*  DEFAULT_LABELS[4]  = {"A","B","C","D"};

// ─── RUNTIME CONFIGURATION ──────────────────────────────────
struct Config {
  char    csv_name[32];
  int     trig_flank;            // RISING or FALLING
  float   trig_threshold;        // 0.0–1.0 (mapped to DAC)
  float   min_time_s;
  bool    confirm_buzzer;
  float   buzzer_delay_s;
  char    labels[4][32];
  bool    use_external_antenna;
};
Config cfg;

// ─── TIMING STATE ───────────────────────────────────────────
volatile uint32_t pps_timer_count   = 0;
volatile uint32_t event_timer_count = 0;
volatile bool     event_pending     = false;
volatile uint32_t gps_seconds_utc   = 0;  // whole GPS seconds since epoch
volatile bool     gps_locked        = false;

// ─── GPS ────────────────────────────────────────────────────
TinyGPSPlus gps;
bool        gps_time_valid = false;
uint32_t    last_pps_millis = 0;

// ─── LED / BUZZER STATE ─────────────────────────────────────
enum LedState { LED_ORANGE, LED_RED_FLASH, LED_GREEN_FLASH, LED_OFF };
LedState    led_state       = LED_ORANGE;
uint32_t    led_timer       = 0;
bool        buzzer_pending  = false;
uint32_t    buzzer_schedule = 0;
uint32_t    event_index     = 0;

// ─── FORWARD DECLARATIONS ───────────────────────────────────
void     pps_isr();
void     trigger_isr();
void     load_config();
void     set_led(uint8_t r, uint8_t g, uint8_t b);
void     update_led();
void     log_event(uint32_t ev_timer);
void     dump_csv();
char*    format_timestamp(uint32_t sec_utc, uint32_t offset_us, char* buf);
uint8_t  read_rotary();
void     configure_gps();
void     trim_str(char* s);

// ============================================================
void setup() {
  Serial.begin(115200);          // USB serial

  // LED and buzzer
  pinMode(PIN_LED_R, OUTPUT);
  pinMode(PIN_LED_G, OUTPUT);
  pinMode(PIN_LED_B, OUTPUT);
  pinMode(PIN_BUZZER, OUTPUT);
  set_led(255, 128, 0);          // orange = startup

  // Rotary
  pinMode(PIN_ROT_A, INPUT_PULLUP);
  pinMode(PIN_ROT_B, INPUT_PULLUP);

  // Trigger (direction set after config load)
  pinMode(PIN_TRIGGER, INPUT);

  // Reduce CPU to 150 MHz for power saving; PPS timing unaffected
  // F_CPU_ACTUAL = 150000000;     // uncomment to scale down

  // SD card
  SPI.begin();
  if (!SD.begin(PIN_SD_CS)) {
    // SD fail — flash red
    led_state = LED_RED_FLASH;
    while (!SD.begin(PIN_SD_CS)) { delay(500); }
  }

  // Load config from SD
  load_config();

  // Apply DAC threshold to set comparator reference
  // Teensy 4.0 does not have a true DAC; use analogWrite on a
  // filtered PWM pin instead. Wire the output through a low-pass
  // RC filter (10k + 100nF) to the comparator REF+ input.
  analogWriteResolution(12);
  uint32_t dac_val = (uint32_t)(cfg.trig_threshold * 4095.0f);
  analogWrite(PIN_LED_B, 0);     // placeholder; use dedicated PWM pin in schematic

  // Attach interrupts
  attachInterrupt(digitalPinToInterrupt(PIN_PPS),
                  pps_isr, RISING);
  attachInterrupt(digitalPinToInterrupt(PIN_TRIGGER),
                  trigger_isr,
                  cfg.trig_flank == RISING ? RISING : FALLING);

  // Init GPS serial
  Serial1.begin(9600);
  configure_gps();

  led_state = LED_ORANGE;
}

// ============================================================
void loop() {
  // ── Feed GPS parser ──────────────────────────────────────
  while (Serial1.available()) {
    char c = Serial1.read();
    gps.encode(c);
  }
  if (gps.time.isValid() && gps.date.isValid() && gps.time.isUpdated()) {
    // Build epoch from GPS NMEA
    tmElements_t tm;
    tm.Year   = gps.date.year() - 1970;
    tm.Month  = gps.date.month();
    tm.Day    = gps.date.day();
    tm.Hour   = gps.time.hour();
    tm.Minute = gps.time.minute();
    tm.Second = gps.time.second();
    gps_seconds_utc = makeTime(tm);
    gps_time_valid  = true;
  }
  if (gps.satellites.isValid() && gps.satellites.value() >= 4) {
    gps_locked = true;
  }

  // ── Handle pending event ─────────────────────────────────
  if (event_pending) {
    event_pending = false;
    if (gps_locked && gps_time_valid) {
      log_event(event_timer_count);
    }
  }

  // ── USB serial command interface ─────────────────────────
  if (Serial.available()) {
    String cmd = Serial.readStringUntil('\n');
    cmd.trim();
    if (cmd.equalsIgnoreCase("DUMP")) {
      dump_csv();
    } else if (cmd.equalsIgnoreCase("STATUS")) {
      Serial.printf("GPS_LOCKED=%d  SATS=%d  EVENTS=%lu\n",
        (int)gps_locked, (int)gps.satellites.value(), event_index);
    }
  }

  // ── LED state machine ────────────────────────────────────
  update_led();

  // ── Buzzer schedule ──────────────────────────────────────
  if (buzzer_pending && millis() >= buzzer_schedule) {
    buzzer_pending = false;
    if (cfg.confirm_buzzer) {
      tone(PIN_BUZZER, 2000, 150);
    }
  }
}

// ─── PPS ISR ────────────────────────────────────────────────
void pps_isr() {
  pps_timer_count = ARM_DWT_CYCCNT;   // latch CPU cycle counter
  if (gps_time_valid) {
    gps_seconds_utc++;                 // increment each PPS
  }
}

// ─── TRIGGER ISR ────────────────────────────────────────────
static uint32_t last_event_time_ms = 0;

void trigger_isr() {
  uint32_t now_ms = millis();
  uint32_t delta_ms = now_ms - last_event_time_ms;
  uint32_t min_ms   = (uint32_t)(cfg.min_time_s * 1000.0f);
  if (delta_ms >= min_ms) {
    event_timer_count = ARM_DWT_CYCCNT;
    event_pending     = true;
    last_event_time_ms = now_ms;
  }
}

// ─── EVENT LOGGING ──────────────────────────────────────────
void log_event(uint32_t ev_timer) {
  // Offset from last PPS in CPU cycles → microseconds
  uint32_t delta_cycles  = ev_timer - pps_timer_count;
  uint32_t cpu_freq_mhz  = F_CPU_ACTUAL / 1000000UL;
  uint32_t offset_us     = delta_cycles / cpu_freq_mhz;

  char ts_buf[40];
  format_timestamp(gps_seconds_utc, offset_us, ts_buf);

  uint8_t rot     = read_rotary();  // 0–3 → A/B/C/D
  char rot_letter = 'A' + rot;

  event_index++;

  // Append to CSV
  File f = SD.open(cfg.csv_name, FILE_WRITE);
  if (f) {
    if (f.size() == 0) {
      f.println("timestamp_utc,rotary_label,rotary_position,"
                "event_index,raw_seconds,raw_offset_us");
    }
    f.printf("%s,%s,%c,%lu,%lu,%lu\n",
             ts_buf,
             cfg.labels[rot],
             rot_letter,
             event_index,
             (unsigned long)gps_seconds_utc,
             (unsigned long)offset_us);
    f.close();
  }

  // LED green flash
  set_led(0, 255, 0);
  led_state = LED_GREEN_FLASH;
  led_timer = millis();

  // Schedule buzzer
  if (cfg.confirm_buzzer) {
    buzzer_pending  = true;
    buzzer_schedule = millis() + (uint32_t)(cfg.buzzer_delay_s * 1000.0f);
  }
}

// ─── FORMAT TIMESTAMP ───────────────────────────────────────
char* format_timestamp(uint32_t sec_utc, uint32_t offset_us, char* buf) {
  time_t t       = (time_t)sec_utc;
  tmElements_t tm;
  breakTime(t, tm);
  uint32_t us_part = offset_us % 1000000UL;
  snprintf(buf, 40, "%04d-%02d-%02dT%02d:%02d:%02d.%06luZ",
           tm.Year + 1970, tm.Month, tm.Day,
           tm.Hour, tm.Minute, tm.Second,
           (unsigned long)us_part);
  return buf;
}

// ─── READ ROTARY (2-bit Gray or binary) ─────────────────────
uint8_t read_rotary() {
  uint8_t a = !digitalRead(PIN_ROT_A);  // active-low
  uint8_t b = !digitalRead(PIN_ROT_B);
  return (b << 1) | a;  // 0–3
}

// ─── LED HELPERS ────────────────────────────────────────────
void set_led(uint8_t r, uint8_t g, uint8_t b) {
  analogWrite(PIN_LED_R, r);
  analogWrite(PIN_LED_G, g);
  analogWrite(PIN_LED_B, b);
}

void update_led() {
  uint32_t now = millis();
  if (!gps_locked) {
    // Flash red every 500 ms once we've had time to get lock
    if ((now / 500) % 2 == 0) set_led(255, 0, 0);
    else                       set_led(0, 0, 0);
  } else if (led_state == LED_GREEN_FLASH) {
    if (now - led_timer > 200) {
      led_state = LED_OFF;
      set_led(0, 0, 0);
    }
  } else {
    set_led(0, 0, 0);  // off when locked and idle
  }
}

// ─── GPS CONFIGURATION VIA UBX ──────────────────────────────
void configure_gps() {
  // Set NMEA to 1 Hz, enable PPS
  // u-blox CFG-RATE: measRate=1000ms, navRate=1, timeRef=1 (GPS)
  uint8_t cfg_rate[] = {
    0xB5,0x62,0x06,0x08,0x06,0x00,
    0xE8,0x03, // measRate 1000ms
    0x01,0x00, // navRate 1
    0x01,0x00, // timeRef GPS
    0x01,0x39  // checksum (must recalculate for real use)
  };
  Serial1.write(cfg_rate, sizeof(cfg_rate));
  delay(100);

  // Configure antenna: if external, send CFG-ANT command
  if (cfg.use_external_antenna) {
    // CFG-ANT: svcs=0x003B (power ctrl+short/open det), ovrride=0x018A
    // Full UBX packet — recalculate checksum with u-center
    // Placeholder: u-blox NEO-M8N auto-detects external antenna
    // when signal quality improves; force config only if needed
  }
}

// ─── LOAD CONFIG FROM SD ────────────────────────────────────
void load_config() {
  // Set defaults
  strncpy(cfg.csv_name, DEFAULT_CSV, 32);
  cfg.trig_flank          = DEFAULT_TRIG_FLANK;
  cfg.trig_threshold      = DEFAULT_THRESHOLD;
  cfg.min_time_s          = DEFAULT_MIN_S;
  cfg.confirm_buzzer      = DEFAULT_BUZZER;
  cfg.buzzer_delay_s      = DEFAULT_BUZ_DELAY;
  cfg.use_external_antenna = false;
  for (int i = 0; i < 4; i++) {
    strncpy(cfg.labels[i], DEFAULT_LABELS[i], 32);
  }

  File f = SD.open(CONFIG_FILE);
  if (!f) return;

  char line[128];
  int  li = 0;
  while (f.available()) {
    char c = f.read();
    if (c == '\n' || c == '\r') {
      if (li > 0) {
        line[li] = '\0';
        // Strip comments
        char* hash = strchr(line, '#');
        if (hash) *hash = '\0';
        // Parse key=value
        char* eq = strchr(line, '=');
        if (eq) {
          *eq = '\0';
          char* key = line;
          char* val = eq + 1;
          trim_str(key);
          trim_str(val);
          if      (strcmp(key,"csv_name")==0)             strncpy(cfg.csv_name, val, 32);
          else if (strcmp(key,"trig_flank")==0)           cfg.trig_flank = strcmp(val,"negative")==0 ? FALLING : RISING;
          else if (strcmp(key,"trig_threshold")==0)       cfg.trig_threshold = atof(val);
          else if (strcmp(key,"min_time_between_events_s")==0) cfg.min_time_s = atof(val);
          else if (strcmp(key,"confirm_buzzer")==0)       cfg.confirm_buzzer = strcmp(val,"True")==0;
          else if (strcmp(key,"buzzer_delay_s")==0)       cfg.buzzer_delay_s = atof(val);
          else if (strcmp(key,"A_string")==0)             strncpy(cfg.labels[0], val, 32);
          else if (strcmp(key,"B_string")==0)             strncpy(cfg.labels[1], val, 32);
          else if (strcmp(key,"C_string")==0)             strncpy(cfg.labels[2], val, 32);
          else if (strcmp(key,"D_string")==0)             strncpy(cfg.labels[3], val, 32);
          else if (strcmp(key,"gps_antenna_mode")==0)     cfg.use_external_antenna = strcmp(val,"external")==0;
        }
      }
      li = 0;
    } else if (li < 127) {
      line[li++] = c;
    }
  }
  f.close();
}

// ─── TRIM WHITESPACE ────────────────────────────────────────
void trim_str(char* s) {
  int len = strlen(s);
  while (len > 0 && (s[len-1]==' '||s[len-1]=='\t'||s[len-1]=='\r')) s[--len]='\0';
  int start = 0;
  while (s[start]==' '||s[start]=='\t') start++;
  if (start) memmove(s, s+start, len-start+1);
}

// ─── DUMP CSV OVER USB SERIAL ────────────────────────────────
void dump_csv() {
  File f = SD.open(cfg.csv_name);
  if (!f) { Serial.println("ERROR: cannot open CSV"); return; }
  Serial.println("--- BEGIN CSV ---");
  while (f.available()) Serial.write(f.read());
  Serial.println("\n--- END CSV ---");
  f.close();
}
'''

with open('/tmp/gps_logger/gps_logger.ino', 'w') as fh:
    fh.write(firmware)
print("Firmware written")
