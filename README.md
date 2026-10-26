# Сервис бронирования мест

Данный сервис предназначен для бронирования мест на любые мероприятия, их подтверждения или отмены

## Запуск

```
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
python -m pip install -r requirements.txt
pytest -q
python demo.py
uvicorn main:app --reload
```

Swagger UI: http://127.0.0.1:8000/docs
OpenAPI: http://127.0.0.1:8000/openapi.json

Тесты: `python -m pytest -q` (ЛР № 1: `test_reservations.py`, `test_smoke.py`; ЛР № 2: `test_lab2.py`).

## Реализованные правила

- `POST /reservations` создает бронь со статусом `held` и id в формате uuid4. Формат места проверяет Pydantic (422).
- Активной считается бронь в статусе `held` или `confirmed`. Второй активной брони на то же место того же события быть не может (409).
- `POST /reservations/{id}/confirm` переводит `held -> confirmed`. Неизвестный id дает 404, повторное подтверждение дает 409.
- `POST /reservations/{id}/cancel` переводит бронь из `held` или `confirmed` в `cancelled` и освобождает место. Неизвестный id дает 404, повторная отмена дает 409.
- Все проверки выполняются до изменения `store`.

## Примеры запросов

Создание брони:

```
curl -X POST http://127.0.0.1:8000/reservations \
  -H "Content-Type: application/json" \
  -d '{"event_id": "concert-7", "seat": "B-5", "customer_id": "customer-2"}'
```

Получение брони:

```
curl -X GET http://127.0.0.1:8000/reservations/reservation-001
```

Подтверждение брони:

```
curl -X POST http://127.0.0.1:8000/reservations/reservation-001/confirm
```

Отмена брони:

```
curl -X POST http://127.0.0.1:8000/reservations/reservation-001/cancel
```

## ЛР № 2. HTTP-контракт, диагностика и HTTPS

### Маршруты

| Метод | URI                                       | Успех         | Ошибки       |
| ---------- | ----------------------------------------- | ------------------ | ------------------ |
| GET        | `/health`                               | 200                |                    |
| GET        | `/reservations?status=&event_id=&seat=` | 200                | 400, 422           |
| GET        | `/reservations/{id}`                    | 200                | 404                |
| POST       | `/reservations`                         | 201 + `Location` | 409, 422           |
| PATCH      | `/reservations/{id}`                    | 200                | 400, 404, 409, 422 |
| POST       | `/reservations/{id}/confirm`            | 200                | 404, 409           |
| POST       | `/reservations/{id}/cancel`             | 200                | 404, 409           |

### Фильтры GET /reservations

Фильтры необязательные и комбинируются (логическое И).

- `status` — `held`, `confirmed` или `cancelled`; другое значение дает 422.
- `event_id` — точное совпадение.
- `seat` — формат `A-12`, иначе 422. Место осмысленно только в рамках события, поэтому `seat` без `event_id` дает 400.

### PATCH /reservations/

Меняется только `seat`, и только у брони в статусе `held`.

Порядок: 422 (Pydantic: формат места, `null`, лишние поля) → 404 → 409 (статус не `held`) → 400 (пустое тело) → 409 (место занято активной бронью того же события).
PATCH на то же самое место возвращает 200 без изменений. Старое место освобождается, новое занимается.

### Диагностические заголовки

Каждый ответ содержит `X-Request-ID` (из запроса или uuid4) и `X-Process-Time-ms`.

```
curl -v -H 'X-Request-ID: lab2-demo' http://127.0.0.1:8000/health
```

### HTTPS. Создание учебного сертификата и запуск

```
mkdir -p certs
openssl req -x509 -newkey rsa:2048 -nodes -days 30 \
  -keyout certs/dev-key.pem -out certs/dev-cert.pem \
  -subj "/CN=localhost" \
  -addext "subjectAltName=DNS:localhost,IP:127.0.0.1"
chmod 600 certs/dev-key.pem

uvicorn main:app --host 127.0.0.1 --port 8443 \
  --ssl-keyfile certs/dev-key.pem --ssl-certfile certs/dev-cert.pem

curl -k -v https://127.0.0.1:8443/health
```

**Внимание**: `curl -k` отключает проверку сертификата и допустим только для этого локального учебного сертификата. Каталог `certs/` в `.gitignore`, закрытый ключ нельзя публиковать.

### Nginx

Nginx завершает TLS на 8443, редиректит 8080 на HTTPS (308) и проксирует на FastAPI (8000). Конфигурация: `deploy/nginx-seat-reservation.conf`

Добавление конфигурации в общую

```
sudo nano /etc/nginx/nginx.conf
```

Внутри блока http { ... }, на одном уровне с существующим server { ... }, добавить:

```nginx
  include /home/bogdan/Documents/study/microservices/09_seat_reservation_service/deploy/nginx-seat-reservation.conf;
```

Проверка и запуск

```
sudo nginx -t
sudo systemctl reload nginx
uvicorn main:app --host 127.0.0.1 --port 8000 \
  --proxy-headers --forwarded-allow-ips=127.0.0.1

curl -I http://127.0.0.1:8080/health
curl -k -v https://127.0.0.1:8443/health
```

### Примеры

```
curl -s 'http://127.0.0.1:8000/reservations?status=held&event_id=concert-7&seat=A-12'
curl -i -X PATCH http://127.0.0.1:8000/reservations/reservation-001 \
  -H 'Content-Type: application/json' -d '{"seat":"C-3"}'
```

## ЛР № 3. Docker, PostgreSQL и Docker Compose

Разделы выше описывают состояние без БД и контейнеризации: код в корне, хранилище в памяти. Код сервера перенесен в `backend/` и работает с PostgreSQL. Тесты ЛР 1–2 остаются в корне как архив и на текущем коде не запускаются.

### Структура

```
backend/      FastAPI, SQLAlchemy, requirements.txt, Dockerfile
frontend/     index.html, app.js, styles.css, Dockerfile
proxy/        nginx.conf
compose.yaml
.env.example
```

### Контейнеры

| Контейнер | Роль                                  | Сети   | Порт хоста |
| ------------------ | ----------------------------------------- | ---------- | ------------------- |
| proxy              | Nginx, единая точка входа | edge       | 8080:80             |
| frontend           | HTML/CSS/JS                               | edge       | нет              |
| backend            | FastAPI и доступ к SQL            | edge, data | нет              |
| db                 | PostgreSQL, том `pgdata`             | data       | нет              |

Маршруты: `/` → frontend, `/api/*` → backend (префикс `/api` убирается).

### Запуск

```
cp .env.example .env
docker compose config
docker compose up --build -d
docker compose ps
```

Интерфейс: http://localhost:8080. API: `curl http://localhost:8080/api/reservations`.

В `.env` задается `POSTGRES_PASSWORD`. Файл `.env` в Git не попадает. Порт 8080 должен быть свободен: nginx из ЛР 2 нужно остановить.

### Переменные окружения backend

`DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`. Compose берет их из `.env`, `DB_HOST=db`.

### Health

- `GET /api/health/live` не обращается к БД.
- `GET /api/health/ready` выполняет `SELECT 1`, при недоступной БД отвечает 503.

### Хранилище

Таблица `seat_reservations` создается при старте backend через `Base.metadata.create_all`. Миграций нет: изменение структуры уже созданной таблицы не применяется. Данные лежат в именованном томе `lab3_pgdata`, которым управляет Docker.

### Проверки

| Команда | Что делает |
|---|---|
| `docker compose logs --tail=100` | Показывает последние 100 строк логов всех сервисов |
| `docker inspect lab3-proxy-1 lab3-backend-1 lab3-db-1` | Выводит сети, порты, переменные окружения и тома контейнеров |
| `docker compose exec proxy nginx -t` | Проверяет синтаксис конфигурации Nginx внутри proxy |
| `docker compose exec db pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB"` | Проверяет, что PostgreSQL принимает подключения |
| `docker compose restart backend` | Перезапускает backend, данные в БД остаются |
| `docker compose down` | Останавливает и удаляет контейнеры и сети, том сохраняется |
| `docker compose up -d` | Создаёт и запускает контейнеры заново в фоне |
| `docker compose stop db` | Останавливает БД: `/api/health/ready` должен вернуть 503 |
| `docker compose start db` | Запускает БД снова, сервис должен восстановиться |

`docker compose down -v` удаляет том вместе с данными.
