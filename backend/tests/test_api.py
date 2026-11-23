"""Pruebas de la API. Requieren DATABASE_URL apuntando a una base con 001_schema.sql."""
import os
import sys
import uuid

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from app.main import app  # noqa: E402

pytestmark = pytest.mark.skipif(not os.getenv("DATABASE_URL"), reason="DATABASE_URL no configurada")
client = TestClient(app)


@pytest.fixture()
def dev():
    code = f"TEST-{uuid.uuid4().hex[:8]}"
    yield code
    # Limpieza: borra el dispositivo de prueba (cascada: lecturas y recorridos).
    import psycopg
    with psycopg.connect(os.environ["DATABASE_URL"], prepare_threshold=None) as conn:
        conn.execute("delete from devices where device_code = %s", (code,))
        conn.execute("delete from logs where message like %s", (f"%{code}%",))


def test_health():
    r = client.get("/health")
    assert r.status_code == 200 and r.json() == {"status": "ok", "database": True}


def test_single_reading_creates_device(dev):
    r = client.post("/api/v1/readings", json={"device_code": dev, "sensor_type": "temperature", "value": 25.7})
    assert r.status_code == 201
    devices = {d["device_code"]: d for d in client.get("/api/v1/devices").json()}
    assert devices[dev]["online"] is True
    logs = client.get("/api/v1/logs?limit=50").json()
    assert any(dev in l["message"] and l["level"] == "INFO" for l in logs)


def test_batch_and_summary(dev):
    body = {"device_code": dev, "readings": [
        {"sensor_type": "temperature", "value": 24.3},
        {"sensor_type": "acc_z", "value": 1.01},
        {"sensor_type": "gas", "value": 0},
    ]}
    assert client.post("/api/v1/readings/batch", json=body).json() == {"inserted": 3}
    s = client.get(f"/api/v1/summary?device_code={dev}").json()
    assert s["temperature"]["value"] == 24.3 and s["gas"]["value"] == 0


def test_out_of_range_rejected_and_logged(dev):
    r = client.post("/api/v1/readings", json={"device_code": dev, "sensor_type": "temperature", "value": 999})
    assert r.status_code == 422
    logs = client.get("/api/v1/logs?level=WARNING&limit=20").json()
    assert any(dev in l["message"] for l in logs)


def test_invalid_sensor_and_nan(dev):
    assert client.post("/api/v1/readings", json={"device_code": dev, "sensor_type": "foo", "value": 1}).status_code == 422
    assert client.post("/api/v1/readings", content='{"device_code":"%s","sensor_type":"temperature","value":NaN}' % dev,
                       headers={"Content-Type": "application/json"}).status_code == 422


def test_batch_is_atomic_on_invalid_item(dev):
    body = {"device_code": dev, "readings": [
        {"sensor_type": "temperature", "value": 20}, {"sensor_type": "distance", "value": -5}]}
    assert client.post("/api/v1/readings/batch", json=body).status_code == 422
    assert client.get(f"/api/v1/readings?device_code={dev}").json() == []


def test_age_s_backdates_reading(dev):
    client.post("/api/v1/readings/batch", json={"device_code": dev, "age_s": 3600,
                "readings": [{"sensor_type": "distance", "value": 12}]})
    row = client.get(f"/api/v1/readings?device_code={dev}").json()[0]
    from datetime import datetime, timezone
    age = (datetime.now(timezone.utc) - datetime.fromisoformat(row["recorded_at"])).total_seconds()
    assert 3590 < age < 3700


def test_series_ascending(dev):
    for v in (1.0, 2.0, 3.0):
        client.post("/api/v1/readings", json={"device_code": dev, "sensor_type": "acc_x", "value": v})
    s = client.get(f"/api/v1/series?types=acc_x&device_code={dev}&limit=2").json()
    assert [p["v"] for p in s["acc_x"]] == [2.0, 3.0]


def test_trip_lifecycle_attaches_readings(dev):
    t = client.post("/api/v1/trips", json={"device_code": dev, "name": "prueba"}).json()
    client.post("/api/v1/readings", json={"device_code": dev, "sensor_type": "speed", "value": 30})
    assert client.get(f"/api/v1/readings?device_code={dev}").json()[0]["trip_id"] == t["id"]
    assert client.post(f"/api/v1/trips/{t['id']}/end").status_code == 200
    assert client.post(f"/api/v1/trips/{t['id']}/end").status_code == 404
    client.post("/api/v1/readings", json={"device_code": dev, "sensor_type": "speed", "value": 31})
    assert client.get(f"/api/v1/readings?device_code={dev}").json()[0]["trip_id"] is None
    trips = [x for x in client.get("/api/v1/trips").json() if x["id"] == t["id"]]
    assert trips[0]["readings"] == 1
