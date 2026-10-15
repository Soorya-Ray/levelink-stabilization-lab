import io
import hashlib
import json
import sqlite3
import time
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from analysis import fault_events, fit_slr
from telemetry import LANReceiver, MQTTReceiver, demo_data, normalize_csv

st.set_page_config(page_title='Levelink · Stabilization Lab', page_icon='◈', layout='wide')
st.markdown('''<style>
.block-container {padding-top:2rem;max-width:1500px}
h1 {font-size:2.8rem!important;letter-spacing:-1.5px}
h2,h3 {letter-spacing:-.5px}
[data-testid="stMetric"] {background:#111e2b;border:1px solid #263645;border-radius:12px;padding:16px}
[data-testid="stMetricLabel"] {color:#9dafbf}
div[data-testid="stSidebar"] {border-right:1px solid #263645}
.eyebrow {color:#4ee0ba;letter-spacing:3px;font-size:12px;font-weight:700}
.hero {color:#9dafbf;max-width:860px;margin-bottom:24px}
</style>''', unsafe_allow_html=True)

if 'origin' not in st.session_state:
    st.session_state.origin = time.time()-90
if 'history' not in st.session_state:
    st.session_state.history = []
if 'recording' not in st.session_state:
    st.session_state.recording = False
    st.session_state.recorded = []

with st.sidebar:
    st.markdown('## ◈ LEVELINK')
    st.caption('STABILIZATION LAB / ESP32')
    source = st.selectbox('Telemetry source', ['Demo simulator', 'USB bridge', 'ESP32 Wi-Fi / LAN', 'Cloud MQTT', 'CSV replay'])
    page = st.radio('Workspace', ['Control room', 'Signal explorer', 'Regression lab', 'Experiment desk', 'System & setup'])
    st.divider()
    scenario = st.selectbox('Simulation scenario', ['Gentle tilting', 'Rough motion', 'Command saturation', 'Sensor dropout']) if source == 'Demo simulator' else None
    db_path = st.text_input('Bridge database', 'telemetry.db') if source == 'USB bridge' else ''
    esp_url = st.text_input('ESP32 telemetry URL', 'http://192.168.4.1/telemetry') if source == 'ESP32 Wi-Fi / LAN' else ''
    upload = st.file_uploader('Recorded telemetry CSV', type='csv') if source == 'CSV replay' else None
    window = st.slider('Chart window · seconds', 10, 180, 60)
    tilt_limit = st.slider('Base tilt advisory · °', 10, 80, 35)
    with st.expander('Command limits & experiment'):
        st.caption('Match the limits in firmware; these controls only change dashboard alerts.')
        servo_min = st.number_input('Minimum command · °', 0, 179, 0)
        servo_max = st.number_input('Maximum command · °', 1, 180, 180)
        experiment = st.text_input('Experiment label', 'review-run-01', max_chars=80)
        payload = st.number_input('Payload mass · g (metadata)', 0, 10000, 0, step=10)
    st.caption('BASE-MOUNTED IMU\n\nTray attitude and actual servo position are not measured.')

if servo_min >= servo_max:
    st.error('Minimum command must be below maximum command.')
    st.stop()

# Resource lives for the app process; every browser session keeps its own recordings.
@st.cache_resource
def mqtt_receiver(host, port, username, password, topic):
    return MQTTReceiver(host, port, username, password, topic)


@st.cache_resource
def lan_receiver(url):
    return LANReceiver(url)


def acquire():
    status = ''
    if source == 'Demo simulator':
        return demo_data(time.time()-st.session_state.origin, 180, scenario), 'SIMULATED DATA'
    if source == 'CSV replay':
        if upload is None:
            return pd.DataFrame(), 'Upload a CSV to inspect an experiment.'
        return normalize_csv(io.BytesIO(upload.getvalue())), 'RECORDED DATA · not a live connection'
    if source == 'Cloud MQTT':
        if 'mqtt' not in st.secrets:
            return pd.DataFrame(), 'Add the [mqtt] settings to Streamlit secrets. See System & setup.'
        cfg = dict(st.secrets['mqtt'])
        receiver = mqtt_receiver(cfg['host'], int(cfg.get('port', 8883)), cfg['username'], cfg['password'], cfg['topic'])
        return receiver.frame(), f'MQTT · {receiver.status} · rejected packets: {receiver.errors}'
    if source == 'USB bridge':
        path = Path(db_path)
        if not path.exists():
            return pd.DataFrame(), 'Start bridge.py first; the database does not exist yet.'
        with sqlite3.connect(f'file:{path.resolve()}?mode=ro', uri=True, timeout=1) as connection:
            df = pd.read_sql_query('SELECT * FROM (SELECT * FROM telemetry ORDER BY id DESC LIMIT 18000) ORDER BY id', connection)
        return df, 'USB SERIAL · read-only telemetry'
    receiver = lan_receiver(esp_url)
    return receiver.frame(), f'WI-FI / LAN · {receiver.status} · background polling at up to 10 Hz'


def chart(df, fields, colors, title, ytitle='Degrees', height=290):
    fig = go.Figure()
    for field, label, color in zip(fields, [x.replace('_', ' ').title() for x in fields], colors):
        fig.add_trace(go.Scatter(x=df.t_ms/1000, y=df[field], name=label, mode='lines', line=dict(color=color, width=2)))
    fig.update_layout(title=title, height=height, margin=dict(l=8,r=8,t=45,b=10),
        paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
        font=dict(color='#bacbd9'), xaxis_title='Device uptime / s', yaxis_title=ytitle,
        legend=dict(orientation='h', y=1.15), hovermode='x unified')
    fig.update_xaxes(gridcolor='#20303d')
    fig.update_yaxes(gridcolor='#20303d')
    return fig


def csv_bytes(df):
    result = df.copy()
    if 'source' not in result:
        result['source'] = source
    result['experiment'] = experiment
    result['payload_g'] = payload
    return result.to_csv(index=False).encode()


def render_regression(df):
    st.subheader('Learn the command response')
    st.write('Simple linear regression: one base-tilt input predicts one servo command. This identifies the controller’s mapping; it is not a payload-stability model or a future-tilt forecast.')
    axis = st.radio('Axis', ['Roll', 'Pitch'], horizontal=True)
    if st.button('Train & evaluate SLR', type='primary'):
        try:
            result = fit_slr(df, axis)
            result['axis'] = axis
            result['source'] = source
            result['trained_at'] = time.strftime('%H:%M:%S')
            st.session_state.model_result = result
        except ValueError as exc:
            st.warning(str(exc))
    result = st.session_state.get('model_result')
    if not result:
        st.info('Collect a varied tilt sweep, then train. The first 70% trains the model; the final 30% is held out for testing.')
        return
    if result['axis'] != axis or result['source'] != source:
        st.warning('The saved model belongs to another axis or source. Train again for this selection.')
        return
    a,b,c = st.columns(3)
    a.metric('Held-out MAE', f"{result['mae']:.2f}°")
    b.metric('Held-out R²', 'Undefined' if result['r2'] is None else f"{result['r2']:.3f}")
    c.metric('Mean-command baseline MAE', f"{result['baseline_mae']:.2f}°")
    st.code(f"{result['y']} = {result['intercept']:.3f} + ({result['slope']:.3f} × {result['x']})")
    st.caption(f"Trained at {result['trained_at']} · {len(result['train'])} train / {len(result['test'])} test samples · {source}")
    left,right = st.columns(2)
    fig = go.Figure()
    for name,color in [('train','#688299'),('test','#4ee0ba')]:
        subset = result[name]
        fig.add_trace(go.Scatter(x=subset[result['x']], y=subset[result['y']], mode='markers', name=name, marker=dict(size=5,color=color,opacity=.6)))
    xs = np.linspace(result['train'][result['x']].min(), result['train'][result['x']].max(), 100)
    fig.add_trace(go.Scatter(x=xs,y=result['intercept']+result['slope']*xs,name='SLR fit',line=dict(color='#f6bd60')))
    fig.update_layout(title='Tilt → commanded position', xaxis_title='Base tilt / °', yaxis_title='Servo command / °', height=340)
    left.plotly_chart(fig, use_container_width=True)
    residuals = result['test'].copy()
    residuals['residual'] = residuals[result['y']]-result['predicted']
    right.plotly_chart(chart(residuals,['residual'],['#a79bff'],'Held-out residuals',height=340), use_container_width=True)
    angle = st.slider('Explore a hypothetical base tilt · °', -90., 90., 0., step=.5)
    predicted = result['intercept']+result['slope']*angle
    st.metric('SLR command estimate · does not move hardware', f'{predicted:.1f}°')
    if not result['train'][result['x']].min() <= angle <= result['train'][result['x']].max():
        st.warning('Outside the training tilt range: this is extrapolation.')
    st.caption('Derivative action, command clipping, and timing cause departures from a straight line. A high R² mostly shows that firmware commands follow tilt; it is not proof of successful leveling.')
    metadata = {k: result[k] for k in ['slope','intercept','mae','baseline_mae','r2','axis','source','trained_at']}
    st.download_button('Download model report · JSON', json.dumps(metadata, indent=2), 'levelink-slr.json', 'application/json')


def setup():
    st.subheader('Your system, made observable')
    st.markdown('**Base MPU6050 → ESP32 compensation → two servo commands**\n\nTelemetry travels independently to this dashboard. The dashboard is read-only and cannot change gains or move the servos.')
    st.markdown('''**Fastest review setup**
1. Upload `firmware/levelink/levelink.ino` with its companion headers. Your original control calculations and pins are retained.
2. Close Arduino Serial Monitor, connect USB, and run `python bridge.py --list-ports`.
3. Run `python bridge.py --port YOUR_PORT` from the project directory.
4. Select **USB bridge** here. Begin an experiment and gently tilt both axes.

**Wireless local setup**
The supplied firmware starts an access point named `Levelink-Lab`. Connect the laptop to it, then select **ESP32 Wi-Fi / LAN**. Set your own AP password in `wifi_config.h`; see README. Default address: `http://192.168.4.1/telemetry`. Cloud-hosted Streamlit cannot reach this private address.

**Online setup**
Deploy `app.py` on Streamlit Community Cloud from GitHub. Create a TLS MQTT broker and put its settings in Streamlit secrets. Run the USB bridge with `--mqtt`; it sends live readings to the broker, which the cloud dashboard subscribes to. Your laptop must remain connected to the ESP32 and the internet. See `DEPLOY.md` for the complete steps.
''')
    st.code('[mqtt]\nhost = "your-cluster.s1.eu.hivemq.cloud"\nport = 8883\nusername = "dashboard-reader"\npassword = "YOUR_PASSWORD"\ntopic = "levelink/YOUR_RANDOM_DEVICE_ID/telemetry"', language='toml')
    st.info('Demonstration mode is synthetic. It is available immediately and must be labeled as simulated in your review.')
    st.caption('No tray sensor: no measured tray error, leveling percentage, actual shaft position, stall diagnosis, or settling time is claimed.')


@st.fragment(run_every=1)
def workspace():
    st.markdown('<div class="eyebrow">TWO AXES. ONE CLEAR VIEW.</div>', unsafe_allow_html=True)
    st.title('Keep your experiment in view.')
    st.markdown('<div class="hero">Base motion, commanded correction, and the evidence behind your prototype. A live workspace for your self-leveling carrier.</div>', unsafe_allow_html=True)
    if page == 'System & setup':
        setup()
        return
    try:
        df, status = acquire()
    except Exception as exc:
        st.error(f'Telemetry unavailable: {type(exc).__name__}. Check the connection and setup instructions.')
        st.caption(str(exc)[:200] if source != 'Cloud MQTT' else 'Check your broker settings in Streamlit secrets.')
        return
    st.caption(status)
    if source == 'Demo simulator':
        st.warning('DEMO MODE · All readings and model results on this source are simulated.')
    if source == 'CSV replay' and 'source' in df and df.source.astype(str).str.contains('Demo',case=False).any():
        st.warning('SIMULATED RECORDING · This file contains data exported from the demo simulator.')
    if df.empty:
        st.info('Waiting for telemetry. Open System & setup for connection instructions.')
        return
    # Display only the current uptime segment after a hardware restart.
    resets = np.where(np.diff(df.t_ms.to_numpy()) < 0)[0]
    if len(resets):
        df = df.iloc[resets[-1]+1:]
    df = df.reset_index(drop=True)
    row = df.iloc[-1]
    age = max(0, time.time()-row.received_at)
    live_source = source not in ['Demo simulator','CSV replay']
    if live_source and age > 3:
        st.error(f'STALE TELEMETRY · Last packet received {age:.1f}s ago. Values below are historical.')
    if not bool(row.sensor_ok):
        st.error('MPU READ FAILED · Angles are last-known values; check sensor wiring. Firmware commands neutral on failure.')
    if st.session_state.recording:
        # Host arrival time + device time distinguish restarts and repeated render cycles.
        seen = st.session_state.setdefault('record_seen', set())
        for record in df.to_dict('records'):
            key = record['t_ms'] if source == 'Demo simulator' else (record['t_ms'], record['received_at'])
            if key not in seen and record['received_at'] >= st.session_state.record_started:
                st.session_state.recorded.append(record)
                seen.add(key)
        if len(st.session_state.recorded) >= 18000:
            st.session_state.recording = False
            st.warning('Recording reached 18,000 samples and stopped. Export before starting another run.')
    view = df[df.t_ms >= row.t_ms-window*1000]
    if page == 'Signal explorer':
        st.subheader('Inspect the disturbance')
        st.caption('Measured base motion only. Frequency analysis is exploratory and requires approximately regular sampling.')
        r,p = np.radians([row.roll,row.pitch])
        rx = np.array([[1,0,0],[0,np.cos(r),-np.sin(r)],[0,np.sin(r),np.cos(r)]])
        ry = np.array([[np.cos(p),0,np.sin(p)],[0,1,0],[-np.sin(p),0,np.cos(p)]])
        vertices = (ry@rx@np.array([[-1,-.7,0],[1,-.7,0],[1,.7,0],[-1,.7,0]]).T).T
        attitude = go.Figure(go.Mesh3d(x=vertices[:,0],y=vertices[:,1],z=vertices[:,2],i=[0,0],j=[1,2],k=[2,3],color='#4ee0ba',opacity=.8,name='Measured base'))
        attitude.add_trace(go.Scatter3d(x=[-1.3,1.3,1.3,-1.3,-1.3],y=[-.9,-.9,.9,.9,-.9],z=[0]*5,mode='lines',line=dict(color='#f6bd60',width=3),name='Level reference'))
        attitude.update_layout(title='Base attitude · yaw fixed to zero for visualization',height=330,margin=dict(l=0,r=0,t=40,b=0),scene=dict(xaxis=dict(range=[-1.5,1.5],visible=False),yaxis=dict(range=[-1.5,1.5],visible=False),zaxis=dict(range=[-1.5,1.5],visible=False),aspectmode='cube'))
        st.plotly_chart(attitude,use_container_width=True)
        left,right = st.columns(2)
        phase = go.Figure(go.Scatter(x=view.roll,y=view.pitch,mode='markers',marker=dict(color=view.t_ms,colorscale='Teal',size=4)))
        phase.update_layout(title='Roll–pitch motion map',xaxis_title='Base roll / °',yaxis_title='Base pitch / °',height=360)
        left.plotly_chart(phase,use_container_width=True)
        hist = go.Figure()
        for name,color in [('roll','#4ee0ba'),('pitch','#a79bff')]:
            hist.add_trace(go.Histogram(x=view[name],name=name,opacity=.6,marker_color=color,nbinsx=30))
        hist.update_layout(title='Base angle distribution',barmode='overlay',xaxis_title='Angle / °',yaxis_title='Samples',height=360)
        right.plotly_chart(hist,use_container_width=True)
        dt = np.diff(view.t_ms.to_numpy())/1000
        valid_dt = dt[dt>0]
        if len(valid_dt)>20:
            st.metric('Median observed sample rate',f'{1/np.median(valid_dt):.1f} Hz')
            if np.all(dt>0) and np.std(dt)/np.mean(dt)<.15 and view.sensor_ok.astype(bool).all():
                spectrum = go.Figure()
                for name,color in [('roll','#4ee0ba'),('pitch','#a79bff')]:
                    signal=view[name].to_numpy()
                    weights=np.hanning(len(signal))
                    amplitude=2*np.abs(np.fft.rfft((signal-signal.mean())*weights))/weights.sum()
                    frequency=np.fft.rfftfreq(len(signal),np.median(valid_dt))
                    spectrum.add_trace(go.Scatter(x=frequency[1:],y=amplitude[1:],name=name,line=dict(color=color)))
                spectrum.update_layout(title='Base-motion spectrum · Hann window',xaxis_title='Frequency / Hz',yaxis_title='Approximate amplitude / °',height=300)
                st.plotly_chart(spectrum,use_container_width=True)
            else:
                st.info('Spectrum withheld: sampling is irregular, a sensor fault occurred, or device timing reset.')
        st.plotly_chart(chart(view,['pid_r','pid_p'],['#f6bd60','#67b7ff'],'Controller correction terms'),use_container_width=True)
        return
    if page == 'Regression lab':
        render_regression(df)
        return
    if page == 'Experiment desk':
        st.subheader('Turn a demonstration into evidence')
        c1,c2 = st.columns(2)
        if c1.button('● Start new recording', disabled=st.session_state.recording or source == 'CSV replay', type='primary'):
            st.session_state.recording = True
            st.session_state.recorded = []
            st.session_state.record_seen = set()
            st.session_state.record_started = time.time()
            st.rerun(scope='fragment')
        if c2.button('■ Stop recording', disabled=not st.session_state.recording):
            st.session_state.recording = False
            st.rerun(scope='fragment')
        st.write(f"{'Recording' if st.session_state.recording else 'Stopped'} · {len(st.session_state.recorded):,} recorded samples")
        if st.session_state.recorded:
            recorded = pd.DataFrame(st.session_state.recorded)
            st.download_button('Export recorded experiment', csv_bytes(recorded), 'levelink-recording.csv', 'text/csv')
        st.download_button('Export current buffer', csv_bytes(df), 'levelink-buffer.csv', 'text/csv')
        st.caption('Recordings are held in browser-session server memory. Export before closing the session or restarting the server. Source changes end and clear the prior recording.')
        st.markdown('**Review sequence:** level reference → slow roll sweep → slow pitch sweep → combined motion → hold at an inclination → return to level. Record a video with a fixed horizontal reference to assess the payload separately.')
        st.dataframe(df.tail(150), use_container_width=True, hide_index=True)
        return
    a,b,c,d = st.columns(4)
    a.metric('Base roll', f'{row.roll:+.2f}°')
    b.metric('Base pitch', f'{row.pitch:+.2f}°')
    c.metric('Top servo command', f'{row.top:.1f}°')
    d.metric('Bottom servo command', f'{row.bottom:.1f}°')
    left,right = st.columns([1.6,1])
    with left:
        st.plotly_chart(chart(view,['roll','pitch'],['#4ee0ba','#a79bff'],'01 / Base inclination'),use_container_width=True)
        st.plotly_chart(chart(view,['top','bottom'],['#f6bd60','#67b7ff'],'02 / Commanded compensation'),use_container_width=True)
    with right:
        st.subheader('Operating envelope')
        healthy_view = view[view.sensor_ok.astype(bool)]
        peak = healthy_view[['roll','pitch']].abs().max().max()
        rms = np.sqrt(np.mean(healthy_view[['roll','pitch']].to_numpy()**2)) if len(healthy_view) else np.nan
        saturated = ((view[['top','bottom']] <= servo_min+1)|(view[['top','bottom']] >= servo_max-1)).any(axis=1)
        st.metric('Base disturbance RMS · both axes',f'{rms:.2f}°' if np.isfinite(rms) else 'Unavailable')
        st.metric('Peak absolute base tilt',f'{peak:.2f}°' if np.isfinite(peak) else 'Unavailable')
        st.metric('Samples at command limit',f'{100*saturated.mean():.1f}%')
        st.caption('Base-motion statistics exclude failed sensor reads. These are not residual tray tilt. Limit occupancy is sample-based.')
        if abs(row.roll)>tilt_limit or abs(row.pitch)>tilt_limit:
            st.warning('Base tilt exceeds the selected advisory threshold.')
        elif bool(row.sensor_ok) and (not live_source or age <= 3):
            st.success('Telemetry healthy · within base-tilt advisory')
    with st.expander('Fault event timeline', expanded=True):
        events = fault_events(view,tilt_limit,servo_min,servo_max)
        if events.empty:
            st.caption('No sensor, tilt-advisory, or command-limit events in this window.')
        else:
            st.dataframe(events.tail(30),hide_index=True,use_container_width=True)
    st.caption('LEVELINK / prototype observability · ESP32 + MPU6050 + dual servos · telemetry only')


# Never mix sources in recording, polling history, or a trained model.
source_key = (source, scenario, db_path, esp_url, hashlib.sha256(upload.getvalue()).hexdigest() if upload else None)
if st.session_state.get('source_key') != source_key:
    st.session_state.source_key = source_key
    st.session_state.history = []
    st.session_state.recording = False
    st.session_state.recorded = []
    st.session_state.pop('model_result', None)
workspace()
