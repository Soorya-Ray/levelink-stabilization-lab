# Put Levelink online

## 1. Deploy the dashboard (demo works immediately)

Streamlit Community Cloud is the recommended host for this Python Streamlit app. Use its official flow instead of trying to run the Streamlit server on Vercel.

1. Use the prepared private repository: https://github.com/Soorya-Ray/levelink-stabilization-lab (branch `main`). For another account, copy this project's files to your own repository. Keep `.streamlit/config.toml`; do not commit `.streamlit/secrets.toml`, a telemetry database, or your personal `wifi_config.h`.
2. Visit https://share.streamlit.io and sign in using GitHub. Authorize access to the repository if asked.
3. Choose **Create app**, select the repository and branch, and set the entrypoint to `app.py`.
4. In advanced settings choose Python 3.12 if available. Deploy.
5. Open the returned `https://….streamlit.app` address. Demo mode is ready without a broker. Cloud live mode requires the next steps.

## 2. Create a TLS MQTT broker

Use HiveMQ Cloud or another managed MQTT broker supporting TLS on port 8883. HiveMQ's current guide offers a Starter trial; do not look for its retired new Serverless cluster signup. Check the provider's current plan and limits when creating the account; this project does not purchase hosting.

1. Create a broker cluster. Copy the hostname (hostname only, without `mqtts://`).
2. Create credentials allowed to publish and subscribe to a unique topic such as `levelink/REPLACE_WITH_RANDOM_ID/telemetry`. Prefer separate write-only bridge and read-only dashboard credentials where your plan supports permissions.
3. In Streamlit's app settings → Secrets, add:

```toml
[mqtt]
host = "YOUR_BROKER_HOSTNAME"
port = 8883
username = "YOUR_SUBSCRIBER_USERNAME"
password = "YOUR_SUBSCRIBER_PASSWORD"
topic = "levelink/YOUR_RANDOM_ID/telemetry"
```

4. Save, restart if needed, and choose **Cloud MQTT** in the dashboard.

## 3. Relay your USB hardware to the cloud

Upload the provided firmware and connect USB. Keep your laptop connected to the internet, close Serial Monitor, and activate the Python environment. On macOS/zsh:

```sh
export MQTT_HOST='YOUR_BROKER_HOSTNAME'
export MQTT_USERNAME='YOUR_PUBLISHER_USERNAME'
export MQTT_TOPIC='levelink/YOUR_RANDOM_ID/telemetry'
read -s 'MQTT_PASSWORD?MQTT password: '
export MQTT_PASSWORD
python bridge.py --list-ports
python bridge.py --port /dev/cu.YOUR_ESP32_PORT --mqtt
```

The password prompt keeps the password out of shell history. Use your actual port, not the placeholder. Both ends must use the same broker and topic. TLS certificates are checked using Python's trusted certificate store. No insecure TLS fallback is included. Publish uses QoS 0, with no retained telemetry; data generated during a disconnect may be dropped. The local database continues recording while MQTT reconnects.

Keep that terminal running during the review. The cloud app receives approximately 10 samples per second and redraws once per second. Closing the relay stops live hardware telemetry; after three seconds the dashboard labels existing data stale.

**This cloud path uses a laptop relay.** ESP32-to-broker direct Wi-Fi publishing is not included in this version. The firmware's Wi-Fi mode serves a local endpoint; it does not publish directly to the internet. This avoids introducing broker credentials and TLS setup into your working control sketch overnight.

## Troubleshooting

- **No USB ports:** use a data-capable USB cable and install the board's serial driver if required.
- **Port busy:** close Serial Monitor and other programs using the serial port.
- **MQTT connected, no data:** verify both topic strings and permissions; ensure bridge prints valid packet counts.
- **MQTT disconnected:** verify hostname, TLS port, credentials, and internet access. Some networks block port 8883.
- **Cloud app cannot reach ESP32:** private LAN addresses are inaccessible from Streamlit Cloud; use the relay.
- **Empty regression:** collect 60 healthy samples with enough tilt variation, then train explicitly.
- **Cloud app restarts:** memory history and recordings reset; export CSV during experiments.

Deployment instructions follow [Streamlit's official guide](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/deploy). HiveMQ account setup follows its [official quick start](https://docs.hivemq.com/hivemq-cloud/quick-start-guide.html).
