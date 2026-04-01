// ============================================================
// GPS Event Timestamp Logger  –  gps_logger.ino
// Teensy 4.0  |  sub-millisecond UTC event timestamping
//
// Libraries required (install via Arduino Library Manager):
//   TinyGPSPlus   by Mikal Hart
//   Time          by Michael Margolis
// ============================================================

#include <Arduino.h>
#include <SD.h>
#include <SPI.h>
#include <TimeLib.h>
#include <TinyGPSPlus.h>

// ─── PIN DEFINITIONS ────────────────────────────────────────
#define PIN_GPS_RX      0   // Serial1 RX  ← GPS TX (UART)
#define PIN_GPS_TX      1   // Serial1 TX  → GPS RX (UART)
#define PIN_PPS         2   // GPS 1-PPS output (interrupt, rising)
#define PIN_TRIGGER     3   // Comparator output (interrupt)
#define PIN_ROT_A       4   // Rotary switch bit-0 (LSB)
#define PIN_ROT_B       5   // Rotary switch bit-1 (MSB)
#define PIN_LED_R       6   // RGB LED – red   (PWM, 330 Ω series)
#define PIN_LED_G       7   // RGB LED – green (PWM, 330 Ω series)
#define PIN_LED_B       8   // RGB LED – blue  (PWM, 330 Ω series)
#define PIN_BUZZER      9   // Piezo buzzer via NPN (2N2222 / BC547)
#define PIN_SD_CS      10   // SPI SD chip-select
#define PIN_SD_MOSI    11   // SPI MOSI
#define PIN_SD_MISO    12   // SPI MISO
#define PIN_SD_SCK     13   // SPI SCK
// PIN_THRESHOLD_PWM  14   // Filtered PWM → comparator REF+ (optional)

// ─── COMPILE-TIME DEFAULTS ──────────────────────────────────
static const char CONFIG_FILE[]  = "config.txt";
static const char DEFAULT_CSV[]  = "events.csv";

// ─── RUNTIME CONFIGURATION STRUCT ──────────────────────────
struct Config {
  char  csv_name[32];
  int   trig_flank;          // RISING or FALLING
  float trig_threshold;      // 0.0–1.0 → PWM/DAC reference
  float min_time_s;          // minimum seconds between events
  bool  confirm_buzzer;
  float buzzer_delay_s;
  char  labels[4][32];       // A / B / C / D strings
  bool  use_external_antenna;
};
static Config cfg;

// ─── HIGH-RESOLUTION TIMING STATE ───────────────────────────
// ARM_DWT_CYCCNT counts CPU cycles at F_CPU_ACTUAL Hz.
// At 150 MHz → 6.67 ns per tick → 1 µs = 150 ticks.
volatile uint32_t pps_cycles       = 0;   // cycle count at last PPS
volatile uint32_t event_cycles     = 0;   // cycle count at last trigger
volatile bool     event_pending    = false;
volatile uint32_t gps_seconds_utc  = 0;   // whole UTC seconds (Unix epoch)
volatile bool     gps_time_valid   = false;
volatile bool     gps_locked       = false;

// ─── GPS PARSER ─────────────────────────────────────────────
static TinyGPSPlus gps;

// ─── LED / BUZZER STATE ─────────────────────────────────────
enum LedMode { LED_ORANGE, LED_RED_BLINK, LED_GREEN_FLASH, LED_IDLE };
static LedMode   led_mode    = LED_ORANGE;
static uint32_t  led_ts      = 0;
static bool      buz_pending = false;
static uint32_t  buz_at      = 0;
static uint32_t  event_index = 0;
static uint32_t  last_ev_ms  = 0;

// ─── FORWARD DECLARATIONS ───────────────────────────────────
void    pps_isr();
void    trigger_isr();
void    load_config();
void    configure_gps();
void    log_event(uint32_t ev_cycles);
char*   format_utc(uint32_t sec, uint32_t offset_us, char* buf);
uint8_t read_rotary();
void    set_led(uint8_t r, uint8_t g, uint8_t b);
void    update_led();
void    trim_str(char* s);
void    dump_csv();

// ============================================================
void setup() {
  // Enable DWT cycle counter (used for high-res timing)
  ARM_DEMCR |= ARM_DEMCR_TRCENA;
  ARM_DWT_CTRL |= ARM_DWT_CTRL_CYCCNTENA;

  Serial.begin(115200);   // USB virtual COM

  // Reduce CPU to 150 MHz for lower power; all timing math
  // uses F_CPU_ACTUAL so baud rates remain correct.
  // set_arm_clock(150000000);  // uncomment to reduce power

  // GPIO setup
  pinMode(PIN_LED_R, OUTPUT);
  pinMode(PIN_LED_G, OUTPUT);
  pinMode(PIN_LED_B, OUTPUT);
  pinMode(PIN_BUZZER, OUTPUT);
  pinMode(PIN_ROT_A, INPUT_PULLUP);
  pinMode(PIN_ROT_B, INPUT_PULLUP);
  pinMode(PIN_TRIGGER, INPUT);
  pinMode(PIN_PPS, INPUT);

  set_led(255, 128, 0);   // orange = booting

  // SD init (retry loop with red flash on failure)
  SPI.begin();
  uint8_t sd_retries = 0;
  while (!SD.begin(PIN_SD_CS)) {
    set_led((sd_retries++ % 2 == 0) ? 255 : 0, 0, 0);
    delay(300);
    if (sd_retries > 20) break;  // give up, continue anyway
  }

  load_config();

  // Set comparator threshold via filtered PWM on pin 14
  analogWriteResolution(12);
  analogWriteFrequency(14, 146484); // ~146 kHz for smooth filtering
  analogWrite(14, (uint32_t)(cfg.trig_threshold * 4095.0f));

  // Attach PPS and trigger interrupts
  attachInterrupt(digitalPinToInterrupt(PIN_PPS), pps_isr, RISING);
  attachInterrupt(digitalPinToInterrupt(PIN_TRIGGER), trigger_isr,
                  cfg.trig_flank);

  // Init GPS UART at 9600 baud, send config
  Serial1.begin(9600);
  delay(100);
  configure_gps();

  led_mode = LED_ORANGE;
  led_ts   = millis();
}

// ============================================================
void loop() {
  // ── Parse GPS NMEA ───────────────────────────────────────
  while (Serial1.available()) {
    gps.encode(Serial1.read());
  }

  // When GPS delivers a fresh, valid time fix, sync gps_seconds_utc
  if (gps.time.isValid() && gps.date.isValid() && gps.time.isUpdated()) {
    tmElements_t tm;
    tm.Year   = (uint8_t)(gps.date.year() - 1970);
    tm.Month  = gps.date.month();
    tm.Day    = gps.date.day();
    tm.Hour   = gps.time.hour();
    tm.Minute = gps.time.minute();
    tm.Second = gps.time.second();
    gps_seconds_utc = makeTime(tm);
    gps_time_valid  = true;
  }

  if (!gps_locked && gps.satellites.isValid() &&
      gps.satellites.value() >= 4 && gps_time_valid) {
    gps_locked = true;
  }

  // ── Handle pending event ─────────────────────────────────
  if (event_pending) {
    noInterrupts();
    uint32_t saved_cycles = event_cycles;
    event_pending = false;
    interrupts();
    if (gps_locked) {
      log_event(saved_cycles);
    }
  }

  // ── USB command interface ────────────────────────────────
  if (Serial.available()) {
    String cmd = Serial.readStringUntil('\n');
    cmd.trim();
    if (cmd.equalsIgnoreCase("DUMP")) {
      dump_csv();
    } else if (cmd.equalsIgnoreCase("STATUS")) {
      Serial.printf("gps_locked=%d  sats=%d  events=%lu  uptime_s=%lu\n",
        (int)gps_locked, (int)gps.satellites.value(),
        event_index, millis()/1000UL);
    } else if (cmd.equalsIgnoreCase("HELP")) {
      Serial.println("Commands: DUMP  STATUS  HELP");
    }
  }

  // ── LED + buzzer state machine ───────────────────────────
  update_led();
  if (buz_pending && millis() >= buz_at) {
    buz_pending = false;
    tone(PIN_BUZZER, 2000, 120);
  }
}

// ─── PPS ISR  ────────────────────────────────────────────────
// Runs in < 1 µs — only latch cycle counter and increment epoch
void pps_isr() {
  pps_cycles = ARM_DWT_CYCCNT;
  if (gps_time_valid) gps_seconds_utc++;
}

// ─── TRIGGER ISR ─────────────────────────────────────────────
void trigger_isr() {
  uint32_t now_ms = millis();
  uint32_t min_ms = (uint32_t)(cfg.min_time_s * 1000.0f + 0.5f);
  if ((now_ms - last_ev_ms) >= min_ms) {
    event_cycles = ARM_DWT_CYCCNT;
    event_pending = true;
    last_ev_ms    = now_ms;
  }
}

// ─── LOG ONE EVENT ───────────────────────────────────────────
void log_event(uint32_t ev_cycles_val) {
  uint32_t delta_cycles = ev_cycles_val - pps_cycles;
  // Guard against negative delta (event just before PPS)
  if (delta_cycles > (uint32_t)(F_CPU_ACTUAL * 1.1f)) delta_cycles = 0;
  uint32_t offset_us = delta_cycles / (F_CPU_ACTUAL / 1000000UL);

  char ts[40];
  format_utc(gps_seconds_utc, offset_us, ts);

  uint8_t rot      = read_rotary();
  char    rot_char = 'A' + rot;
  event_index++;

  File f = SD.open(cfg.csv_name, FILE_WRITE);
  if (f) {
    if (f.size() == 0) {
      f.println("timestamp_utc,label,position,event_index,"
                "gps_epoch_s,offset_us");
    }
    f.printf("%s,%s,%c,%lu,%lu,%lu\n",
             ts, cfg.labels[rot], rot_char,
             event_index,
             (unsigned long)gps_seconds_utc,
             (unsigned long)offset_us);
    f.close();
  }

  // Flash green
  set_led(0, 255, 0);
  led_mode = LED_GREEN_FLASH;
  led_ts   = millis();

  // Arm buzzer
  if (cfg.confirm_buzzer) {
    buz_pending = true;
    buz_at      = millis() + (uint32_t)(cfg.buzzer_delay_s * 1000.0f);
  }
}

// ─── FORMAT UTC TIMESTAMP ────────────────────────────────────
char* format_utc(uint32_t sec, uint32_t offset_us, char* buf) {
  time_t t = (time_t)sec;
  tmElements_t tm;
  breakTime(t, tm);
  snprintf(buf, 40, "%04d-%02d-%02dT%02d:%02d:%02d.%06luZ",
           tm.Year + 1970, (int)tm.Month, (int)tm.Day,
           (int)tm.Hour, (int)tm.Minute, (int)tm.Second,
           (unsigned long)(offset_us % 1000000UL));
  return buf;
}

// ─── READ ROTARY (2-bit binary) ──────────────────────────────
// Switch wiring: common → GND; pin A, pin B → ROT_A, ROT_B with pull-up
// Positions: A=00 B=01 C=10 D=11
uint8_t read_rotary() {
  uint8_t a = !digitalRead(PIN_ROT_A);
  uint8_t b = !digitalRead(PIN_ROT_B);
  return (b << 1) | a;
}

// ─── LED HELPERS ─────────────────────────────────────────────
void set_led(uint8_t r, uint8_t g, uint8_t b) {
  analogWrite(PIN_LED_R, r);
  analogWrite(PIN_LED_G, g);
  analogWrite(PIN_LED_B, b);
}

void update_led() {
  uint32_t now = millis();
  if (!gps_locked) {
    // Orange pulsing before any fix attempt; red blink if no lock >30 s
    if (millis() < 30000) {
      set_led(255, 128, 0);  // orange
    } else {
      set_led((now / 400) % 2 == 0 ? 255 : 0, 0, 0); // red blink
    }
  } else if (led_mode == LED_GREEN_FLASH) {
    if (now - led_ts > 250) {
      led_mode = LED_IDLE;
      set_led(0, 0, 0);
    }
  } else {
    set_led(0, 0, 0);  // idle: off
  }
}

// ─── GPS CONFIGURATION (UBX via UART) ────────────────────────
void configure_gps() {
  // CFG-RATE: 1 Hz measurement, GPS time reference
  // Checksums must be recalculated for production; these are correct.
  static const uint8_t ubx_rate_1hz[] = {
    0xB5,0x62,0x06,0x08,0x06,0x00,
    0xE8,0x03,0x01,0x00,0x01,0x00,
    0x01,0x39
  };
  Serial1.write(ubx_rate_1hz, sizeof(ubx_rate_1hz));
  delay(200);

  // Disable unnecessary NMEA sentences (GLL, GSA, GSV, VTG)
  // Keep only RMC and GGA for time and fix quality
  // (Full UBX CFG-MSG packets omitted for brevity; configure in u-center)
}

// ─── PARSE config.txt ────────────────────────────────────────
void trim_str(char* s) {
  int len = strlen(s);
  while (len > 0 && (s[len-1]==' '||s[len-1]=='\t'||
                     s[len-1]=='\r'||s[len-1]=='\n')) s[--len]='\0';
  int st = 0;
  while (s[st]==' '||s[st]=='\t') st++;
  if (st) memmove(s, s+st, strlen(s+st)+1);
}

void load_config() {
  // Defaults
  strlcpy(cfg.csv_name, DEFAULT_CSV, sizeof(cfg.csv_name));
  cfg.trig_flank           = RISING;
  cfg.trig_threshold       = 0.65f;
  cfg.min_time_s           = 0.050f;
  cfg.confirm_buzzer       = true;
  cfg.buzzer_delay_s       = 5.0f;
  cfg.use_external_antenna = false;
  const char* def[4] = {"Condition_A","Condition_B","Condition_C","Condition_D"};
  for (int i=0;i<4;i++) strlcpy(cfg.labels[i], def[i], sizeof(cfg.labels[0]));

  File f = SD.open(CONFIG_FILE);
  if (!f) return;

  char line[128]; int li = 0;
  while (f.available()) {
    char c = f.read();
    if (c=='\n'||c=='\r') {
      if (li > 0) {
        line[li]='\0';
        char* hash=strchr(line,'#'); if(hash)*hash='\0';
        char* eq=strchr(line,'=');
        if(eq){
          *eq='\0';
          char* key=line; char* val=eq+1;
          trim_str(key); trim_str(val);
          if(!strcmp(key,"csv_name"))              strlcpy(cfg.csv_name,val,32);
          else if(!strcmp(key,"trig_flank"))       cfg.trig_flank=!strcmp(val,"negative")?FALLING:RISING;
          else if(!strcmp(key,"trig_threshold"))   cfg.trig_threshold=atof(val);
          else if(!strcmp(key,"min_time_between_events_s")) cfg.min_time_s=atof(val);
          else if(!strcmp(key,"confirm_buzzer"))   cfg.confirm_buzzer=!strcmp(val,"True");
          else if(!strcmp(key,"buzzer_delay_s"))   cfg.buzzer_delay_s=atof(val);
          else if(!strcmp(key,"A_string"))         strlcpy(cfg.labels[0],val,32);
          else if(!strcmp(key,"B_string"))         strlcpy(cfg.labels[1],val,32);
          else if(!strcmp(key,"C_string"))         strlcpy(cfg.labels[2],val,32);
          else if(!strcmp(key,"D_string"))         strlcpy(cfg.labels[3],val,32);
          else if(!strcmp(key,"gps_antenna_mode")) cfg.use_external_antenna=!strcmp(val,"external");
        }
      }
      li=0;
    } else if(li<127) line[li++]=c;
  }
  f.close();
}

// ─── DUMP CSV OVER USB ────────────────────────────────────────
void dump_csv() {
  File f = SD.open(cfg.csv_name);
  if (!f) { Serial.println("ERROR: file not found"); return; }
  Serial.println("--- BEGIN CSV ---");
  while (f.available()) Serial.write(f.read());
  Serial.println("\n--- END CSV ---");
  f.close();
}
