## Детали реализации

![Диаграмма архитектуры](diagram/BionicPRO_C4_model.drawio.png)

Запуск и сборка проекта:

`
docker compose build
`

`
docker compose up -d
`

После запуска необходимо пойти в Apache Airflow по адресу http://localhost:8081 и запустить 
пайплайн bionic_crm_ch_etl,
который соберет данные из двух баз PostgreSQL и создаст витрину — отдельную 
таблицу для сервиса отчётов в ClickHouse.

![DAG status](diagram/airflow_dag.png)

![ClickHouse results](diagram/clickhouse_results.png)

Потом можно идти в интерфейс фронт приложения, доступный по https://localhost, 
залогиниться под тестовым пользователем prothetic1 и скачать pdf-отчёт.

![Report PDF](diagram/report_pdf.png)

В сервисе reports есть переменная окружения MART_TABLE_NAME, в ней можно указать какую
витрину использовать для генерации отчета: созданную через Apache Airflow user_telemetry_mart 
или через Debezium user_telemetry_mart_cdc.



