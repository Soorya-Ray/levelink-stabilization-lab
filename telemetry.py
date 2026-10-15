"""Validated telemetry, deterministic demonstration data, and bounded MQTT receiver."""
import json
import math
import threading
import time
from collections import deque

import numpy as np
import pandas as pd

FIELDS = ['t_ms', 'roll', 'pitch', 'top', 'bottom', 'pid_r', 'pid_p', 'sensor_ok']


def validate(packet):
    if not isinstance(packet, dict):
        raise ValueError('Telemetry must be a JSON object.')
    result = {}
    for field in FIELDS:
        if field not in packet:
            raise ValueError(f'Missing field: {field}')
        value = packet[field]
        if field == 'sensor_ok':
            if not isinstance(value, (bool, int)) or value not in (0, 1):
                raise ValueError('sensor_ok must be true/false or 0/1')
            result[field] = bool(value)
        else:
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError(f'{field} must be finite numeric data')
            result[field] = float(value)
    if result['t_ms'] < 0 or any(abs(result[x]) > 180 for x in ['roll', 'pitch']):
        raise ValueError('Invalid timestamp or tilt angle')
    if any(not 0 <= result[x] <= 180 for x in ['top', 'bottom']):
        raise ValueError('Servo commands must be in 0–180 degrees')
    result['received_at'] = time.time()
    return result


def demo_data(end, seconds=90, scenario='Gentle tilting'):
    end_tick = int(end*10)
    t = np.arange(max(0, end_tick-int(seconds*10)), end_tick)/10
    if len(t) < 2:
        t = np.array([0., .1])
    scale = {'Gentle tilting': 12, 'Rough motion': 32, 'Command saturation': 95, 'Sensor dropout': 12}[scenario]
    roll = scale*np.sin(.72*t) + .8*np.sin(6*t)
    pitch = .7*scale*np.sin(.48*t+.6) + .4*np.sin(5*t)
    dr = .72*scale*np.cos(.72*t)+4.8*np.cos(6*t)
    dp = .336*scale*np.cos(.48*t+.6)+2*np.cos(5*t)
    pr, pp = -1.2*roll-.08*dr, -1.2*pitch-.08*dp
    ok = np.ones(len(t), dtype=bool)
    if scenario == 'Sensor dropout':
        ok = (t % 20) < 15
    return pd.DataFrame(dict(t_ms=t*1000, roll=roll, pitch=pitch,
        top=np.where(ok, np.clip(90+pr, 0, 180), 90),
        bottom=np.where(ok, np.clip(90-pp, 0, 180), 90),
        pid_r=pr, pid_p=pp, sensor_ok=ok, received_at=time.time()-end+t))


def normalize_csv(file):
    df = pd.read_csv(file)
    missing = set(FIELDS)-set(df.columns)
    if missing:
        raise ValueError('Missing CSV columns: '+', '.join(sorted(missing)))
    if len(df) > 100_000:
        raise ValueError('Upload at most 100,000 rows per experiment.')
    records = []
    for row in df[FIELDS].to_dict('records'):
        if isinstance(row['sensor_ok'], str):
            mapping = {'true': True, 'false': False, '1': True, '0': False}
            if row['sensor_ok'].lower() not in mapping:
                raise ValueError('sensor_ok must be true/false or 0/1')
            row['sensor_ok'] = mapping[row['sensor_ok'].lower()]
        records.append(validate(row))
    result = pd.DataFrame(records)
    for column in ['source','experiment','payload_g']:
        if column in df:
            result[column] = df[column].to_numpy()
    return result


class MQTTReceiver:
    def __init__(self, host, port, username, password, topic):
        import paho.mqtt.client as mqtt
        self.rows = deque(maxlen=18000)
        self.lock = threading.Lock()
        self.status = 'Connecting'
        self.errors = 0
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        self.client.username_pw_set(username, password)
        self.client.tls_set()
        def connected(client, userdata, flags, reason, properties):
            self.status = 'Connected' if reason == 0 else f'Connection refused: {reason}'
            if reason == 0:
                client.subscribe(topic, qos=0)
        def disconnected(client, userdata, flags, reason, properties):
            self.status = 'Disconnected; retrying'
        def message(client, userdata, msg):
            try:
                if len(msg.payload) > 4096:
                    raise ValueError('Packet too large')
                row = validate(json.loads(msg.payload))
                with self.lock:
                    self.rows.append(row)
            except (ValueError, TypeError, UnicodeError):
                self.errors += 1
        self.client.on_connect = connected
        self.client.on_disconnect = disconnected
        self.client.on_message = message
        self.client.reconnect_delay_set(1, 30)
        self.client.connect_async(host, port, 30)
        self.client.loop_start()

    def frame(self):
        with self.lock:
            return pd.DataFrame(list(self.rows))

    def close(self):
        self.client.disconnect()
        self.client.loop_stop()


class LANReceiver:
    def __init__(self, url):
        import requests
        self.rows = deque(maxlen=18000)
        self.lock = threading.Lock()
        self.status = 'Connecting'
        self.stop = threading.Event()
        def poll():
            session = requests.Session()
            while not self.stop.is_set():
                try:
                    response = session.get(url, timeout=.7)
                    response.raise_for_status()
                    row = validate(response.json())
                    with self.lock:
                        if not self.rows or self.rows[-1]['t_ms'] != row['t_ms']:
                            self.rows.append(row)
                    self.status = 'Connected'
                except (requests.RequestException, ValueError, TypeError):
                    self.status = 'No valid response; retrying'
                self.stop.wait(.1)
            session.close()
        threading.Thread(target=poll, daemon=True).start()

    def frame(self):
        with self.lock:
            return pd.DataFrame(list(self.rows))

    def close(self):
        self.stop.set()
