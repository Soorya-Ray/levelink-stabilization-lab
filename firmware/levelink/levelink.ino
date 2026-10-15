#include <Wire.h>
#include <ESP32Servo.h>
#include <math.h>
#include "telemetry_link.h"

// =====================================================
// PIN CONFIGURATION
// =====================================================

#define SDA_PIN 21
#define SCL_PIN 22

#define MPU_ADDR 0x68

#define TOP_SERVO_PIN 26
#define BOTTOM_SERVO_PIN 27


// =====================================================
// SERVO CONFIGURATION
// =====================================================

const float TOP_CENTER = 90.0;
const float BOTTOM_CENTER = 90.0;

// ±60° correction
const float SERVO_MIN = 0.0;
const float SERVO_MAX = 180.0;


// =====================================================
// MPU CALIBRATION
// =====================================================

// Gyroscope bias obtained from your calibration
const float GYRO_BIAS_X = -644.88;
const float GYRO_BIAS_Y = 177.40;
const float GYRO_BIAS_Z = -27.15;

// Level reference obtained from your calibration
const float ROLL_OFFSET = 2.82;
const float PITCH_OFFSET = 1.56;


// =====================================================
// PID PARAMETERS
// =====================================================

// STARTING VALUES ONLY.
// We will tune these experimentally.

float Kp = 1.20;
float Ki = 0.00;
float Kd = 0.08;


// Integral limits to prevent integral windup
const float INTEGRAL_LIMIT = 30.0;


// =====================================================
// SERVO OBJECTS
// =====================================================

Servo topServo;
Servo bottomServo;


// =====================================================
// PID VARIABLES
// =====================================================

float rollIntegral = 0.0;
float pitchIntegral = 0.0;

float previousRollError = 0.0;
float previousPitchError = 0.0;


// =====================================================
// FILTER VARIABLES
// =====================================================

float rollAngle = 0.0;
float pitchAngle = 0.0;

unsigned long previousTime;


// =====================================================
// MPU READ FUNCTION
// =====================================================

bool readMPU(
  int16_t &ax,
  int16_t &ay,
  int16_t &az,
  int16_t &gx,
  int16_t &gy,
  int16_t &gz
) {

  Wire.beginTransmission(MPU_ADDR);
  Wire.write(0x3B);

  if (Wire.endTransmission(false) != 0) {
    return false;
  }

  if (Wire.requestFrom(MPU_ADDR, 14, true) != 14) {
    return false;
  }

  ax = (Wire.read() << 8) | Wire.read();
  ay = (Wire.read() << 8) | Wire.read();
  az = (Wire.read() << 8) | Wire.read();

  // Skip temperature
  Wire.read();
  Wire.read();

  gx = (Wire.read() << 8) | Wire.read();
  gy = (Wire.read() << 8) | Wire.read();
  gz = (Wire.read() << 8) | Wire.read();

  return true;
}


// =====================================================
// SETUP
// =====================================================

void setup() {

  Serial.begin(115200);

  delay(1000);

  // -----------------------------
  // Start I2C
  // -----------------------------

  Wire.begin(SDA_PIN, SCL_PIN);

  // -----------------------------
  // Wake MPU-6050
  // -----------------------------

  Wire.beginTransmission(MPU_ADDR);
  Wire.write(0x6B);
  Wire.write(0x00);
  Wire.endTransmission();

  delay(500);


  // -----------------------------
  // Attach servos
  // -----------------------------

  topServo.setPeriodHertz(50);
  bottomServo.setPeriodHertz(50);

  topServo.attach(TOP_SERVO_PIN, 500, 2500);
  bottomServo.attach(BOTTOM_SERVO_PIN, 500, 2500);


  // -----------------------------
  // Move servos to neutral
  // -----------------------------

  topServo.write((int)TOP_CENTER);
  bottomServo.write((int)BOTTOM_CENTER);

  delay(1000);


  // -----------------------------
  // Initialize angles
  // -----------------------------

  rollAngle = 0.0;
  pitchAngle = 0.0;

  previousTime = micros();


  Serial.println();
  Serial.println("======================================");
  Serial.println("   ESP32 SELF-STABILIZING PLATFORM");
  Serial.println("======================================");
  Serial.println();

  Serial.println("MPU: 0x68");
  Serial.println("Top servo: GPIO 26");
  Serial.println("Bottom servo: GPIO 27");

  Serial.println();
  Serial.println("PID:");
  Serial.print("Kp = ");
  Serial.println(Kp);

  Serial.print("Ki = ");
  Serial.println(Ki);

  Serial.print("Kd = ");
  Serial.println(Kd);

  Serial.println();
  Serial.println("KEEP PLATFORM LEVEL...");
  delay(2000);

  telemetryBegin();
  Serial.println("STABILIZATION STARTED");
  Serial.println();

  previousTime = micros();
}


// =====================================================
// MAIN CONTROL LOOP
// =====================================================

void loop() {

  // ===================================================
  // READ MPU
  // ===================================================

  int16_t ax, ay, az;
  int16_t gx, gy, gz;

  if (!readMPU(ax, ay, az, gx, gy, gz)) {

    Serial.println("MPU READ ERROR");

    // Put servos at neutral if sensor communication fails
    topServo.write((int)TOP_CENTER);
    bottomServo.write((int)BOTTOM_CENTER);

    telemetryUpdate(rollAngle,pitchAngle,TOP_CENTER,BOTTOM_CENTER,0,0,false);
    previousTime = micros();
    previousRollError = -rollAngle;
    previousPitchError = -pitchAngle;
    delay(100);

    return;
  }


  // ===================================================
  // ACCELEROMETER
  // ===================================================

  float axg = ax / 16384.0;
  float ayg = ay / 16384.0;
  float azg = az / 16384.0;


  // ===================================================
  // ACCELEROMETER ANGLES
  // ===================================================

  float accelRoll =
    atan2(ayg, azg) * 180.0 / PI;

  float accelPitch =
    atan2(
      -axg,
      sqrt(ayg * ayg + azg * azg)
    ) * 180.0 / PI;


  // Apply your level calibration
  accelRoll -= ROLL_OFFSET;
  accelPitch -= PITCH_OFFSET;


  // ===================================================
  // GYROSCOPE
  // ===================================================

  float gyroX =
    (gx - GYRO_BIAS_X) / 131.0;

  float gyroY =
    (gy - GYRO_BIAS_Y) / 131.0;

  float gyroZ =
    (gz - GYRO_BIAS_Z) / 131.0;


  // ===================================================
  // CALCULATE DT
  // ===================================================

  unsigned long currentTime = micros();

  float dt =
    (currentTime - previousTime) / 1000000.0;

  previousTime = currentTime;


  // Prevent bad timing values
  if (dt <= 0.0 || dt > 0.1) {
    dt = 0.01;
  }


  // ===================================================
  // COMPLEMENTARY FILTER
  // ===================================================

  // Integrate gyro
  float gyroRoll =
    rollAngle + gyroX * dt;

  float gyroPitch =
    pitchAngle + gyroY * dt;


  // Combine gyro + accelerometer
  rollAngle =
    0.98 * gyroRoll +
    0.02 * accelRoll;

  pitchAngle =
    0.98 * gyroPitch +
    0.02 * accelPitch;


  // ===================================================
  // PID ERROR
  // ===================================================

  // Desired platform orientation = 0°
  float rollError =
    0.0 - rollAngle;

  float pitchError =
    0.0 - pitchAngle;


  // ===================================================
  // INTEGRAL
  // ===================================================

  rollIntegral += rollError * dt;
  pitchIntegral += pitchError * dt;


  rollIntegral =
    constrain(
      rollIntegral,
      -INTEGRAL_LIMIT,
      INTEGRAL_LIMIT
    );

  pitchIntegral =
    constrain(
      pitchIntegral,
      -INTEGRAL_LIMIT,
      INTEGRAL_LIMIT
    );


  // ===================================================
  // DERIVATIVE
  // ===================================================

  float rollDerivative =
    (rollError - previousRollError) / dt;

  float pitchDerivative =
    (pitchError - previousPitchError) / dt;


  previousRollError = rollError;
  previousPitchError = pitchError;


  // ===================================================
  // PID OUTPUT
  // ===================================================

  float rollOutput =
    Kp * rollError +
    Ki * rollIntegral +
    Kd * rollDerivative;

  float pitchOutput =
    Kp * pitchError +
    Ki * pitchIntegral +
    Kd * pitchDerivative;


  // ===================================================
  // SERVO COMMAND
  // ===================================================

  // TOP SERVO
  float topCommand =
    TOP_CENTER + rollOutput;


  // BOTTOM SERVO
  // Direction intentionally reversed
  float bottomCommand =
    BOTTOM_CENTER - pitchOutput;


  // ===================================================
  // SAFETY LIMITS
  // ===================================================

  topCommand =
    constrain(
      topCommand,
      SERVO_MIN,
      SERVO_MAX
    );

  bottomCommand =
    constrain(
      bottomCommand,
      SERVO_MIN,
      SERVO_MAX
    );


  // ===================================================
  // WRITE SERVOS
  // ===================================================

  topServo.write((int)topCommand);
  bottomServo.write((int)bottomCommand);


  // ===================================================
  // SERIAL MONITOR
  // ===================================================

  telemetryUpdate(rollAngle,pitchAngle,topCommand,bottomCommand,rollOutput,pitchOutput,true);


  // ===================================================
  // CONTROL LOOP DELAY
  // ===================================================

  delay(5);
}