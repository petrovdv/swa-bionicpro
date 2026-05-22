CREATE DATABASE IF NOT EXISTS cdc_staging;
CREATE DATABASE IF NOT EXISTS bionic_analytics;

-- 1. Kafka Engine Table (источник событий CDC)
CREATE TABLE IF NOT EXISTS cdc_staging.users_cdc (
    id UInt32,
    full_name String,
    email String,
    age Nullable(UInt16),
    registration_date Nullable(String),
    __deleted Nullable(String),
    op Nullable(String),
    ts_ms Nullable(UInt64)
) ENGINE = Kafka
SETTINGS
    kafka_broker_list = 'kafka:29092',
    kafka_topic_list = 'crm.public.users',
    kafka_group_name = 'clickhouse_crm_users_v2',
    kafka_format = 'JSONEachRow',
    kafka_max_block_size = 1048576;

-- 2. Целевая таблица (ReplacingMergeTree)
CREATE TABLE IF NOT EXISTS bionic_analytics.crm_users_cdc (
    user_id UInt32,
    full_name String,
    email String,
    age Nullable(UInt16),
    registration_date Nullable(Date),
    _version UInt64,
    _deleted UInt8,
    _updated_at DateTime
) ENGINE = ReplacingMergeTree(_version)
ORDER BY user_id
SETTINGS index_granularity = 8192;

-- 3. Materialized View (парсинг и маппинг)
CREATE MATERIALIZED VIEW IF NOT EXISTS cdc_staging.users_cdc_mv
TO bionic_analytics.crm_users_cdc
AS SELECT
    toUInt32(id) AS user_id,
    nullIf(toString(full_name), '') AS full_name,
    nullIf(toString(email), '') AS email,
    toUInt16OrNull(toString(age)) AS age,

    if(
        toUInt32OrNull(toString(registration_date)) > 10000
        AND toUInt32OrNull(toString(registration_date)) < 30000,
        toDate(toUInt32(registration_date)),
        toDateOrNull(toString(registration_date))
    ) AS registration_date,

    toUInt64(now()) AS _version,

    if(__deleted = 'true', 1, 0) AS _deleted,

    now() AS _updated_at
FROM cdc_staging.users_cdc;

-- 4. VIEW для удобного чтения (без FINAL)
CREATE VIEW IF NOT EXISTS bionic_analytics.crm_users AS
SELECT
    user_id, full_name, email, age, registration_date
FROM bionic_analytics.crm_users_cdc
WHERE _deleted = 0;

-- 5. Таблица телеметрии
CREATE TABLE IF NOT EXISTS bionic_analytics.prosthetic_telemetry
(
    user_id       UInt32,
    device_id     String,
    step_count    UInt32,
    battery_level Float64,
    usage_hours   Float64,
    recorded_at   DateTime
) ENGINE = MergeTree()
ORDER BY (user_id, recorded_at);

-- 6. CDC-витрина
CREATE VIEW IF NOT EXISTS bionic_analytics.user_telemetry_mart_cdc AS
SELECT
    c.user_id,
    c.full_name,
    c.email,
    c.age,
    c.registration_date,
    count(t.device_id) AS device_count,
    sum(t.step_count) AS total_steps,
    avg(t.battery_level) AS avg_battery_level,
    sum(t.usage_hours) AS total_usage_hours,
    max(t.recorded_at) AS last_active_date,
    count(t.device_id) > 0 AS has_telemetry,
    today() AS report_date
FROM bionic_analytics.crm_users AS c
LEFT JOIN bionic_analytics.prosthetic_telemetry AS t
    ON c.user_id = t.user_id
GROUP BY c.user_id, c.full_name, c.email, c.age, c.registration_date;

-- 7. Старая витрина (фоллбэк)
CREATE TABLE IF NOT EXISTS bionic_analytics.user_telemetry_mart (
    user_id UInt32,
    full_name String,
    email String,
    age Nullable(UInt16),
    registration_date Nullable(Date),
    device_count UInt64,
    total_steps UInt64,
    avg_battery_level Float64,
    total_usage_hours Float64,
    last_active_date Nullable(DateTime),
    has_telemetry UInt8,
    report_date Date
) ENGINE = MergeTree()
ORDER BY (user_id, report_date);