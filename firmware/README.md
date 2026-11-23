# Firmware ESP32 (MicroPython)

Envía lotes JSON a `POST /api/v1/readings/batch` cada 5 s con temperatura, distancia, gas (digital), IMU de 6 ejes y GPS.

## Conexiones (según el reporte ThingsLab)

| Módulo | Pines |
|---|---|
| DS18B20 | OneWire GPIO4, pull-up 4.7 kΩ a 3.3 V |
| HC-SR04 | Trig GPIO5; Echo GPIO18 **con divisor de tensión** |
| IMU MPU6500/6050 | I²C SDA GPIO22, SCL GPIO21, dirección 0x68 |
| Módulo MQ | DO GPIO25 **con divisor**; activo en nivel bajo |
| GPS NEO-6M | TX del GPS → GPIO16 (UART2, 9600 baudios) |

Todos los módulos comparten GND. Los pines se pueden cambiar en `config.py`.

## Instalación

1. Flashea MicroPython en la ESP32.
2. Copia `config.example.py` a `config.py` y llena Wi-Fi, `API_URL` (IP LAN del equipo con FastAPI) y `DEVICE_CODE`.
3. Sube `main.py` y `config.py` a la placa (Thonny, `mpremote` o `ampy`):

```bash
mpremote cp main.py :main.py + cp config.py :config.py + reset
```

4. Revisa en el dashboard que el dispositivo aparezca ONLINE.

## Comportamiento

- Valores no válidos (sensor sin respuesta, GPS sin fix o con más de 5 s de antigüedad) **se omiten**; no se rellenan con ceros.
- Sin Wi-Fi o sin servidor, los lotes se guardan en RAM (máx. `MAX_BUFFER`) y se reenvían al reconectar con `age_s`, así conservan su hora.
- Si el buffer se llena, se descarta el lote más antiguo.
- La salida del MQ es digital: indica si pasó el umbral, no concentración en ppm.

## Límites

- El buffer está en RAM: se pierde si la placa se reinicia.
- Este código no se ha ejecutado en hardware; ajusta pines, escala de la IMU y parseo NMEA si tu módulo difiere.
- La IMU se lee en ±2 g y ±250 °/s (valores por defecto). Para vibración fuerte de vehículo, considera ±4 g u ±8 g y ajusta el registro 0x1C y las escalas (16384 / 131) en `read_imu`.
