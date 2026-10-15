# Levelink · Stabilization Lab

A Streamlit dashboard for a base-mounted MPU6050, ESP32 DevKit, and two servo commands. Includes live charts, signal exploration, fault timelines, experiment recording, CSV replay, and simple linear regression with held-out evaluation.

**One sensor on the base measures base tilt. This project does not measure tray angle, servo shaft position, spill prevention, or stabilization accuracy.** Demo data is always labeled synthetic. SLR identifies the firmware's tilt-to-command mapping, not physical stabilization performance.

## Start here

Use Python 3.12. Open a terminal in this folder:

```sh
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

On Windows, activate with `.venv\Scripts\activate`. Open http://localhost:8501. The demo works immediately without hardware or credentials. Explore the sidebar's Control room, Signal explorer, Regression lab, Experiment desk, and System & setup.

## Connect real hardware over USB (recommended for tomorrow)

1. Save a backup of your existing Arduino sketch.
2. Open `firmware/levelink/levelink.ino`. Install the ESP32 board package and ESP32Servo library in Arduino IDE.
3. Copy `wifi_config.example.h` to `wifi_config.h` in that same sketch folder if it is absent. Set `ENABLE_WIFI = false` for USB-only, or choose a new AP password for Wi-Fi.
4. Select your ESP32 DevKit board and port, then compile/upload. Pins remain SDA 21, SCL 22, top servo 26, bottom servo 27. Calibration and controller gains are retained from your supplied sketch; Ki remains zero.
5. Close Arduino Serial Monitor. In a second terminal, activate the same virtual environment and run:

```sh
python bridge.py --list-ports
python bridge.py --port /dev/cu.YOUR_ESP32_PORT
```

6. Keep the bridge running. Choose **USB bridge** in the dashboard. Run both commands from this project folder so the default `telemetry.db` paths match.

The bridge reads JSON at 115200 baud, retains the latest approximately 18,000 samples in SQLite, and never sends actuator commands. Opening the serial port may reset the ESP32. Keep the mechanism clear while it initializes. A USB disconnect stops the bridge; rerun it after reconnecting.

## Use ESP32 Wi-Fi locally

With `ENABLE_WIFI = true`, the firmware creates `Levelink-Lab`. Join that network with the password in your local `wifi_config.h`. Choose **ESP32 Wi-Fi / LAN** in the locally running dashboard, URL `http://192.168.4.1/telemetry`. Up to roughly 10 readings per second are polled in a background thread; the display refreshes once per second. Network timing varies.

This is local wireless telemetry. The AP itself has no internet uplink. A cloud Streamlit server cannot reach `192.168.4.1`; use the MQTT relay described in [DEPLOY.md](DEPLOY.md). For the cloud USB relay, keep the laptop on its normal internet-connected Wi-Fi.

## Firmware changes

The original control calculations, gyro biases, angle offsets, servo range, pins, and gains are preserved. Human-readable periodic output is replaced by 10 Hz JSON from a low-priority task on core 0. The same task optionally handles the HTTP endpoint. A protected snapshot shares data with the control loop. Failed MPU reads emit `sensor_ok=false`, retain last-known tilt, and retain your existing neutral-command response; timing and previous-error values are refreshed on failure.

Wi-Fi/telemetry still consume shared CPU, power, and memory; compare physical behavior to your original sketch. The firmware targets the dual-core ESP32 DevKit and has been compiled with the user's Arduino-ESP32 3.3.11 package. A startup crash was captured on the ESP32-D0WD-V3: `spinlock_acquire` during `esp_bt_mem_release` in `initArduino`, before `setup()`. The sketch overrides the core's supported `btInUse()` hook to retain Bluetooth memory and avoid that failing release path; Bluetooth is not started. This costs some available heap. If Wi-Fi affects behavior, disable it and use USB. Servo mechanical limits and supply suitability must be established on your actual build; the original 0–180° range is retained, not certified safe.

## SLR experiment

1. Collect at least 60 healthy samples while gently tilting the base through both directions (at least 5° training variation).
2. Open Regression lab, select roll or pitch, and click **Train & evaluate SLR**.
3. The first 70% of valid samples train a `LinearRegression`; the final 30% test it. Device timestamp resets discard older runs.
4. Report slope, intercept, held-out MAE, R², and the constant mean-command baseline MAE. Constant test targets have undefined R².
5. Download the JSON report. Use the hypothetical-angle slider to explore predictions; it cannot move servos.

Roll predicts the top servo command; pitch predicts the bottom command. Derivative action and saturation mean the mapping need not be exactly linear. A high R² can be expected because commands are already calculated from tilt. It is evidence of command consistency, not independent proof of leveling or predictive maintenance. For stronger validation, record a separate run and evaluate outside the training sweep; contiguous samples remain correlated even with chronological splitting.

## Recording and limits

Experiment desk starts a fresh memory recording and exports CSV with source, experiment label, and payload metadata. Export before closing the browser session or restarting the server. Source changes clear the current recording. Live buffers and recordings are bounded to approximately 18,000 samples (30 minutes at 10 Hz). The app is an experiment dashboard, not permanent cloud storage.

CSV needs: `t_ms,roll,pitch,top,bottom,pid_r,pid_p,sensor_ok`. Angles are degrees, gyro-derived PID outputs are command corrections, time is device uptime in milliseconds, and sensor_ok is boolean or 0/1. CSV replay displays the recorded buffer; it is not a timed playback. USB logs also contain host arrival time and row ID. LAN and MQTT histories are process memory and are lost on restart.

Alerts detect sensor-read failure, stale arrivals, configured command-limit occupancy, and excessive base tilt. They do not diagnose actual servo stall, overload, bad wiring, power brownout, or payload instability. Limits in the sidebar change dashboard alerts only. A fault timeline reports transitions visible in the selected history window; an event at the left edge may have begun before that window.

Cloud broker credentials are server-side secrets. Use a unique topic and broker access controls; do not use an anonymous public broker for your experiment. A public app exposes displayed telemetry to its visitors. The receiver is shared across visitors to that app process; per-browser recording and model state are separate.

## Review pitch

“Levelink is a low-cost tilt-compensating carrier prototype for small containers on indoor carts. A base-mounted inertial sensor drives two servo axes. A wireless dashboard makes base motion and requested compensation observable, records repeatable experiments, flags sensor and operating-limit events, and identifies command response using simple linear regression. Payload leveling is demonstrated independently with a fixed visual reference.”

## Validation

Run `pip install pytest`, then `python -m pytest -q`. Tests cover packet validation, fault transitions, regression holdout behavior, CSV parsing, and Streamlit page execution. Hardware compilation and physical verification remain separate.

## Official references

- [Streamlit deployment](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/deploy)
- [Streamlit fragments](https://docs.streamlit.io/develop/api-reference/execution-flow/st.fragment)
- [MQTT Python client](https://eclipse.dev/paho/files/paho.mqtt.python/html/client.html)
- [HiveMQ Cloud getting started](https://docs.hivemq.com/hivemq-cloud/quick-start-guide.html)

### Startup PWM diagnostic

The firmware prints `PWM CHECK` for GPIO26 and GPIO27 at neutral before Wi-Fi starts. It reports attachment, LEDC frequency/duty, and a pulse duration measured by enabling input readback on the output pad. Observed neutral pulses on the test board were 50 Hz and approximately 1484 microseconds. This does not verify power or the signal at the servo connector; check the separate supply, common ground, and signal wiring if the motors do not respond.
