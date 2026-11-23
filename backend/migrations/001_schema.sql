-- VECTRA IoT Monitor · esquema inicial (Supabase / PostgreSQL)
-- Ejecutar completo en Supabase > SQL Editor.

create table if not exists devices (
    id          serial primary key,
    device_code text not null unique,
    created_at  timestamptz not null default now(),
    last_seen   timestamptz
);

-- Un recorrido (trip) agrupa lecturas de un dispositivo entre dos momentos.
create table if not exists trips (
    id         serial primary key,
    device_id  integer not null references devices(id) on delete cascade,
    name       text,
    started_at timestamptz not null default now(),
    ended_at   timestamptz
);

create table if not exists readings (
    id          bigserial primary key,
    device_id   integer not null references devices(id) on delete cascade,
    trip_id     integer references trips(id) on delete set null,
    sensor_type text not null,
    value       double precision not null,
    recorded_at timestamptz not null default now()
);

create table if not exists logs (
    id         bigserial primary key,
    level      text not null check (level in ('INFO', 'WARNING', 'ERROR')),
    message    text not null,
    created_at timestamptz not null default now()
);

create index if not exists idx_readings_sensor_time on readings (sensor_type, recorded_at desc);
create index if not exists idx_readings_device_time on readings (device_id, recorded_at desc);
create index if not exists idx_readings_trip on readings (trip_id);
create index if not exists idx_trips_device_open on trips (device_id) where ended_at is null;
create index if not exists idx_logs_created on logs (created_at desc);
