# Verification record

Verified on Python 3.12 on macOS. Direct dependency versions in requirements.txt match the tested environment.

`python -m pytest -q`: **14 passed in 57.70 seconds**.

Coverage: telemetry validation and CSV roundtrip; malformed packets; chronological SLR holdout, insufficient variation, and timestamp resets; fault transition detection; execution of all five Streamlit pages and model training; stable demo timestamps; HTTP receiver against a local simulated device; serial bridge against a pseudo-terminal with real SQLite writes.

The local Streamlit server was started and the rendered control room was verified in the in-app browser.

Not verified: Arduino compilation, firmware upload, actual IMU/servo operation, real MQTT broker connectivity, and Streamlit Cloud deployment. Cloud hosting requires the account setup described in DEPLOY.md. Hardware behavior must be checked against your known-working sketch.
