# Análisis del avance y de la actividad

## 1. Avance de VECTRA hasta el 23-nov-2026

| Etapa | Qué hay | Evidencia |
|---|---|---|
| Propuesta | Concepto, arquitectura de 4 capas, alcance, enfoque de IA (detección de anomalías) | Documento IA |
| Pruebas unitarias (18-oct) | DS18B20, MPU6050 y NEO-6M con ESP32 + MicroPython + ThingSpeak (HTTP GET) | reporte_iot |
| Integración (3-nov) | 5 sensores, MQTT QoS 1 cada 5 s → ThingsBoard → PostgreSQL | reporte_sensores, avance 2º parcial |

Datos de la integración: 112 instantes en 13 min (19:30–19:43), 21 variables, temperatura 23.12–28.06 °C, distancia 6.79–34.39 cm, 0 detecciones de gas.

Pendiente declarado por el propio equipo: pruebas en vehículo, calibración, continuidad (hueco de 133.6 s por no tener cola local) y el modelo de IA con alertas.

## 2. Actividad (interpretación)

El documento *IoT Sensor Monitor* describe una práctica de Ingeniería de Software con la arquitectura ESP32 → FastAPI → Supabase → dashboard React, en Docker Compose. Es un README, no un enunciado: se interpretó como "implementar ese sistema para VECTRA". Si el profesor pidió algo distinto, ajustar este documento.

## 3. Brecha y cómo se cerró en este repo

| Tema | VECTRA antes | La actividad pide | En este repo |
|---|---|---|---|
| Transporte | MQTT → ThingsBoard | HTTP POST → FastAPI | `firmware/main.py` usa `urequests` |
| Tipos de sensor | Temp, distancia, gas, IMU 6 ejes, GPS | temperature, humidity, co2, distance | 12 tipos VECTRA con rangos físicos |
| Volumen | ~21 variables cada 5 s | 1 lectura por POST | Endpoint `/readings/batch` |
| Base de datos | PostgreSQL local | Supabase vía `DATABASE_URL` | `001_schema.sql` + tabla `trips` |
| Dashboard | ThingsBoard | React + Recharts | Tarjetas, 4 gráficas, GPS, logs, recorridos |
| Resiliencia | Sin cola local | Tampoco la trae | Buffer en RAM + `age_s` |

## 4. Decisiones de diseño

- **`age_s` en lugar de reloj en la ESP32:** el servidor calcula `recorded_at = ahora − age_s`, así los lotes reenviados tras una desconexión conservan su hora.
- **Validación por rangos físicos:** rechaza valores imposibles (p. ej. 999 °C) y los registra como `WARNING`.
- **Recorridos (`trips`):** agrupan lecturas por salida. Base para comparar recorridos y entrenar la línea base de comportamiento normal.
- **Simulador con anomalías:** inyecta vibración alta cada cierto tiempo para probar visualización y, después, la detección.

## 5. Riesgos

- La ESP32 no puede usar `localhost`; en el coche se necesita hotspot o backend desplegado.
- La API no tiene autenticación (prototipo).
- Supabase real y firmware en hardware sin probar.
- Gas digital ≠ calidad del aire; las coordenadas GPS tienen dispersión.

## 6. Siguientes pasos

1. Crear el proyecto Supabase, correr la migración y probar `/health`.
2. Cargar el firmware en la ESP32 y comparar con el simulador.
3. Montaje y recorridos en vehículo (usar `trips`).
4. Calibrar IMU y temperatura contra referencias.
5. Detección de anomalías sobre `readings` por recorrido (p. ej. Isolation Forest sobre ventanas de aceleración/giro) y alertas.
