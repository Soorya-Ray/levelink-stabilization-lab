#pragma once
#include <WiFi.h>
#include <WebServer.h>
#include "wifi_config.h"

// Network work runs in its own low-priority task. Only a short snapshot copy is locked.
struct TelemetrySnapshot {
  uint32_t t_ms;
  float roll, pitch, top, bottom, pid_r, pid_p;
  bool sensor_ok;
};
static TelemetrySnapshot snapshot = {0,0,0,90,90,0,0,false};
static portMUX_TYPE snapshotMux = portMUX_INITIALIZER_UNLOCKED;

static void telemetryUpdate(float r,float p,float t,float b,float pr,float pp,bool ok) {
  TelemetrySnapshot next = {millis(),r,p,t,b,pr,pp,ok};
  portENTER_CRITICAL(&snapshotMux);
  snapshot = next;
  portEXIT_CRITICAL(&snapshotMux);
}

static void telemetryJSON(char* buffer,size_t size) {
  TelemetrySnapshot value;
  portENTER_CRITICAL(&snapshotMux);
  value = snapshot;
  portEXIT_CRITICAL(&snapshotMux);
  snprintf(buffer,size,
    "{\"t_ms\":%lu,\"roll\":%.3f,\"pitch\":%.3f,\"top\":%.2f,\"bottom\":%.2f,\"pid_r\":%.3f,\"pid_p\":%.3f,\"sensor_ok\":%s}",
    (unsigned long)value.t_ms,value.roll,value.pitch,value.top,value.bottom,value.pid_r,value.pid_p,value.sensor_ok?"true":"false");
}

static void telemetryTask(void*) {
  WebServer server(80);
  if (ENABLE_WIFI) {
    WiFi.mode(WIFI_AP);
    WiFi.softAP(AP_NAME,AP_PASSWORD);
    server.on("/telemetry",HTTP_GET,[&server]() {
      char buffer[320];
      telemetryJSON(buffer,sizeof(buffer));
      server.sendHeader("Cache-Control","no-store");
      server.send(200,"application/json",buffer);
    });
    server.on("/",HTTP_GET,[&server]() {
      server.send(200,"text/plain","Levelink ESP32 telemetry. GET /telemetry. Dashboard is read-only.");
    });
    server.begin();
  }
  uint32_t lastSent = 0;
  for (;;) {
    if (ENABLE_WIFI) server.handleClient();
    if (millis()-lastSent >= 100) {
      lastSent = millis();
      char buffer[320];
      telemetryJSON(buffer,sizeof(buffer));
      Serial.println(buffer);
    }
    vTaskDelay(pdMS_TO_TICKS(5));
  }
}

static void telemetryBegin() {
  // Standard dual-core ESP32 DevKit: Arduino loop is normally on core 1.
  BaseType_t result = xTaskCreatePinnedToCore(telemetryTask,"telemetry",6144,nullptr,1,nullptr,0);
  if (result != pdPASS) Serial.println("TELEMETRY TASK START FAILED");
}
