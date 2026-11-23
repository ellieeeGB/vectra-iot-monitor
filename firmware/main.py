"""VECTRA · firmware MicroPython para ESP32.

Lee DS18B20, HC-SR04, IMU MPU6500/6050, módulo MQ (digital) y GPS NEO-6M, y envía
un lote JSON por HTTP POST a /api/v1/readings/batch.

Si no hay conexión, guarda los lotes en RAM y los reenvía al reconectar con `age_s`
(segundos transcurridos desde la medición) para que el servidor los fechue bien
sin necesitar reloj en la ESP32.

LIMITACIÓN: el buffer vive en RAM; si la placa se reinicia o se queda sin energía
se pierde. Hardware NO probado por el autor del código: validar en la placa real.
"""
import time

import machine
import network
import onewire
import ds18x20
import urequests as requests
import ujson as json

import config as cfg

# ---------- sensores ----------
ow = ds18x20.DS18X20(onewire.OneWire(machine.Pin(cfg.PIN_DS18B20)))
roms = ow.scan()

trig = machine.Pin(cfg.PIN_TRIG, machine.Pin.OUT)
echo = machine.Pin(cfg.PIN_ECHO, machine.Pin.IN)
mq = machine.Pin(cfg.PIN_MQ_DO, machine.Pin.IN)

i2c = machine.I2C(0, sda=machine.Pin(cfg.PIN_I2C_SDA), scl=machine.Pin(cfg.PIN_I2C_SCL), freq=400000)
try:
    i2c.writeto_mem(cfg.MPU_ADDR, 0x6B, b"\x00")  # sale de modo sleep; ±2 g y ±250 °/s por defecto
except OSError:
    print("IMU no responde")

gps_uart = machine.UART(2, baudrate=9600, rx=cfg.PIN_GPS_RX)
gps = {"lat": None, "lon": None, "speed": None, "t": 0}
_nmea_buf = b""


def read_temperature():
    if not roms:
        return None
    ow.convert_temp()
    time.sleep_ms(750)
    t = ow.read_temp(roms[0])
    return t if -55 <= t <= 125 else None


def read_distance_cm():
    trig.value(0)
    time.sleep_us(2)
    trig.value(1)
    time.sleep_us(10)
    trig.value(0)
    try:
        us = machine.time_pulse_us(echo, 1, 30000)
    except OSError:
        return None
    if us < 0:
        return None
    return us / 58.0  # ida y vuelta -> cm


def _s16(b, i):
    v = (b[i] << 8) | b[i + 1]
    return v - 65536 if v & 0x8000 else v


def read_imu():
    try:
        d = i2c.readfrom_mem(cfg.MPU_ADDR, 0x3B, 14)
    except OSError:
        return None
    return {
        "acc_x": _s16(d, 0) / 16384.0, "acc_y": _s16(d, 2) / 16384.0, "acc_z": _s16(d, 4) / 16384.0,
        "gyro_x": _s16(d, 8) / 131.0, "gyro_y": _s16(d, 10) / 131.0, "gyro_z": _s16(d, 12) / 131.0,
    }


def _coord(raw, hemi):
    if not raw:
        return None
    dot = raw.index(".")
    deg = float(raw[: dot - 2])
    val = deg + float(raw[dot - 2:]) / 60.0
    return -val if hemi in ("S", "W") else val


def poll_gps():
    """Lee lo que haya en el UART y actualiza la última posición válida (RMC)."""
    global _nmea_buf
    data = gps_uart.read()
    if data:
        _nmea_buf += data
    while b"\n" in _nmea_buf:
        line, _nmea_buf = _nmea_buf.split(b"\n", 1)
        try:
            s = line.decode().strip()
        except UnicodeError:
            continue
        if s[3:6] == "RMC":
            f = s.split(",")
            if len(f) > 7 and f[2] == "A":  # A = fix válido
                lat, lon = _coord(f[3], f[4]), _coord(f[5], f[6])
                if lat is not None and lon is not None:
                    gps["lat"], gps["lon"] = lat, lon
                    gps["speed"] = float(f[7]) * 1.852 if f[7] else None  # nudos -> km/h
                    gps["t"] = time.ticks_ms()
    if len(_nmea_buf) > 512:
        _nmea_buf = b""


# ---------- red ----------
wlan = network.WLAN(network.STA_IF)
wlan.active(True)


def ensure_wifi(wait_s=10):
    if wlan.isconnected():
        return True
    wlan.connect(cfg.WIFI_SSID, cfg.WIFI_PASSWORD)
    t0 = time.time()
    while not wlan.isconnected() and time.time() - t0 < wait_s:
        time.sleep_ms(200)
    return wlan.isconnected()


def post(batch):
    """Envía un lote. Devuelve True si el servidor respondió 2xx."""
    body = {
        "device_code": cfg.DEVICE_CODE,
        "age_s": round(time.time() - batch["t0"], 1),
        "readings": batch["readings"],
    }
    try:
        r = requests.post(
            cfg.API_URL + "/api/v1/readings/batch",
            data=json.dumps(body),
            headers={"Content-Type": "application/json"},
        )
        ok = 200 <= r.status_code < 300
        if not ok:
            print("API:", r.status_code, r.text[:80])
        r.close()
        return ok or r.status_code == 422  # 422 = lote inválido: reintentar no lo arregla
    except Exception as exc:  # OSError, timeouts, DNS...
        print("POST falló:", exc)
        return False


def collect():
    readings = []

    def add(k, v):
        if v is not None:
            readings.append({"sensor_type": k, "value": round(v, 5)})

    add("temperature", read_temperature())
    add("distance", read_distance_cm())
    add("gas", 1 if mq.value() == 0 else 0)  # activo en bajo
    imu = read_imu()
    if imu:
        for k, v in imu.items():
            add(k, v)
    poll_gps()
    if gps["lat"] is not None and time.ticks_diff(time.ticks_ms(), gps["t"]) <= cfg.GPS_MAX_AGE_S * 1000:
        add("lat", gps["lat"])
        add("lon", gps["lon"])
        add("speed", gps["speed"])
    return readings


# ---------- bucle principal ----------
buffer = []  # lotes pendientes: {"t0": segundos, "readings": [...]}

while True:
    cycle_start = time.time()
    poll_gps()
    readings = collect()
    if readings:
        buffer.append({"t0": cycle_start, "readings": readings})
        if len(buffer) > cfg.MAX_BUFFER:
            buffer.pop(0)  # descarta el más viejo: no hay memoria infinita
            print("Buffer lleno: se descartó el lote más antiguo")

    if ensure_wifi():
        while buffer:
            if post(buffer[0]):
                buffer.pop(0)
            else:
                break  # sin servidor: se reintenta en el siguiente ciclo
    else:
        print("Sin Wi-Fi; lotes pendientes:", len(buffer))

    elapsed = time.time() - cycle_start
    time.sleep(max(0.2, cfg.SEND_INTERVAL_S - elapsed))
