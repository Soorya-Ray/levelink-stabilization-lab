import io
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from telemetry import demo_data, normalize_csv, validate
from analysis import fit_slr, fault_events


def test_packet_and_csv_roundtrip():
    frame = demo_data(100,10)
    row = frame.iloc[0].to_dict()
    row['sensor_ok'] = bool(row['sensor_ok'])
    assert validate(row)['sensor_ok'] is True
    restored = normalize_csv(io.StringIO(frame.to_csv(index=False)))
    assert len(restored) == len(frame)
    assert restored.top.between(0,180).all()


@pytest.mark.parametrize('change', [{'roll':float('nan')},{'top':200},{'sensor_ok':'yes'},{'t_ms':-1},{'pitch':True}])
def test_bad_packets_rejected(change):
    row = dict(t_ms=1,roll=0,pitch=0,top=90,bottom=90,pid_r=0,pid_p=0,sensor_ok=True)
    row.update(change)
    with pytest.raises(ValueError):
        validate(row)


def test_slr_uses_only_earlier_samples_for_training():
    df = demo_data(100,60)
    result = fit_slr(df)
    assert result['train'].t_ms.max() < result['test'].t_ms.min()
    assert result['slope'] == pytest.approx(-1.2,abs=.08)
    assert result['mae'] < result['baseline_mae']


def test_slr_low_variation_and_insufficient_data():
    with pytest.raises(ValueError):
        fit_slr(demo_data(10,2))
    df=demo_data(100,60)
    df['roll']=0
    with pytest.raises(ValueError,match='variation'):
        fit_slr(df)


def test_slr_reset_does_not_mix_runs():
    df=pd.concat([demo_data(100,60),demo_data(2,2)],ignore_index=True)
    with pytest.raises(ValueError,match='healthy samples'):
        fit_slr(df)


def test_faults_are_transitions_not_one_per_sample():
    df=demo_data(100,10)
    df['roll']=0
    df['pitch']=0
    df['top']=90
    df['bottom']=90
    df.loc[3:8,'sensor_ok']=False
    df.loc[20:25,'top']=180
    result=fault_events(df)
    assert len(result)==2
    assert 'Sensor read failed' in result.event.to_list()


def test_app_pages():
    from streamlit.testing.v1 import AppTest
    app=AppTest.from_file(str(Path(__file__).with_name('app.py')),default_timeout=30).run()
    assert not app.exception
    assert len(app.metric)>=4
    for page in ['Signal explorer','Regression lab','Experiment desk','System & setup']:
        app.sidebar.radio[0].set_value(page).run()
        assert not app.exception, str(app.exception)
    app.sidebar.radio[0].set_value('Regression lab').run()
    app.button[0].click().run()
    assert not app.exception
    assert len(app.metric)>=3
    app.sidebar.selectbox[0].set_value('USB bridge').run()
    assert not app.exception


def test_demo_timestamps_stay_on_fixed_grid():
    a=demo_data(100.123,5)
    b=demo_data(100.245,5)
    assert set(a.t_ms) & set(b.t_ms)


def test_lan_receiver_collects_and_validates_http_packets():
    import threading
    import time
    from http.server import BaseHTTPRequestHandler, HTTPServer
    from telemetry import LANReceiver
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            row=dict(t_ms=time.monotonic()*1000,roll=2,pitch=3,top=88,bottom=94,pid_r=-2,pid_p=-4,sensor_ok=True)
            self.send_response(200)
            self.end_headers()
            self.wfile.write(json.dumps(row).encode())
        def log_message(self,*args):
            pass
    server=HTTPServer(('127.0.0.1',0),Handler)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    receiver=LANReceiver(f'http://127.0.0.1:{server.server_port}/telemetry')
    try:
        deadline=time.monotonic()+5
        while len(receiver.frame())<3 and time.monotonic()<deadline:
            time.sleep(.1)
        assert len(receiver.frame())>=3
        assert receiver.frame().sensor_ok.all()
    finally:
        receiver.close()
        server.shutdown()
        server.server_close()


def test_serial_bridge_writes_real_sqlite_rows(tmp_path):
    import os
    import sqlite3
    import subprocess
    import sys
    import time
    if sys.platform == 'win32':
        pytest.skip('POSIX pseudo-terminal integration')
    import pty
    master,slave=pty.openpty()
    database=tmp_path/'telemetry.db'
    process=subprocess.Popen([sys.executable,str(Path(__file__).with_name('bridge.py')),'--port',os.ttyname(slave),'--db',str(database)],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    count=0
    try:
        deadline=time.monotonic()+8
        while time.monotonic()<deadline:
            row=dict(t_ms=time.monotonic()*1000,roll=2,pitch=3,top=88,bottom=94,pid_r=-2,pid_p=-4,sensor_ok=True)
            os.write(master,(json.dumps(row)+'\n').encode())
            time.sleep(.15)
            if database.exists():
                try:
                    with sqlite3.connect(database) as db:
                        count=db.execute('SELECT COUNT(*) FROM telemetry').fetchone()[0]
                except sqlite3.OperationalError:
                    pass
            if count>=3:
                break
        assert count>=3
    finally:
        process.terminate()
        process.communicate(timeout=5)
        os.close(master)
        os.close(slave)
