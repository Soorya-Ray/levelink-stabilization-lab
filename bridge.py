"""USB JSON telemetry → local SQLite and optional TLS MQTT. Never commands hardware."""
import argparse
import json
import os
import sqlite3
import time

import serial
from serial.tools import list_ports
from telemetry import validate


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--list-ports', action='store_true')
    parser.add_argument('--port')
    parser.add_argument('--db', default='telemetry.db')
    parser.add_argument('--mqtt', action='store_true', help='Use MQTT_* environment variables')
    args = parser.parse_args()
    if args.list_ports:
        for port in list_ports.comports():
            print(f'{port.device}: {port.description}')
        return
    if not args.port:
        parser.error('Supply --port or use --list-ports')
    mqtt_client = None
    if args.mqtt:
        import paho.mqtt.client as mqtt
        required = ['MQTT_HOST','MQTT_USERNAME','MQTT_PASSWORD','MQTT_TOPIC']
        if any(not os.environ.get(key) for key in required):
            parser.error('Set MQTT_HOST, MQTT_USERNAME, MQTT_PASSWORD, and MQTT_TOPIC first.')
        mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        mqtt_client.username_pw_set(os.environ['MQTT_USERNAME'], os.environ['MQTT_PASSWORD'])
        mqtt_client.tls_set()
        mqtt_client.max_queued_messages_set(20)
        mqtt_client.connect_async(os.environ['MQTT_HOST'], int(os.environ.get('MQTT_PORT','8883')), 30)
        mqtt_client.loop_start()
    db = sqlite3.connect(args.db)
    db.execute('PRAGMA journal_mode=WAL')
    db.execute('''CREATE TABLE IF NOT EXISTS telemetry
        (id INTEGER PRIMARY KEY, t_ms REAL, roll REAL, pitch REAL, top REAL,
        bottom REAL, pid_r REAL, pid_p REAL, sensor_ok INTEGER, received_at REAL)''')
    count = 0
    try:
        print('Listening at 115200 baud. Close Arduino Serial Monitor. Ctrl+C to stop.')
        with serial.Serial(args.port, 115200, timeout=1) as device:
            while True:
                raw = device.readline(4096)
                if not raw.startswith(b'{'):
                    continue
                try:
                    row = validate(json.loads(raw))
                except (ValueError, UnicodeError, TypeError):
                    continue
                db.execute('INSERT INTO telemetry (t_ms,roll,pitch,top,bottom,pid_r,pid_p,sensor_ok,received_at) VALUES (?,?,?,?,?,?,?,?,?)',
                    tuple(row[key] for key in ['t_ms','roll','pitch','top','bottom','pid_r','pid_p','sensor_ok','received_at']))
                count += 1
                if count % 100 == 0:
                    db.execute('DELETE FROM telemetry WHERE id < (SELECT MAX(id)-18000 FROM telemetry)')
                db.commit()
                if mqtt_client:
                    mqtt_client.publish(os.environ['MQTT_TOPIC'], json.dumps(row), qos=0, retain=False)
                if count % 100 == 0:
                    print(f'{count} valid packets received; MQTT connected: {mqtt_client.is_connected() if mqtt_client else "disabled"}')
    except KeyboardInterrupt:
        print('\nBridge stopped.')
    finally:
        db.close()
        if mqtt_client:
            mqtt_client.disconnect()
            mqtt_client.loop_stop()


if __name__ == '__main__':
    main()
