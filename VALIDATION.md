# Verification record

Verified on Python 3.12 on macOS. Direct dependency versions in requirements.txt match the tested environment.

`python -m pytest -q`: **14 passed in 57.70 seconds**.

Coverage: telemetry validation and CSV roundtrip; malformed packets; chronological SLR holdout, insufficient variation, and timestamp resets; fault transition detection; execution of all five Streamlit pages and model training; stable demo timestamps; HTTP receiver against a local simulated device; serial bridge against a pseudo-terminal with real SQLite writes.

The local Streamlit server was started and the rendered control room was verified in the in-app browser.

Firmware follow-up: compiled with Arduino-ESP32 3.3.11 for the ESP32 Dev Module. Captured a pre-setup crash in Bluetooth memory release, added the core-supported btInUse() override, and flashed the corrected application uncompressed at 0x10000. Flash hash verified. A fresh boot produced STABILIZATION STARTED and 99 healthy sensor packets over approximately ten seconds, without assertion/panic/brownout markers. The last observed tilt was approximately roll 170°, pitch 46°, with the top command at its lower limit; physical leveling and mechanism behavior require user verification.

Not verified: actual servo shaft movement and physical stabilization performance, real MQTT broker connectivity, and Streamlit Cloud deployment. Cloud hosting requires the account setup described in DEPLOY.md. Hardware behavior must be checked against your known-working sketch.
