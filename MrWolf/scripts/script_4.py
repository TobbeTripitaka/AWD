
# Write the Python CSV downloader utility
py_downloader = '''#!/usr/bin/env python3
"""
gps_logger_download.py
======================
Download event log from GPS Timestamp Logger over USB serial.

Usage:
  python gps_logger_download.py              # auto-detect port, save events.csv
  python gps_logger_download.py COM3         # Windows explicit port
  python gps_logger_download.py /dev/ttyACM0 my_log.csv

Requirements:
  pip install pyserial
"""

import sys
import serial
import serial.tools.list_ports
import time
from pathlib import Path
from datetime import datetime

BAUD = 115200
TIMEOUT = 10   # seconds to wait for END marker


def find_teensy_port():
    """Auto-detect Teensy virtual COM port."""
    for p in serial.tools.list_ports.comports():
        desc = (p.description or "").lower()
        if "teensy" in desc or "usb serial" in desc:
            return p.device
    # Fallback: return first available port
    ports = list(serial.tools.list_ports.comports())
    if ports:
        return ports[0].device
    return None


def main():
    port     = sys.argv[1] if len(sys.argv) > 1 else find_teensy_port()
    out_file = sys.argv[2] if len(sys.argv) > 2 else "events.csv"

    if not port:
        print("ERROR: No serial port found. Plug in the logger and try again.")
        sys.exit(1)

    print(f"Connecting to {port} at {BAUD} baud ...")
    with serial.Serial(port, BAUD, timeout=2) as ser:
        time.sleep(1.0)          # let USB enumerate
        ser.reset_input_buffer()
        ser.write(b"DUMP\\n")     # request CSV dump
        print("Sent DUMP command, waiting ...")

        lines = []
        in_csv = False
        deadline = time.time() + TIMEOUT
        while time.time() < deadline:
            raw = ser.readline()
            if not raw:
                continue
            line = raw.decode("utf-8", errors="replace").rstrip()
            if "BEGIN CSV" in line:
                in_csv = True
                continue
            if "END CSV" in line:
                break
            if in_csv:
                lines.append(line)

    if not lines:
        print("No data received. Check connection and GPS lock.")
        sys.exit(1)

    out_path = Path(out_file)
    out_path.write_text("\\n".join(lines) + "\\n", encoding="utf-8")
    print(f"Saved {len(lines)} lines to {out_path.resolve()}")

    # Quick parse to count events
    data_lines = [l for l in lines if l and not l.startswith("timestamp")]
    print(f"Events in file: {len(data_lines)}")


if __name__ == "__main__":
    main()
'''

with open('/tmp/gps_logger/gps_logger_download.py', 'w') as fh:
    fh.write(py_downloader)
print("Download utility written")
