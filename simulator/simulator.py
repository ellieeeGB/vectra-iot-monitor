"""Simulador VECTRA: genera lecturas ficticias de los 5 sensores y las envía a la API.

Simula un recorrido corto en Querétaro con vibración normal y, de vez en cuando,
un episodio de vibración anómala (útil para probar el dashboard y, más adelante,
la detección de anomalías). Los datos NO son reales.
"""
import math
import os
import random
import time

import requests

API_URL = os.getenv("API_URL", "http://localhost:8000").rstrip("/")
DEVICE_CODE = os.getenv("DEVICE_CODE", "ESP32-DEMO-01")
INTERVAL = float(os.getenv("INTERVAL_S", "3"))
ANOMALY_EVERY = int(os.getenv("ANOMALY_EVERY", "40"))  # ciclos entre anomalías (0 = nunca)
ANOMALY_LEN = 4

LAT0, LON0 = 20.54826, -100.27475  # punto de partida (UPQ aprox.)


def make_batch(step: int, anomaly: bool) -> list[dict]:
    noise = 0.25 if anomaly else 0.02          # g de vibración
    heading = step / 30.0
    speed = max(0.0, 25 + 15 * math.sin(step / 20.0) + random.gauss(0, 1.5))
    r = [
        ("temperature", 25 + 1.5 * math.sin(step / 50.0) + random.gauss(0, 0.2)),
        ("distance", max(2.0, 150 + 100 * math.sin(step / 15.0) + random.gauss(0, 3))),
        ("gas", 0),
        ("acc_x", random.gauss(0, noise)),
        ("acc_y", random.gauss(0, noise)),
        ("acc_z", 1.0 + random.gauss(0, noise)),
        ("gyro_x", random.gauss(0, 8 if anomaly else 1)),
        ("gyro_y", random.gauss(0, 8 if anomaly else 1)),
        ("gyro_z", random.gauss(0, 8 if anomaly else 1)),
        ("lat", LAT0 + 0.0004 * math.sin(heading) + step * 0.000004),
        ("lon", LON0 + 0.0004 * math.cos(heading) + step * 0.000004),
        ("speed", speed),
    ]
    return [{"sensor_type": k, "value": round(v, 5)} for k, v in r]


def main() -> None:
    print(f"Simulador → {API_URL} como {DEVICE_CODE} cada {INTERVAL}s", flush=True)
    step = 0
    anomaly_left = 0
    while True:
        if ANOMALY_EVERY and step > 0 and step % ANOMALY_EVERY == 0:
            anomaly_left = ANOMALY_LEN
        anomaly = anomaly_left > 0
        anomaly_left = max(0, anomaly_left - 1)
        body = {"device_code": DEVICE_CODE, "readings": make_batch(step, anomaly)}
        try:
            r = requests.post(f"{API_URL}/api/v1/readings/batch", json=body, timeout=5)
            print(f"[{step}] {r.status_code} {'ANOMALÍA ' if anomaly else ''}{r.text[:80]}", flush=True)
        except requests.RequestException as exc:
            print(f"[{step}] error de red: {exc}", flush=True)
        step += 1
        time.sleep(INTERVAL)


if __name__ == "__main__":
    main()
