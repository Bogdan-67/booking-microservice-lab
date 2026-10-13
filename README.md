# Вариант 9. Сервис бронирования мест

Реализуйте удержание и подтверждение места. Место события нельзя удержать повторно,
пока бронь активна. Тесты: создание, формат места (422), конфликт места (409),
подтверждение, повторное подтверждение (409), неизвестная бронь (404).

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
