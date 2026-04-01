
# Now write the comprehensive build document as markdown
doc = r'''# GPS Event Timestamp Logger
## Detailed Construction Manual  –  v1.0
*Teensy 4.0 · u-blox NEO-M8N · NiMH AA battery · sub-millisecond UTC timestamps*

---

## 1. Overview and Design Principles

This device timestamps extremely short contact-closure events (e.g. a hammer
striking a metal target) with sub-millisecond accuracy using GPS-disciplined
timing. A GPS PPS (pulse-per-second) output aligned to UTC provides an
absolute 1 Hz reference with ≤1 µs error. A free-running hardware cycle
counter on the microcontroller interpolates between PPS pulses with
~7 ns resolution at 150 MHz CPU clock.

**Key design decisions:**
- CPU runs at 150 MHz (down-clocked from 600 MHz) for power reduction without
  sacrificing timing; all UART baud rates, timer frequencies, and the
  `millis()` function remain accurate via Teensy's dynamic clock scaling.
- GPS NMEA is parsed at 1 Hz to extract whole-second UTC. PPS edge latches
  the cycle counter and increments the epoch; the trigger ISR latches the
  same counter, giving sub-microsecond offset from the last PPS.
- A dedicated Schmitt-comparator front-end (MCP6541) with configurable
  threshold and hysteresis conditions the trigger input independently of
  the MCU, preventing false triggers from induced noise or slow edges.
- All user parameters are stored in `config.txt` on the SD card and parsed
  at startup; changing settings requires only editing a text file on a PC.

---

## 2. Power Budget and Battery Life Estimate

| Component | Idle current | Notes |
|---|---|---|
| Teensy 4.0 @ 150 MHz | ~30–35 mA | Dynamic clock scaling applied |
| u-blox NEO-M8N (tracking) | ~23 mA | Continuous tracking mode, 1 Hz |
| SPI microSD (idle) | ~0.5–4 mA | SanDisk; send CMD0 Idle after write |
| MCP6541 comparator | 0.001 mA | 600 nA quiescent — negligible |
| RGB LED (off = 0, green flash) | ~20 mA peak | On only 250 ms per event |
| Piezo buzzer | ~20 mA peak | On for ~120 ms per event |
| Rotary switch sense (pull-ups) | ~0.3 mA | Three 10 kΩ to 3.3 V |
| Misc regulators / logic | ~2 mA | LDO quiescent |
| **Total (steady state)** | **~60–65 mA** | LED and buzzer excluded |

**Battery: 4× AA NiMH at 2500 mAh (4.8 V nominal)**

Usable capacity (80% depth of discharge) ≈ 2000 mAh.

Runtime ≈ 2000 mAh ÷ 65 mA ≈ **30 hours continuous**

> This is a conservative estimate. In practice, GPS power drops to ~11 mA in
> Power Save Mode (PSM) once a fix is obtained. Enabling PSM in firmware can
> extend runtime to ~50–60 hours. However, PSM slightly increases PPS jitter
> (still <10 µs), which remains acceptable for millisecond-class timing.

**Charging:** 4× NiMH AA cells at 0.1C (250 mA) takes ~12–15 hours from USB
5 V. A dedicated NiMH charger IC (e.g. MCP73831 or TP4056-style module
adapted for NiMH) provides safe -ΔV or timer cutoff. Ensure the USB power
supply or computer port can sustain 500 mA (USB 2.0 minimum).

---

## 3. Bill of Materials

### 3.1 Core Electronics

| # | Item | Qty | Approx AUD | Supplier | Notes |
|---|---|---|---|---|---|
| 1 | Teensy 4.0 development board | 1 | $46 | Core Electronics (DEV-15583) | Main MCU |
| 2 | u-blox NEO-M8N GPS module (SMA, with PPS pin) | 1 | $28–$50 | Buzz Hobbies / Mouser / gnss.store | Must expose PPS; SMA antenna port |
| 3 | Active GPS patch antenna, SMA male, 3–5 V, 28 dB, ~5 m cable | 1 | $22 | Core Electronics | For outdoor use / bench testing |
| 4 | SPI microSD card breakout (level-shifted, 3.3 V reg) | 1 | $5–$8 | Auscomtech / Zaitronics / Core Electronics | |
| 5 | microSD card, 8–16 GB, SanDisk (good SPI compat) | 1 | $10 | RS Components / Jaycar | FAT32 format |
| 6 | MCP6541-I/P comparator DIP-8 | 1 | $2 | RS Components (049-6855) / element14 | Schmitt trigger for trigger input |
| 7 | 4× AA NiMH rechargeable cells, 2500 mAh | 1 pack | $12–$18 | Jaycar / Altronics | Low-self-discharge preferred |
| 8 | 4× AA battery holder (series, with leads) | 1 | $2 | Jaycar PH9204 / Altronics S5030 | |
| 9 | NiMH USB charger module (5 V in, 4S NiMH out) | 1 | $8–$15 | eBay / AliExpress (MH-CD42 or similar) | Or dedicated NiMH charger IC circuit |
| 10 | 3.3 V LDO regulator module (500 mA+) or AMS1117-3.3 | 1 | $2–$5 | Altronics / Jaycar | Powers logic rail |

### 3.2 Connectors and Panel Hardware

| # | Item | Qty | Approx AUD | Supplier | Notes |
|---|---|---|---|---|---|
| 11 | RS PRO 4-position cam switch, IP65, panel mount, knob actuator, 16 A | 1 | $62 | RS Components (265-7671) | Heavy duty; glove-operable |
| 12 | Panel-mount waterproof USB-C, IP68, with screw/silicone cap | 1 | $12–$18 | Tempero Systems / RS Components (231-7951) | Data + power |
| 13 | BNC female flange bulkhead panel mount (4-hole) | 1 | $9 | Telco Antennas (BNCF-FLANGE) | GPS antenna port |
| 14 | BNC dust/weather cap (screw type) | 1 | $3 | Altronics / Jaycar | Protect BNC when no antenna |
| 15 | SMA male to BNC female pigtail, RG316, 20 cm | 1 | $10–$15 | wegmatt.com / local RF shops | Connects GPS module to panel BNC |
| 16 | Cable gland, IP68, for trigger cable (choose size for cable OD) | 2 | $3–$5 ea | RS Components / Altronics | 1× trigger, 1× power/spare |
| 17 | 2-way pluggable screw terminal block, 5 mm pitch | 2 | $2 | Altronics / Jaycar | Trigger and power input |
| 18 | Nexperia PESD3V3S2UT ESD protection diode, SOT-23 | 2 | $0.50 ea | RS Components (050-9099) | Trigger line ESD protection |

### 3.3 Passives and Small Components

| # | Item | Qty | Approx AUD | Supplier | Notes |
|---|---|---|---|---|---|
| 19 | 10 kΩ resistor, 1/4 W (for pull-ups, bias divider) | 10 | $1 | Jaycar / Altronics | |
| 20 | 1 kΩ resistor, 1/4 W (series protection) | 5 | $0.50 | Jaycar / Altronics | |
| 21 | 330 Ω resistor, 1/4 W (LED current limit) | 3 | $0.50 | Jaycar / Altronics | |
| 22 | 100 nF ceramic capacitor (decoupling) | 10 | $1 | Jaycar / Altronics | |
| 23 | 10 µF electrolytic capacitor, 10 V+ | 4 | $1 | Jaycar / Altronics | |
| 24 | RGB LED, common cathode, 5 mm | 1 | $1 | Jaycar / Altronics | |
| 25 | Piezo buzzer, 3–5 V, self-driven, ~12 mm | 1 | $2 | Jaycar / Altronics | |
| 26 | BC547 or 2N2222 NPN transistor | 2 | $0.50 | Jaycar / Altronics | Buzzer drive |
| 27 | 1N4148 signal diode | 2 | $0.50 | Jaycar / Altronics | Flyback protection |
| 28 | 47 nF capacitor (RC trigger filter) | 2 | $0.50 | Jaycar / Altronics | |

### 3.4 Mechanical and Easy-to-Forget Items

| # | Item | Qty | Notes |
|---|---|---|---|
| 29 | Perfboard / prototype PCB (70×90 mm or larger) | 1–2 | Jaycar / Altronics; one for main board, one spare |
| 30 | M3×10 mm machine screws + nuts | 20 | Mounting standoffs to enclosure floor |
| 31 | M3 brass standoffs, 10–15 mm (M-F) | 8 | Raise PCB above enclosure floor |
| 32 | M3 flat washers | 20 | Under screw heads |
| 33 | Nylon spacers, 5 mm | 4 | Under battery holder |
| 34 | Hook-up wire, solid core 22 AWG (red, black, blue, green, yellow) | 1 reel ea | Jaycar / Altronics |
| 35 | Heat-shrink tubing, assorted (2–6 mm) | 1 pack | |
| 36 | Female Dupont / jumper wire assortment (150 mm, 20-pin) | 2 | Prototyping connections |
| 37 | JST-XH 4-pin connector set (housing + pins, M+F) | 5 | Battery harness |
| 38 | Zip ties, 100 mm | 1 pack | Cable management inside enclosure |
| 39 | Double-sided foam tape | 1 strip | Secure battery holder |
| 40 | Label maker tape or printed adhesive labels | 1 | Rotary switch positions, USB lid, BNC lid |
| 41 | Isopropyl alcohol + cotton swabs | — | Flux cleaning after soldering |
| 42 | Rosin-core solder, 0.6–0.8 mm | 1 reel | |
| 43 | Multimeter | 1 | Continuity checks |
| 44 | USB-C cable (data-capable, not charge-only) | 1 | For programming and CSV download |

### 3.5 Estimated Per-Unit Budget Summary

| Category | AUD (approx) |
|---|---|
| Core electronics (Teensy, GPS, SD, comparator, battery + charger) | $115–$150 |
| Connectors and panel hardware | $110–$130 |
| Passives, LEDs, buzzer, transistors | $10–$15 |
| Mechanical (standoffs, wire, heat-shrink, PCB) | $25–$40 |
| **Total per unit** | **$260–$335** |

> Prices drop with quantity. Buying parts for 10 units simultaneously reduces
> cost to approximately $200–$260/unit.

---

## 4. Schematic and Circuit Description

### 4.1 Power Architecture

```
USB-C (5 V) ──┬── NiMH Charger Module ──── 4× AA NiMH pack
               │                                    │
               └────────────────────────────────────┴──> 4.8–5 V system rail
                                                         │
                                               AMS1117-3.3
                                                         │
                                               3.3 V logic rail
                                               ├── Teensy 3.3 V pin
                                               ├── GPS VCC
                                               └── SD card VCC
```

The 4-position rotary cam switch is wired on the **positive battery rail**
(before the regulator), acting as the master power switch:
- Position OFF: circuit open, battery isolated
- Positions A/B/C: circuit closed, system powered

The rotary provides two separate functions using separate poles:
1. **Power switching**: one set of contacts on the main 5 V supply line
2. **Logic coding**: a separate set provides a 2-bit code to Teensy pins
   ROT_A and ROT_B (positions A/B/C/D = 00/01/10/11)

If using a 2-pole cam switch, wire pole 1 as power break and pole 2 as
binary code output (common to 3.3 V; outputs pulled low in off positions).

### 4.2 Trigger Input Conditioning

This is the most critical circuit. The design must:
1. Detect a very brief contact closure reliably
2. Reject ESD, induced noise, and slow non-event edges
3. Produce a clean digital edge for the MCU interrupt

```
Trigger terminal (+) ──── R1 (1 kΩ) ──── D1 (ESD) ──── R2 (10 kΩ) ──┐
                                                                        ├── MCP6541 IN+
Trigger terminal (–) ──── GND ─────────── D2 (ESD) ────────────────────┘

3.3 V ──── R3 (10 kΩ) ──── R4 (10 kΩ) ──── GND
                │
                └──────────────────────────── MCP6541 IN– (reference)

MCP6541 OUT ──── R5 (10 kΩ) ──── Teensy pin 3
             │
             Rfb (220 kΩ, IN+ to OUT, provides hysteresis)

MCP6541 VDD = 3.3 V, VSS = GND
```

**How it works:**
- The two metal pieces act as a normally-open switch.
- When open: no current through R1/R2; IN+ is pulled to ~3.3 V via R2
  (which is in the bias network).
- Actually re-configure for contact-closure → goes LOW:
  - Bias: R2 (10 kΩ) from 3.3 V to IN+. In– set to ~1.65 V (R3/R4 divider)
  - Open contact: IN+ pulled to 3.3 V → IN+ > IN– → OUT HIGH
  - Closed contact: metal pieces connect IN+ to GND via R1 → IN+ ≈ 0 V → OUT LOW
- Schmitt feedback via Rfb (220 kΩ from OUT to IN+) shifts threshold up
  when output is HIGH and down when LOW → hysteresis ≈ ±100 mV
- This prevents the output from chattering due to contact bounce or
  slowly varying signals from induced noise.
- Trig_flank = "negative" in config → configure Teensy for FALLING edge.

**ESD protection:**
- D1 and D2 are PESD3V3S2UT (Nexperia, SOT-23): bi-directional ESD
  protection diodes to 3.3 V and GND, clamping ±8 kV ESD to safe levels.
- R1 (1 kΩ) limits peak current during ESD discharge through the diodes.

**Threshold adjustment:**
- To fine-tune: change R3/R4 ratio (or use a trimpot) to move IN–.
- Alternatively, connect Teensy pin 14 (filtered PWM) to IN– via a
  10 kΩ resistor and 100 nF cap to GND (RC low-pass, fc ≈ 160 Hz).
  Firmware sets the PWM duty cycle from `trig_threshold` in config.

### 4.3 Rotary Switch Logic

A 2-pole cam switch, or a 4-position coded rotary:
- Common terminal (logic pole) → 3.3 V
- Position A output → PIN_ROT_A (Teensy), plus pull-down 10 kΩ to GND
- Position B output → PIN_ROT_B, plus pull-down 10 kΩ to GND

| Position | ROT_A | ROT_B | Decoded |
|---|---|---|---|
| A | LOW | LOW | 0b00 |
| B | HIGH | LOW | 0b01 |
| C | LOW | HIGH | 0b10 |
| D | HIGH | HIGH | 0b11 |

For a cam switch where the power pole is also integrated, the OFF position
leaves both ROT_A and ROT_B floating LOW (pull-downs hold them down).

### 4.4 GPS and PPS

```
GPS VCC (3.3 V) ──── GPS module VCC
GPS GND         ──── GND
GPS TX          ──── Teensy pin 0 (Serial1 RX)  via 1 kΩ series resistor
GPS RX          ──── Teensy pin 1 (Serial1 TX)
GPS PPS         ──── Teensy pin 2 (interrupt)    via 1 kΩ + 100 nF to GND
GPS SDA/SCL     ──── not connected (UART only)
GPS SMA port    ──── RG316 pigtail ──── BNC panel bulkhead ──── external antenna
```

The NEO-M8N automatically detects an external active antenna on the SMA port
via load-state sensing; no firmware command required in auto mode. Once
the external antenna is plugged in, the module switches to it within seconds.

### 4.5 microSD

```
Teensy pin 10 (CS)   ──── SD CS
Teensy pin 11 (MOSI) ──── SD MOSI
Teensy pin 12 (MISO) ──── SD MISO
Teensy pin 13 (SCK)  ──── SD SCK
SD VCC              ──── 3.3 V
SD GND              ──── GND
```

Place a 100 nF decoupling capacitor directly across SD VCC and GND.

### 4.6 RGB LED and Buzzer

```
Teensy pin 6 ──── 330 Ω ──── LED Red anode
Teensy pin 7 ──── 330 Ω ──── LED Green anode
Teensy pin 8 ──── 330 Ω ──── LED Blue anode
                              LED common cathode ──── GND

Teensy pin 9 ──── 1 kΩ ──── BC547 Base
                             BC547 Collector ──── Buzzer + ──── 5 V
                             BC547 Emitter  ──── GND
                             Buzzer –        ──── GND
                             1N4148 across buzzer (cathode to 5 V)
```

---

## 5. Pin Map Summary

| Teensy Pin | Function | Direction | Notes |
|---|---|---|---|
| 0 (RX1) | GPS UART RX | Input | From GPS TX; 1 kΩ series resistor |
| 1 (TX1) | GPS UART TX | Output | To GPS RX |
| 2 | GPS PPS | Interrupt | Rising edge; 1 kΩ + 100 nF to GND |
| 3 | Trigger (comparator out) | Interrupt | Rising or falling per config |
| 4 | Rotary bit-0 (ROT_A) | Input | Pull-down 10 kΩ to GND |
| 5 | Rotary bit-1 (ROT_B) | Input | Pull-down 10 kΩ to GND |
| 6 | LED Red (PWM) | Output | 330 Ω to LED anode |
| 7 | LED Green (PWM) | Output | 330 Ω to LED anode |
| 8 | LED Blue (PWM) | Output | 330 Ω to LED anode |
| 9 | Buzzer drive | Output | Via BC547 NPN transistor |
| 10 | SD CS (SPI) | Output | |
| 11 | SD MOSI (SPI) | Output | |
| 12 | SD MISO (SPI) | Input | |
| 13 | SD SCK (SPI) | Output | |
| 14 | Threshold PWM (optional) | Output | RC-filtered → MCP6541 IN– |
| VIN | 5 V power in | — | From battery / USB-C |
| 3.3 V | 3.3 V out | — | Powers GPS, SD, comparator |
| GND | Ground | — | |

---

## 6. LED Status Summary

| State | Colour | Pattern | Meaning |
|---|---|---|---|
| Booting / GPS acquiring | Orange | Steady | Waiting for first valid GPS time |
| No GPS lock after 30 s | Red | 0.4 s blink | Fix not obtained; check antenna |
| SD card error | Red | Fast 0.2 s blink | SD not found or write error |
| GPS locked, idle | Off | — | Normal operating state |
| Event accepted | Green | 250 ms flash | Timestamp saved to CSV |

---

## 7. SD Card File Structure

```
SD card root/
├── config.txt          ← edit to change settings
├── events.csv          ← event log (name set in config)
└── events_example.csv  ← reference only; can be deleted
```

### config.txt Reference

| Parameter | Type | Example | Description |
|---|---|---|---|
| `csv_name` | string | `events.csv` | Output filename on SD |
| `trig_flank` | `positive`/`negative` | `positive` | Trigger on rising or falling edge |
| `trig_threshold` | float 0–1 | `0.65` | Comparator reference level (0=GND, 1=3.3V) |
| `min_time_between_events_s` | float | `0.050` | Min interval in seconds (50 ms default) |
| `confirm_buzzer` | `True`/`False` | `True` | Enable audio confirmation |
| `buzzer_delay_s` | float | `5.0` | Seconds after event for buzzer |
| `A_string` | string (≤31 chr) | `Condition_A` | Label for rotary position A |
| `B_string` | string | `Condition_B` | |
| `C_string` | string | `Condition_C` | |
| `D_string` | string | `Condition_D` | |
| `gps_antenna_mode` | `internal`/`external`/`auto` | `auto` | GPS antenna selection |

### events.csv Columns

| Column | Example | Description |
|---|---|---|
| `timestamp_utc` | `2026-03-28T11:23:45.012345Z` | ISO 8601 UTC with microseconds |
| `label` | `Condition_A` | String from config matching rotary position |
| `position` | `A` | Rotary switch position letter |
| `event_index` | `1` | Sequential event counter |
| `gps_epoch_s` | `1711625025` | GPS whole seconds (Unix epoch) |
| `offset_us` | `12345` | Microseconds since last PPS |

---

## 8. Step-by-Step Assembly

### Step 1: Prepare and test core modules on breadboard

1. Connect Teensy 4.0 to USB. Open Arduino IDE with Teensyduino installed.
2. Flash a blink sketch to confirm Teensy works.
3. Connect GPS module: VCC→3.3 V, GND, TX→Teensy pin 0, RX→Teensy pin 1.
4. Open Serial Monitor at 9600 baud on Serial1 — confirm NMEA sentences appear.
5. Confirm PPS LED blinks at exactly 1 Hz once GPS has a fix (typically 30–90 s outdoors).
6. Connect SD card module: CS→10, MOSI→11, MISO→12, SCK→13, VCC→3.3 V.
7. Confirm SD mounts in Arduino sketch (SD.begin returns true).

### Step 2: Build trigger input conditioning circuit

1. On perfboard, assemble the comparator sub-circuit:
   - MCP6541 DIP-8, bypass cap (100 nF) across VDD/VSS pins.
   - R1 (1 kΩ) in series from trigger terminal +.
   - ESD diodes D1/D2 (PESD3V3S2UT) from junction of R1/R2 to 3.3 V and GND.
   - R2 (10 kΩ) from the same node to IN+.
   - R3/R4 (10 kΩ/10 kΩ) divider for IN– reference (~1.65 V).
   - Rfb (220 kΩ) from OUT pin back to IN+ for Schmitt hysteresis.
   - R5 (10 kΩ) from OUT to Teensy pin 3.
2. Apply 3.3 V and GND. Verify IN– is at ~1.65 V with a multimeter.
3. Short the two trigger terminals together (simulating contact close).
   OUT should go LOW. Open the terminals — OUT should go HIGH.
4. Connect to Teensy pin 3 and confirm interrupts fire in test sketch.

### Step 3: RGB LED and buzzer

1. Wire RGB LED common cathode to GND.
2. Three 330 Ω resistors from Teensy pins 6/7/8 to LED R/G/B anodes.
3. BC547 NPN: base via 1 kΩ to Teensy pin 9; collector to buzzer +;
   emitter to GND; 1N4148 across buzzer for flyback protection.
4. Test LED colours and buzzer with a simple sketch.

### Step 4: Rotary switch wiring

1. Use the cam switch's logic pole (not the power pole).
2. Wire switch common terminal to 3.3 V.
3. Position-A output → Teensy pin 4 + pull-down 10 kΩ to GND.
4. Position-B output → Teensy pin 5 + pull-down 10 kΩ to GND.
   (For a 2-position binary code: two contacts give 4 states.
   Alternatively, wire all 4 positions individually and use 2 inputs
   to encode them as shown in the table above.)
5. Verify that rotating the switch changes the digital reading in a test sketch.

### Step 5: Power circuit

1. Assemble 4× AA NiMH pack in holder; test voltage (~4.8–5.0 V charged).
2. Wire NiMH charger module: 5 V USB input, output to battery terminals.
3. AMS1117-3.3: input from battery +, output to 3.3 V bus with 10 µF
   input cap and 10 µF output cap.
4. Cam switch power pole wired in series on the positive battery rail
   (before the regulator). Position OFF opens this rail.

### Step 6: Panel connectors

1. Mount BNC panel bulkhead in enclosure. Thread cable gland for trigger.
2. Panel-mount USB-C: wire USB data lines through to Teensy USB.
3. Connect RG316 SMA→BNC pigtail between GPS SMA port and panel BNC.

### Step 7: Final assembly

1. Mount all sub-circuits on perfboard with M3 standoffs.
2. Follow the pin map table to connect all wiring.
3. Dress wires neatly; keep GPS coax clear of power lines.
4. Format SD card as FAT32. Copy `config.txt` and `events_example.csv`.
5. Load firmware (gps_logger.ino) via Arduino IDE + Teensyduino.

### Step 8: Functional verification

1. Power on with switch in position A. LED should turn orange.
2. Outdoors or near a window: wait for GPS lock (~30–90 s first cold start,
   ~1–5 s hot start). LED goes dark when locked.
3. Tap the two trigger terminals together. LED should flash green.
   After `buzzer_delay_s` seconds, buzzer should sound.
4. Connect USB to a PC. Open a serial terminal (115200 baud) and type
   `DUMP` + Enter. Verify CSV rows appear.
5. Run `gps_logger_download.py` to save CSV to a file on your PC.
6. Verify timestamps are in ISO 8601 UTC format with microsecond precision.

---

## 9. Loading Firmware: Arduino IDE Setup

1. Install [Arduino IDE 2.x](https://www.arduino.cc/en/software)
2. Install [Teensyduino](https://www.pjrc.com/teensy/teensyduino.html) plugin
3. Install libraries via Library Manager:
   - **TinyGPSPlus** by Mikal Hart
   - **Time** by Michael Margolis
4. Select board: `Teensy 4.0`
5. Select port: the COM port / `/dev/ttyACM*` that appears when plugged in
6. Open `gps_logger.ino` and click Upload

---

## 10. Downloading Data

### Option A: Serial terminal (any OS)
- Open any terminal (PuTTY, Arduino Serial Monitor, minicom)
- Connect at 115200 baud
- Type `DUMP` and press Enter
- Copy-paste the output between the `--- BEGIN CSV ---` and `--- END CSV ---` markers

### Option B: Python script
```bash
pip install pyserial
python gps_logger_download.py          # auto-detect port
python gps_logger_download.py COM3 my_log.csv
```

### Option C: Direct SD card
- Remove the microSD card and insert into a card reader on any PC
- Copy `events.csv` directly

---

## 11. Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| LED stays orange > 2 min | No GPS fix | Move outdoors or connect external antenna; check SMA pigtail |
| LED blinks red fast | SD card error | Reseat SD; reformat FAT32; use SanDisk branded card |
| Events logged but wrong time | GPS not locked at trigger time | Wait for lock before recording events |
| False triggers / extra events | Noise on trigger line | Increase `trig_threshold`; reduce `min_time_between_events_s`; check ESD diode soldering |
| No trigger at all | Wrong flank setting or threshold too high | Set `trig_flank=negative` if contact closure pulls LOW; decrease `trig_threshold` |
| Buzzer sounds at wrong time | `buzzer_delay_s` misconfigured | Edit config.txt |
| CSV has duplicate timestamps | `min_time_between_events_s` too small | Increase to debounce mechanical contact |

---
*End of document*
'''

with open('/tmp/gps_logger/BUILD_GUIDE.md', 'w') as fh:
    fh.write(doc)
print("Build guide written:", len(doc), "chars")
