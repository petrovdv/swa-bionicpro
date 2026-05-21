-- Тестовые данные: пользователи и телеметрия протезов
CREATE DATABASE crm;
CREATE DATABASE telemetry;

\c crm
GRANT ALL ON SCHEMA public TO airflow;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO airflow;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO airflow;

CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    full_name VARCHAR(100),
    email VARCHAR(100) UNIQUE,
    age INT,
    registration_date DATE DEFAULT CURRENT_DATE
);

INSERT INTO users (full_name, email, age, registration_date) VALUES
('User One', 'user1@example.com', 34, '2023-01-15'),
('User Two', 'user2@example.com', 28, '2023-03-22'),

('Admin One', 'admin1@example.com', 42, '2022-06-10'),

('Prothetic One', 'prothetic1@example.com', 31, '2023-08-20'),
('Prothetic Two', 'prothetic2@example.com', 47, '2022-12-05'),
('Prothetic Three', 'prothetic3@example.com', 39, '2024-02-14');

\c telemetry
GRANT ALL ON SCHEMA public TO airflow;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO airflow;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO airflow;

CREATE TABLE prosthetic_telemetry (
    id SERIAL PRIMARY KEY,
    user_id INT,
    device_id VARCHAR(50),
    step_count INT,
    battery_level FLOAT,
    usage_hours FLOAT,
    recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Телеметрия только для пользователей с протезами (id: 4, 5, 6)
INSERT INTO prosthetic_telemetry (user_id, device_id, step_count, battery_level, usage_hours, recorded_at) VALUES
-- Prothetic One (user id=4)
(4, 'BIONIC-PRO-X1', 12000, 85.5, 8.2, '2024-05-10 08:00:00'),
(4, 'BIONIC-PRO-X1', 10500, 70.0, 7.1, '2024-05-11 08:00:00'),
(4, 'BIONIC-PRO-X1', 11000, 50.0, 7.5, '2024-05-12 08:00:00'),

-- Prothetic Two (user id=5)
(5, 'BIONIC-PRO-Z2', 8000, 92.0, 5.5, '2024-05-10 09:00:00'),
(5, 'BIONIC-PRO-Z2', 9500, 65.0, 6.0, '2024-05-11 09:00:00'),
(5, 'BIONIC-PRO-Z2', 7200, 88.0, 4.8, '2024-05-12 09:00:00'),

-- Prothetic Three (user id=6)
(6, 'BIONIC-PRO-Y3', 15000, 78.0, 9.2, '2024-05-10 07:30:00'),
(6, 'BIONIC-PRO-Y3', 13500, 62.0, 8.1, '2024-05-11 07:30:00');