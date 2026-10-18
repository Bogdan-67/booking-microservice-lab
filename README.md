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

- `POST /reservations` создаёт бронь со статусом `held` и id в формате uuid4. Формат места проверяет Pydantic (422).
- Активной считается бронь в статусе `held` или `confirmed`. Второй активной брони на то же место того же события быть не может (409).
- `POST /reservations/{id}/confirm` переводит `held -> confirmed`. Неизвестный id даёт 404, повторное подтверждение даёт 409.
- `POST /reservations/{id}/cancel` переводит бронь из `held` или `confirmed` в `cancelled` и освобождает место. Неизвестный id даёт 404, повторная отмена даёт 409.
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

| Метод | URI | Успех | Ошибки |
|---|---|---|---|
| GET | `/health` | 200 | |
| GET | `/reservations?status=&event_id=&seat=` | 200 | 400, 422 |
| GET | `/reservations/{id}` | 200 | 404 |
| POST | `/reservations` | 201 + `Location` | 409, 422 |
| PATCH | `/reservations/{id}` | 200 | 400, 404, 409, 422 |
| POST | `/reservations/{id}/confirm` | 200 | 404, 409 |
| POST | `/reservations/{id}/cancel` | 200 | 404, 409 |

### Фильтры GET /reservations

Фильтры необязательные и комбинируются (логическое И).

- `status` — `held`, `confirmed` или `cancelled`; другое значение даёт 422.
- `event_id` — точное совпадение.
- `seat` — формат `A-12`, иначе 422. Место осмысленно только в рамках события, поэтому `seat` без `event_id` даёт 400.

### PATCH /reservations/{id}

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
