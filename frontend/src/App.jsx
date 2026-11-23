import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Scatter, ScatterChart,
  Tooltip, XAxis, YAxis,
} from "recharts";

const API = (import.meta.env.VITE_API_URL || "http://localhost:8000").replace(/\/$/, "");
const REFRESH_MS = 3000;
const POINTS = 60;
const ALL_TYPES = [
  "temperature", "distance", "acc_x", "acc_y", "acc_z", "gyro_x", "gyro_y", "gyro_z", "lat", "lon",
].join(",");

async function api(path, options) {
  const r = await fetch(API + path, options);
  if (!r.ok) throw new Error(`${r.status} ${path}`);
  return r.json();
}

const fmt = (v, d = 2) => (v === undefined || v === null ? "—" : Number(v).toFixed(d));
const time = (iso) => new Date(iso).toLocaleTimeString("es-MX");

// Une varias series (mismo timestamp por lote) en filas para Recharts.
function merge(series, keys) {
  const rows = new Map();
  keys.forEach((k) =>
    (series[k] || []).forEach((p) => {
      const row = rows.get(p.t) || { t: p.t, label: time(p.t) };
      row[k] = p.v;
      rows.set(p.t, row);
    })
  );
  return [...rows.values()].sort((a, b) => (a.t < b.t ? -1 : 1));
}

function Card({ title, value, unit, note, tone }) {
  return (
    <div className={`card ${tone || ""}`}>
      <div className="card-title">{title}</div>
      <div className="card-value">
        {value}
        {unit && <span className="unit"> {unit}</span>}
      </div>
      {note && <div className="card-note">{note}</div>}
    </div>
  );
}

function Chart({ title, data, lines, unit }) {
  return (
    <section className="panel">
      <h2>{title}</h2>
      {data.length === 0 ? (
        <p className="empty">Sin datos todavía.</p>
      ) : (
        <ResponsiveContainer width="100%" height={220}>
          <LineChart data={data} margin={{ top: 8, right: 12, left: -8, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
            <XAxis dataKey="label" tick={{ fontSize: 11 }} minTickGap={32} />
            <YAxis tick={{ fontSize: 11 }} unit={unit ? ` ${unit}` : ""} width={64} domain={["auto", "auto"]} />
            <Tooltip />
            {lines.length > 1 && <Legend />}
            {lines.map((l) => (
              <Line key={l.key} type="monotone" dataKey={l.key} name={l.name} stroke={l.color}
                dot={false} strokeWidth={2} isAnimationActive={false} connectNulls />
            ))}
          </LineChart>
        </ResponsiveContainer>
      )}
    </section>
  );
}

export default function App() {
  const [devices, setDevices] = useState([]);
  const [device, setDevice] = useState("");
  const [summary, setSummary] = useState({});
  const [series, setSeries] = useState({});
  const [readings, setReadings] = useState([]);
  const [logs, setLogs] = useState([]);
  const [trips, setTrips] = useState([]);
  const [error, setError] = useState(null);
  const [updated, setUpdated] = useState(null);

  const load = useCallback(async () => {
    try {
      const devs = await api("/api/v1/devices");
      setDevices(devs);
      const current = device || devs[0]?.device_code || "";
      if (!device && current) setDevice(current);
      const q = current ? `&device_code=${encodeURIComponent(current)}` : "";
      const [sum, ser, rd, lg, tr] = await Promise.all([
        api(`/api/v1/summary?${q.slice(1)}`),
        api(`/api/v1/series?types=${ALL_TYPES}&limit=${POINTS}${q}`),
        api(`/api/v1/readings?limit=12${q}`),
        api("/api/v1/logs?limit=10"),
        api("/api/v1/trips?limit=5"),
      ]);
      setSummary(sum); setSeries(ser); setReadings(rd); setLogs(lg); setTrips(tr);
      setError(null); setUpdated(new Date());
    } catch (e) {
      setError(e.message);
    }
  }, [device]);

  useEffect(() => {
    load();
    const id = setInterval(load, REFRESH_MS);
    return () => clearInterval(id);
  }, [load]);

  const dev = devices.find((d) => d.device_code === device);
  const s = (k) => summary[k]?.value;
  const magnitude = ["acc_x", "acc_y", "acc_z"].every((k) => s(k) !== undefined)
    ? Math.sqrt(s("acc_x") ** 2 + s("acc_y") ** 2 + s("acc_z") ** 2) : undefined;

  const tempData = useMemo(() => merge(series, ["temperature"]), [series]);
  const distData = useMemo(() => merge(series, ["distance"]), [series]);
  const accData = useMemo(() => merge(series, ["acc_x", "acc_y", "acc_z"]), [series]);
  const gyroData = useMemo(() => merge(series, ["gyro_x", "gyro_y", "gyro_z"]), [series]);
  const gps = useMemo(
    () => merge(series, ["lat", "lon"]).filter((r) => r.lat !== undefined && r.lon !== undefined),
    [series]
  );

  async function startTrip() {
    const name = window.prompt("Nombre del recorrido (opcional)") ?? null;
    await api("/api/v1/trips", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ device_code: device, name: name || null }),
    });
    load();
  }
  async function endTrip() {
    await api(`/api/v1/trips/${dev.open_trip_id}/end`, { method: "POST" });
    load();
  }

  return (
    <div className="app">
      <header>
        <div>
          <h1>VECTRA</h1>
          <p className="sub">Monitor IoT · telemetría del vehículo</p>
        </div>
        <div className="header-right">
          <select value={device} onChange={(e) => setDevice(e.target.value)} aria-label="Dispositivo">
            {devices.length === 0 && <option value="">Sin dispositivos</option>}
            {devices.map((d) => <option key={d.device_code} value={d.device_code}>{d.device_code}</option>)}
          </select>
          <span className={`badge ${dev?.online ? "on" : "off"}`}>{dev?.online ? "ONLINE" : "OFFLINE"}</span>
          {dev && (dev.open_trip_id
            ? <button onClick={endTrip}>Terminar recorrido #{dev.open_trip_id}</button>
            : <button onClick={startTrip}>Iniciar recorrido</button>)}
        </div>
      </header>

      {error && <div className="alert">No se pudo contactar la API ({error}). Reintentando…</div>}
      {!error && devices.length === 0 && (
        <div className="alert info">Aún no hay dispositivos. Enciende el simulador o la ESP32.</div>
      )}

      <div className="cards">
        <Card title="Temperatura" value={fmt(s("temperature"), 1)} unit="°C" />
        <Card title="Distancia" value={fmt(s("distance"), 1)} unit="cm" />
        <Card title="Aceleración |a|" value={fmt(magnitude, 3)} unit="g" note="≈1 g en reposo" />
        <Card title="Velocidad (GPS)" value={fmt(s("speed"), 1)} unit="km/h" />
        <Card title="Gas (digital)" value={s("gas") === undefined ? "—" : s("gas") ? "DETECTADO" : "Sin detección"}
          tone={s("gas") ? "danger" : ""} note="No mide ppm" />
        <Card title="Última lectura" value={dev?.last_seen ? time(dev.last_seen) : "—"}
          note={updated ? `Panel actualizado ${updated.toLocaleTimeString("es-MX")}` : ""} />
      </div>

      <div className="grid">
        <Chart title="Temperatura (°C)" data={tempData} unit="°C"
          lines={[{ key: "temperature", name: "Temperatura", color: "#dc2626" }]} />
        <Chart title="Distancia (cm)" data={distData} unit="cm"
          lines={[{ key: "distance", name: "Distancia", color: "#2563eb" }]} />
        <Chart title="Aceleración por eje (g)" data={accData} unit="g"
          lines={[{ key: "acc_x", name: "X", color: "#dc2626" }, { key: "acc_y", name: "Y", color: "#16a34a" },
                  { key: "acc_z", name: "Z", color: "#2563eb" }]} />
        <Chart title="Velocidad angular (°/s)" data={gyroData} unit="°/s"
          lines={[{ key: "gyro_x", name: "X", color: "#dc2626" }, { key: "gyro_y", name: "Y", color: "#16a34a" },
                  { key: "gyro_z", name: "Z", color: "#2563eb" }]} />

        <section className="panel">
          <h2>Trayecto GPS</h2>
          {gps.length === 0 ? <p className="empty">Sin fix GPS todavía.</p> : (
            <>
              <ResponsiveContainer width="100%" height={220}>
                <ScatterChart margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                  <XAxis type="number" dataKey="lon" name="Lon" domain={["auto", "auto"]} tick={{ fontSize: 11 }} tickFormatter={(v) => v.toFixed(4)} />
                  <YAxis type="number" dataKey="lat" name="Lat" domain={["auto", "auto"]} tick={{ fontSize: 11 }} tickFormatter={(v) => v.toFixed(4)} width={64} />
                  <Tooltip />
                  <Scatter data={gps} fill="#7c3aed" line isAnimationActive={false} />
                </ScatterChart>
              </ResponsiveContainer>
              <a className="link" target="_blank" rel="noreferrer"
                href={`https://www.google.com/maps?q=${gps[gps.length - 1].lat},${gps[gps.length - 1].lon}`}>
                Ver última posición en Google Maps
              </a>
              <p className="note">Las coordenadas tienen dispersión; un cambio pequeño no prueba desplazamiento real.</p>
            </>
          )}
        </section>

        <section className="panel">
          <h2>Recorridos recientes</h2>
          {trips.length === 0 ? <p className="empty">Sin recorridos.</p> : (
            <table><thead><tr><th>#</th><th>Dispositivo</th><th>Nombre</th><th>Inicio</th><th>Estado</th><th>Lecturas</th></tr></thead>
              <tbody>{trips.map((t) => (
                <tr key={t.id}><td>{t.id}</td><td>{t.device_code}</td><td>{t.name || "—"}</td>
                  <td>{new Date(t.started_at).toLocaleString("es-MX")}</td>
                  <td>{t.ended_at ? "Terminado" : "En curso"}</td><td>{t.readings}</td></tr>
              ))}</tbody></table>
          )}
        </section>
      </div>

      <div className="grid">
        <section className="panel">
          <h2>Últimas lecturas</h2>
          <table><thead><tr><th>Hora</th><th>Sensor</th><th>Valor</th></tr></thead>
            <tbody>{readings.map((r) => (
              <tr key={r.id}><td>{time(r.recorded_at)}</td><td>{r.sensor_type}</td><td>{fmt(r.value, 3)}</td></tr>
            ))}</tbody></table>
        </section>
        <section className="panel">
          <h2>Logs del sistema</h2>
          <table><thead><tr><th>Hora</th><th>Nivel</th><th>Mensaje</th></tr></thead>
            <tbody>{logs.map((l) => (
              <tr key={l.id}><td>{time(l.created_at)}</td><td><span className={`lvl ${l.level}`}>{l.level}</span></td><td>{l.message}</td></tr>
            ))}</tbody></table>
        </section>
      </div>
    </div>
  );
}
