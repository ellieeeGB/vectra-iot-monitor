"""VECTRA IoT Monitor · API FastAPI.

Recibe lecturas de la ESP32 (o del simulador), las valida, las guarda en
PostgreSQL (Supabase) y las expone al dashboard.
"""
import logging
import os
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Literal, Optional

import psycopg
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from psycopg.rows import dict_row
from pydantic import BaseModel, Field

log = logging.getLogger("vectra")
logging.basicConfig(level=logging.INFO)

DATABASE_URL = os.getenv("DATABASE_URL", "")
CORS_ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",") if o.strip()]
ONLINE_SECONDS = int(os.getenv("ONLINE_SECONDS", "15"))

SensorType = Literal[
    "temperature", "distance", "gas",
    "acc_x", "acc_y", "acc_z",
    "gyro_x", "gyro_y", "gyro_z",
    "lat", "lon", "speed",
]

# Rangos físicos plausibles (min, max). Fuera de rango => 422 y log WARNING.
RANGES = {
    "temperature": (-55.0, 125.0),   # DS18B20
    "distance": (0.0, 400.0),        # HC-SR04, cm
    "gas": (0.0, 1.0),               # salida digital: 1 = detección
    "acc_x": (-16.0, 16.0), "acc_y": (-16.0, 16.0), "acc_z": (-16.0, 16.0),  # g
    "gyro_x": (-2000.0, 2000.0), "gyro_y": (-2000.0, 2000.0), "gyro_z": (-2000.0, 2000.0),  # °/s
    "lat": (-90.0, 90.0), "lon": (-180.0, 180.0),
    "speed": (0.0, 400.0),           # km/h
}

DEVICE_CODE = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")
Value = Field(allow_inf_nan=False)


class ReadingIn(BaseModel):
    device_code: str = DEVICE_CODE
    sensor_type: SensorType
    value: float = Value


class ReadingItem(BaseModel):
    sensor_type: SensorType
    value: float = Value


class BatchIn(BaseModel):
    device_code: str = DEVICE_CODE
    # Segundos transcurridos desde que se midió. Permite reenviar lecturas
    # guardadas sin conexión sin necesitar reloj en la ESP32.
    age_s: float = Field(default=0, ge=0, le=86400)
    readings: list[ReadingItem] = Field(min_length=1, max_length=50)


class TripIn(BaseModel):
    device_code: str = DEVICE_CODE
    name: Optional[str] = Field(default=None, max_length=80)


app = FastAPI(title="VECTRA IoT Monitor", version="1.0.0")
app.add_middleware(
    CORSMiddleware, allow_origins=CORS_ORIGINS, allow_methods=["*"], allow_headers=["*"]
)


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError):
    # Se omite "input"/"ctx": pueden contener NaN/inf y no son serializables a JSON.
    errors = [{"loc": e["loc"], "msg": e["msg"], "type": e["type"]} for e in exc.errors()]
    return JSONResponse(status_code=422, content={"detail": errors})


@contextmanager
def db():
    # prepare_threshold=None: compatible con el pooler de Supabase (modo transacción).
    with psycopg.connect(
        DATABASE_URL, row_factory=dict_row, connect_timeout=5, prepare_threshold=None
    ) as conn:
        yield conn


def write_log(conn, level: str, message: str) -> None:
    conn.execute("insert into logs (level, message) values (%s, %s)", (level, message))


def check_range(sensor_type: str, value: float) -> Optional[str]:
    lo, hi = RANGES[sensor_type]
    if not lo <= value <= hi:
        return f"{sensor_type}={value} fuera de rango [{lo}, {hi}]"
    return None


def reject(device_code: str, problems: list[str]):
    """Registra el rechazo en logs (best effort) y responde 422."""
    detail = "; ".join(problems)
    try:
        with db() as conn:
            write_log(conn, "WARNING", f"Lectura rechazada de {device_code}: {detail}")
    except Exception:  # la validación no debe depender de la base
        log.warning("Lectura rechazada de %s: %s", device_code, detail)
    raise HTTPException(status_code=422, detail=detail)


def touch_device(conn, device_code: str) -> int:
    row = conn.execute(
        """insert into devices (device_code, last_seen) values (%s, now())
           on conflict (device_code) do update set last_seen = now()
           returning id, (xmax = 0) as created""",
        (device_code,),
    ).fetchone()
    if row["created"]:
        write_log(conn, "INFO", f"Dispositivo nuevo registrado: {device_code}")
    return row["id"]


def insert_readings(device_code: str, items: list[ReadingItem], age_s: float = 0) -> int:
    problems = [p for i in items if (p := check_range(i.sensor_type, i.value))]
    if problems:
        reject(device_code, problems)
    recorded_at = datetime.now(timezone.utc) - timedelta(seconds=age_s)
    try:
        with db() as conn:
            device_id = touch_device(conn, device_code)
            trip = conn.execute(
                "select id from trips where device_id=%s and ended_at is null "
                "order by started_at desc limit 1",
                (device_id,),
            ).fetchone()
            trip_id = trip["id"] if trip else None
            with conn.cursor() as cur:
                cur.executemany(
                    "insert into readings (device_id, trip_id, sensor_type, value, recorded_at) "
                    "values (%s, %s, %s, %s, %s)",
                    [(device_id, trip_id, i.sensor_type, i.value, recorded_at) for i in items],
                )
    except psycopg.Error as exc:
        log.error("Error de base de datos: %s", exc)
        raise HTTPException(status_code=503, detail="Base de datos no disponible")
    return len(items)


def db_error(exc: Exception):
    log.error("Error de base de datos: %s", exc)
    raise HTTPException(status_code=503, detail="Base de datos no disponible")


@app.get("/health")
def health():
    try:
        with db() as conn:
            conn.execute("select 1")
        return {"status": "ok", "database": True}
    except Exception as exc:
        log.error("health: %s", exc)
        return {"status": "degraded", "database": False}


@app.post("/api/v1/readings", status_code=201)
def post_reading(r: ReadingIn):
    n = insert_readings(r.device_code, [ReadingItem(sensor_type=r.sensor_type, value=r.value)])
    return {"inserted": n}


@app.post("/api/v1/readings/batch", status_code=201)
def post_batch(b: BatchIn):
    return {"inserted": insert_readings(b.device_code, b.readings, b.age_s)}


@app.get("/api/v1/readings")
def get_readings(
    limit: int = Query(20, ge=1, le=500),
    device_code: Optional[str] = None,
    sensor_type: Optional[SensorType] = None,
):
    try:
        with db() as conn:
            return conn.execute(
                """select r.id, d.device_code, r.trip_id, r.sensor_type, r.value, r.recorded_at
                   from readings r join devices d on d.id = r.device_id
                   where (%(dc)s::text is null or d.device_code = %(dc)s)
                     and (%(st)s::text is null or r.sensor_type = %(st)s)
                   order by r.recorded_at desc, r.id desc limit %(limit)s""",
                {"dc": device_code, "st": sensor_type, "limit": limit},
            ).fetchall()
    except psycopg.Error as exc:
        db_error(exc)


@app.get("/api/v1/series")
def get_series(
    types: str = Query(..., description="Tipos separados por coma, p. ej. acc_x,acc_y,acc_z"),
    limit: int = Query(60, ge=1, le=500),
    device_code: Optional[str] = None,
):
    wanted = [t for t in types.split(",") if t]
    unknown = [t for t in wanted if t not in RANGES]
    if not wanted or unknown:
        raise HTTPException(status_code=422, detail=f"Tipos inválidos: {unknown or types}")
    try:
        with db() as conn:
            rows = conn.execute(
                """select sensor_type, value, recorded_at from (
                       select r.sensor_type, r.value, r.recorded_at,
                              row_number() over (partition by r.sensor_type
                                                 order by r.recorded_at desc, r.id desc) as rn
                       from readings r join devices d on d.id = r.device_id
                       where r.sensor_type = any(%(types)s)
                         and (%(dc)s::text is null or d.device_code = %(dc)s)
                   ) x where rn <= %(limit)s order by recorded_at asc""",
                {"types": wanted, "dc": device_code, "limit": limit},
            ).fetchall()
    except psycopg.Error as exc:
        db_error(exc)
    out: dict[str, list] = {t: [] for t in wanted}
    for r in rows:
        out[r["sensor_type"]].append({"t": r["recorded_at"], "v": r["value"]})
    return out


@app.get("/api/v1/summary")
def get_summary(device_code: Optional[str] = None):
    """Última lectura de cada sensor."""
    try:
        with db() as conn:
            rows = conn.execute(
                """select distinct on (r.sensor_type) r.sensor_type, r.value, r.recorded_at
                   from readings r join devices d on d.id = r.device_id
                   where (%(dc)s::text is null or d.device_code = %(dc)s)
                   order by r.sensor_type, r.recorded_at desc, r.id desc""",
                {"dc": device_code},
            ).fetchall()
    except psycopg.Error as exc:
        db_error(exc)
    return {r["sensor_type"]: {"value": r["value"], "recorded_at": r["recorded_at"]} for r in rows}


@app.get("/api/v1/devices")
def get_devices():
    try:
        with db() as conn:
            rows = conn.execute(
                """select d.device_code, d.created_at, d.last_seen,
                          extract(epoch from (now() - d.last_seen)) as seconds_since,
                          (select t.id from trips t where t.device_id = d.id and t.ended_at is null
                           order by t.started_at desc limit 1) as open_trip_id
                   from devices d order by d.device_code"""
            ).fetchall()
    except psycopg.Error as exc:
        db_error(exc)
    for r in rows:
        s = r["seconds_since"]
        r["online"] = s is not None and float(s) <= ONLINE_SECONDS
        r["seconds_since"] = None if s is None else round(float(s), 1)
    return rows


@app.get("/api/v1/logs")
def get_logs(limit: int = Query(20, ge=1, le=200), level: Optional[Literal["INFO", "WARNING", "ERROR"]] = None):
    try:
        with db() as conn:
            return conn.execute(
                """select id, level, message, created_at from logs
                   where (%(lv)s::text is null or level = %(lv)s)
                   order by created_at desc, id desc limit %(limit)s""",
                {"lv": level, "limit": limit},
            ).fetchall()
    except psycopg.Error as exc:
        db_error(exc)


@app.get("/api/v1/trips")
def get_trips(limit: int = Query(20, ge=1, le=200)):
    try:
        with db() as conn:
            return conn.execute(
                """select t.id, d.device_code, t.name, t.started_at, t.ended_at,
                          (select count(*) from readings r where r.trip_id = t.id) as readings
                   from trips t join devices d on d.id = t.device_id
                   order by t.started_at desc limit %s""",
                (limit,),
            ).fetchall()
    except psycopg.Error as exc:
        db_error(exc)


@app.post("/api/v1/trips", status_code=201)
def start_trip(t: TripIn):
    """Inicia un recorrido; cierra el que siguiera abierto en ese dispositivo."""
    try:
        with db() as conn:
            device_id = touch_device(conn, t.device_code)
            conn.execute(
                "update trips set ended_at = now() where device_id = %s and ended_at is null",
                (device_id,),
            )
            row = conn.execute(
                "insert into trips (device_id, name) values (%s, %s) returning id, started_at",
                (device_id, t.name),
            ).fetchone()
            write_log(conn, "INFO", f"Recorrido {row['id']} iniciado en {t.device_code}")
            return row
    except psycopg.Error as exc:
        db_error(exc)


@app.post("/api/v1/trips/{trip_id}/end")
def end_trip(trip_id: int):
    try:
        with db() as conn:
            row = conn.execute(
                "update trips set ended_at = now() where id = %s and ended_at is null "
                "returning id, ended_at",
                (trip_id,),
            ).fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Recorrido no encontrado o ya cerrado")
            write_log(conn, "INFO", f"Recorrido {trip_id} finalizado")
            return row
    except psycopg.Error as exc:
        db_error(exc)
