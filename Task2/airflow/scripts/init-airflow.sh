#!/bin/bash
# Скрипт инициализации Airflow: БД, пользователь, подключения

echo "Инициализация метаданных БД Airflow..."
airflow db init

echo "Создание админ-пользователя..."
airflow users create \
  --username admin \
  --firstname admin \
  --lastname admin \
  --role Admin \
  --email admin@bionic.com \
  --password admin

echo "Создание подключения к CRM (PostgreSQL)..."
airflow connections add 'pg_crm' \
  --conn-type 'postgres' \
  --conn-host 'postgres' \
  --conn-login 'airflow' \
  --conn-password 'airflow' \
  --conn-schema 'crm' \
  --conn-port '5432'

echo "Создание подключения к Телеметрии (PostgreSQL)..."
airflow connections add 'pg_telemetry' \
  --conn-type 'postgres' \
  --conn-host 'postgres' \
  --conn-login 'airflow' \
  --conn-password 'airflow' \
  --conn-schema 'telemetry' \
  --conn-port '5432'

echo "Создание подключения к ClickHouse..."
airflow connections add 'clickhouse_default' \
  --conn-type 'clickhouse' \
  --conn-host 'clickhouse' \
  --conn-login 'default' \
  --conn-password 'clickhouse_pass' \
  --conn-schema 'bionic_analytics' \
  --conn-port '9000'

echo "Инициализация Airflow завершена успешно!"