from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.hooks.base import BaseHook
from datetime import datetime, timedelta
import psycopg2
from clickhouse_driver import Client

default_args = {
    'owner': 'airflow',
    'depends_on_past': False,
    'start_date': datetime(2024, 1, 1),
    'retries': 1,
    'retry_delay': timedelta(minutes=2),
}

with DAG(
        'bionic_crm_ch_etl',
        default_args=default_args,
        schedule='@daily',  # Расписание: ежедневно
        catchup=False,
        max_active_runs=1,
        tags=['etl', 'clickhouse', 'bionic']
) as dag:
    def _get_pg_conn(conn_id):
        """Получение соединения с PostgreSQL из Airflow Connections"""
        conn = BaseHook.get_connection(conn_id)
        return psycopg2.connect(
            host=conn.host, port=conn.port, dbname=conn.schema,
            user=conn.login, password=conn.password
        )


    def _get_ch_client():
        """Получение клиента ClickHouse из Airflow Connections"""
        conn = BaseHook.get_connection('clickhouse_default')
        return Client(
            host=conn.host, port=9000, database=conn.schema,
            user=conn.login, password=conn.password
        )


    def extract_and_load_crm(**context):
        """Извлечение пользователей из CRM и загрузка в ClickHouse"""
        pg_conn = _get_pg_conn('pg_crm')
        cur = pg_conn.cursor()
        cur.execute("SELECT id, full_name, email, age, registration_date FROM users ORDER BY id;")
        rows = cur.fetchall()
        cur.close()
        pg_conn.close()

        client = _get_ch_client()

        # Создаём таблицу в ClickHouse
        client.execute("DROP TABLE IF EXISTS crm_users")
        client.execute("""
                       CREATE TABLE crm_users
                       (
                           user_id           UInt32,
                           full_name         String,
                           email             String,
                           age               UInt16,
                           registration_date Date
                       ) ENGINE = MergeTree() 
            ORDER BY user_id
                       """)

        client.execute("INSERT INTO crm_users VALUES", rows)
        client.disconnect()
        print(f"Loaded {len(rows)} users to ClickHouse")


    def extract_and_load_telemetry(**context):
        """Извлечение телеметрии и загрузка в ClickHouse"""
        pg_conn = _get_pg_conn('pg_telemetry')
        cur = pg_conn.cursor()
        cur.execute("""
                    SELECT user_id, device_id, step_count, battery_level, usage_hours, recorded_at
                    FROM prosthetic_telemetry
                    ORDER BY user_id, recorded_at;
                    """)
        rows = cur.fetchall()
        cur.close()
        pg_conn.close()

        client = _get_ch_client()

        client.execute("DROP TABLE IF EXISTS prosthetic_telemetry")
        client.execute("""
                       CREATE TABLE prosthetic_telemetry
                       (
                           user_id       UInt32,
                           device_id     String,
                           step_count    UInt32,
                           battery_level Float64,
                           usage_hours   Float64,
                           recorded_at   DateTime
                       ) ENGINE = MergeTree() 
            ORDER BY (user_id, recorded_at)
                       """)

        client.execute("INSERT INTO prosthetic_telemetry VALUES", rows)
        client.disconnect()
        print(f"Loaded {len(rows)} telemetry records to ClickHouse")


    def build_user_telemetry_mart(**context):
        """
        Построение витрины данных: объединение CRM и телеметрии.
        Витрина оптимизирована для быстрых отчётов по пользователям.
        """
        client = _get_ch_client()

        client.execute("DROP TABLE IF EXISTS user_telemetry_mart")

        # Создаём витрину с агрегированными метриками
        client.execute("""
                       CREATE TABLE user_telemetry_mart
                           ENGINE = MergeTree
                       (
                       )
                           ORDER BY
                       (
                           user_id,
                           report_date
                       )
                       AS
                       SELECT c.user_id,
                              c.full_name,
                              c.email,
                              c.age,
                              c.registration_date,

                              -- Агрегированные метрики телеметрии
                              count(t.device_id)     AS device_count,
                              sum(t.step_count)      AS total_steps,
                              avg(t.battery_level)   AS avg_battery_level,
                              sum(t.usage_hours)     AS total_usage_hours,
                              max(t.recorded_at)     AS last_active_date,

                              -- Флаг: есть ли у пользователя телеметрия
                              count(t.device_id) > 0 AS has_telemetry,

                              -- Дата формирования отчёта
                              today()                AS report_date

                       FROM crm_users c
                                LEFT JOIN prosthetic_telemetry t
                                          ON c.user_id = t.user_id
                       GROUP BY c.user_id, c.full_name, c.email, c.age, c.registration_date
                       """)

        client.disconnect()
        print("Successfully built user_telemetry_mart")


    # Определение задач
    extract_crm = PythonOperator(
        task_id='extract_crm_to_clickhouse',
        python_callable=extract_and_load_crm
    )

    extract_telemetry = PythonOperator(
        task_id='extract_telemetry_to_clickhouse',
        python_callable=extract_and_load_telemetry
    )

    build_mart = PythonOperator(
        task_id='build_user_telemetry_mart',
        python_callable=build_user_telemetry_mart
    )

    # Порядок выполнения: параллельная загрузка → построение витрины
    [extract_crm, extract_telemetry] >> build_mart