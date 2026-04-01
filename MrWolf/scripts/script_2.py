
# Write the example config.txt
config_txt = '''# ============================================================
# GPS Event Timestamp Logger - Configuration File
# Edit this file on the SD card with any text editor.
# Lines beginning with # are comments and are ignored.
# Save as config.txt in the root of the SD card.
# ============================================================

# ── Output file ─────────────────────────────────────────────
csv_name=events.csv          # filename on SD card root

# ── Trigger settings ────────────────────────────────────────
trig_flank=positive          # positive (rising) or negative (falling)

trig_threshold=0.65          # Comparator reference level, 0.0 – 1.0
                             # 0.65 means 65% of 3.3 V = ~2.15 V
                             # Increase to reject more noise; decrease
                             # if valid contacts are not being detected.

min_time_between_events_s=0.050   # Minimum time between accepted events
                                   # in seconds (decimals OK).
                                   # 0.050 = 50 ms  |  0.002 = 2 ms

# ── Buzzer ──────────────────────────────────────────────────
confirm_buzzer=True          # True or False
buzzer_delay_s=5.0           # Seconds after event before buzzer sounds
                             # Set to 0.0 for immediate beep

# ── Rotary switch labels ─────────────────────────────────────
# These strings are written to the CSV alongside each timestamp.
# Maximum 31 characters each.
A_string=Condition_A
B_string=Condition_B
C_string=Condition_C
D_string=Condition_D

# ── GPS antenna mode ─────────────────────────────────────────
# internal  = use built-in patch antenna on GPS module
# external  = force external antenna via BNC panel connector
# auto      = auto-detect (u-blox NEO-M8N default behaviour)
gps_antenna_mode=auto
'''

with open('/tmp/gps_logger/config.txt', 'w') as fh:
    fh.write(config_txt)
print("config.txt written")
