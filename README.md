# VECTRA IoT Monitor

Plataforma para recibir, almacenar y visualizar la telemetría de VECTRA (monitoreo del comportamiento de un vehículo con ESP32 y sensores). Práctica de Internet de las Cosas / Ingeniería de Software, UPQ.

Equipo: Patricia Botello · Elliot González · Diego Almaraz · Ignacio Rodríguez

## Arquitectura

```
ESP32 (MicroPython) o Simulador ──HTTP POST──▶ FastAPI ──▶ Supabase PostgreSQL ◀── FastAPI ◀── Dashboard React
```

| Carpeta | Contenido |
|---|---|
| `backend/` | API FastAPI, migración SQL, pruebas |
| `frontend/` | Dashboard React 18 + Vite + Recharts |
| `simulator/` | Generador de lecturas ficticias (incluye episodios de vibración anómala) |
| `firmware/` | Código MicroPython para la ESP32 con los 5 sensores de VECTRA |
| `docs/` | Análisis del avance y de la actividad |

## Sensores soportados (`sensor_type`)

| Tipo | Fuente | Unidad | Rango aceptado |
|---|---|---|---|
| `temperature` | DS18B20 | °C | -55 a 125 |
| `distance` | HC-SR04 | cm | 0 a 400 |
| `gas` | Módulo MQ (salida digital) | 0/1 | 0 a 1 |
| `acc_x`, `acc_y`, `acc_z` | IMU MPU6500/6050 | g | -16 a 16 |
| `gyro_x`, `gyro_y`, `gyro_z` | IMU | °/s | -2000 a 2000 |
| `lat`, `lon` | GPS NEO-6M | grados | ±90 / ±180 |
| `speed` | GPS NEO-6M | km/h | 0 a 400 |

Fuera de rango, la API responde 422 y registra un `WARNING` en los logs.

## Puesta en marcha

Requisitos: Docker + Docker Compose y un proyecto de Supabase.

1. En Supabase: *Project Settings → Database* y copia la cadena de conexión.
2. En Supabase *SQL Editor*, ejecuta `backend/migrations/001_schema.sql`.
3. `cp .env.example .env` y pon tu `DATABASE_URL`.
4. Levanta todo:

```bash
docker compose up -d --build                 # backend + dashboard
docker compose --profile sim up -d --build   # además, con simulador (datos ficticios)
```

- Dashboard: http://localhost:5173
- Swagger: http://localhost:8000/docs
- Health: http://localhost:8000/health (`database: false` = revisa `DATABASE_URL` y que corriste la migración)

Para detener el simulador y usar la ESP32 real: `docker compose stop simulator`.

## API

| Método | Ruta | Uso |
|---|---|---|
| POST | `/api/v1/readings` | Una lectura `{device_code, sensor_type, value}` |
| POST | `/api/v1/readings/batch` | Lote `{device_code, age_s?, readings:[{sensor_type, value}]}` (hasta 50) |
| GET | `/api/v1/readings` | Últimas lecturas (`limit`, `device_code`, `sensor_type`) |
| GET | `/api/v1/series` | Series para gráficas (`types=acc_x,acc_y`, `limit`) |
| GET | `/api/v1/summary` | Última lectura de cada sensor |
| GET | `/api/v1/devices` | Dispositivos con `online` (lectura en los últimos 15 s) |
| POST | `/api/v1/trips` | Inicia un recorrido (cierra el abierto del dispositivo) |
| POST | `/api/v1/trips/{id}/end` | Termina un recorrido |
| GET | `/api/v1/trips` | Recorridos con número de lecturas |
| GET | `/api/v1/logs` | Logs `INFO` / `WARNING` / `ERROR` |

Los dispositivos se crean solos con su primera lectura. Mientras un recorrido está abierto, las lecturas de ese dispositivo se asocian a él.

Ejemplos:

```bash
curl -X POST localhost:8000/api/v1/readings -H "Content-Type: application/json" \
  -d '{"device_code":"ESP32-PRUEBA-01","sensor_type":"temperature","value":25.7}'

curl -X POST localhost:8000/api/v1/readings/batch -H "Content-Type: application/json" \
  -d '{"device_code":"ESP32-PRUEBA-01","readings":[{"sensor_type":"acc_z","value":1.01},{"sensor_type":"gas","value":0}]}'
```

`age_s` (segundos desde que se midió) permite reenviar lecturas guardadas sin conexión con su hora correcta, sin que la ESP32 tenga reloj.

## ESP32 real

Ver [`firmware/README.md`](firmware/README.md). Puntos clave: la ESP32 no puede usar `localhost`, necesita la IP LAN del equipo con FastAPI; en un vehículo, usa el hotspot del celular.

## Pruebas del backend

```bash
cd backend
pip install -r requirements-dev.txt
DATABASE_URL=postgresql://... pytest -q tests
```

Las pruebas crean dispositivos `TEST-*` y los borran al terminar, pero **mejor úsalas contra una base de desarrollo**, no la de datos reales.

## Seguridad

- `.env` y `firmware/config.py` están en `.gitignore`. Nunca subas `DATABASE_URL` ni contraseñas de Wi-Fi.
- La API no tiene autenticación: es un prototipo académico. Antes de exponerla a internet, agrega una API key o JWT y HTTPS.

## Qué está y qué no (estado honesto)

**Verificado** (backend y dashboard, contra un PostgreSQL local):
- 9 pruebas de la API pasan.
- Simulador → API → base → dashboard, con gráficas, GPS, logs y estado ONLINE/OFFLINE.
- `docker compose config` valida.

**No verificado:**
- Construcción de imágenes Docker.
- Conexión a un proyecto Supabase real.
- El firmware en una ESP32 (el código no se ejecutó en hardware; se escribió con los pines y conexiones del reporte ThingsLab).

**Pendiente del proyecto VECTRA:**
- Pruebas dentro de un vehículo.
- Calibración contra referencias.
- Modelo de detección de anomalías y alertas (el simulador ya inyecta anomalías para probarlo).
- El buffer sin conexión del firmware vive en RAM y se pierde si la placa se reinicia.

Versión: `v1-unidad-iot`.
