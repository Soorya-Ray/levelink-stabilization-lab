# Tomorrow's review · 3-minute walkthrough

## 0:00 — Purpose

“Our prototype is a low-cost tilt-compensating carrier for small containers on indoor carts. It addresses slow base inclination, such as ramps, using two servo axes. We added a dashboard to make its behavior observable and record experiments.”

## 0:30 — Hardware and live data

Select your real connection source, not the simulator. Gently tilt roll and pitch separately. Point to measured base roll/pitch and commanded servo angles. Explain that the sensor is on the base, so this is disturbance compensation. Use a fixed visual reference to demonstrate the payload independently.

“These plots show the disturbance and the correction requested by the controller. We do not have a second sensor measuring actual payload tilt.”

## 1:10 — Diagnostics

Show the signal explorer: 3D base attitude, roll–pitch motion map, angle distribution, sample rate, and spectrum if sampling qualifies. Point out the difference between base-motion RMS and payload leveling accuracy.

For fault demonstrations, switch to the clearly labeled simulator and choose Sensor dropout or Command saturation. This avoids deliberately disconnecting the live sensor or forcing the mechanism against stops. Explain that these are simulated test cases for the dashboard.

## 1:45 — SLR model

Switch back to real telemetry and gather a sweep with at least 60 healthy samples. Train roll, then pitch. Show the equation, held-out MAE, R², baseline comparison, and residual plot.

“SLR identifies the command mapping from one tilt input. The first 70% trains the model; the last 30% tests it. It is not proof that the payload stayed level. Derivative corrections and command limits explain departures from the fitted line.”

## 2:30 — Evidence

Start an experiment recording, demonstrate a short sweep, stop, and download the CSV. Download a model report as well. Describe future work as adding a payload sensor for independent feedback and measured stabilization accuracy.

## Questions to expect

- **Is the mechanism novel?** The contribution is the integrated low-cost carrier prototype, telemetry, explicit operating-limit reporting, and evaluation workflow. Self-leveling mechanisms are established.
- **Why SLR?** It provides an interpretable baseline for the tilt-to-command response. It does not add intelligence to the physical controller.
- **Does it prevent spills?** This prototype compensates for slow tilt. Acceleration and sloshing require separate evaluation.
- **Does it detect servo stall?** No. It detects requested-command limits, not actual shaft motion or motor current.
- **What happens without the internet?** The existing controller continues locally. The dashboard marks stale telemetry. USB local operation needs no internet once dependencies are installed.
- **Where is the data saved?** Local USB buffer in SQLite; experiment CSV files after export. Cloud live history is temporary process memory.
- **What is the immediate application?** A small-container carrier demonstrator for slowly moving indoor carts. It is not validated for medical samples, road vehicles, rockets, or drones.
