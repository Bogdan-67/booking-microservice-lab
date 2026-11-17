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

| Команда                                                              | Что делает                                                                                             |
| --------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------- |
| `docker compose logs --tail=100`                                          | Показывает последние 100 строк логов всех сервисов                     |
| `docker inspect lab3-proxy-1 lab3-backend-1 lab3-db-1`                    | Выводит сети, порты, переменные окружения и тома контейнеров |
| `docker compose exec proxy nginx -t`                                      | Проверяет синтаксис конфигурации Nginx внутри proxy                         |
| `docker compose exec db pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB"` | Проверяет, что PostgreSQL принимает подключения                                 |
| `docker compose restart backend`                                          | Перезапускает backend, данные в БД остаются                                       |
| `docker compose down`                                                     | Останавливает и удаляет контейнеры и сети, том сохраняется    |
| `docker compose up -d`                                                    | Создаёт и запускает контейнеры заново в фоне                              |
| `docker compose stop db`                                                  | Останавливает БД: `/api/health/ready` должен вернуть 503                          |
| `docker compose start db`                                                 | Запускает БД снова, сервис должен восстановиться                      |

`docker compose down -v` удаляет том вместе с данными.

## ЛР № 4. Kubernetes на k3s

Приложение из ЛР 3 развернуто в односерверном кластере k3s на Linux VM. Манифесты лежат в `k8s/`, образы backend и frontend берутся из Docker Hub по фиксированным тегам.

### Окружение

| Параметр | Значение                                                                                              |
| ---------------- | ------------------------------------------------------------------------------------------------------------- |
| VM               | Ubuntu Server 24.04 LTS, KVM/libvirt, 4 vCPU, 6 ГБ RAM, 30 ГБ диска                                  |
| Нода         | `k3s-lab`, `192.168.122.68` (NAT-сеть libvirt `default`)                                            |
| k3s / Kubernetes | `v1.37.2+k3s1`                                                                                              |
| Namespace        | `msa-v9-tugai`                                                                                              |
| Ingress host     | `reservations.lab.local`                                                                                    |
| Образы     | `docker.io/bogdan67/seat-reservation-backend:1.0.0`, `docker.io/bogdan67/seat-reservation-frontend:1.0.0` |

### Архитектура

```
браузер → 192.168.122.68:80 → Traefik Ingress (reservations.lab.local)
        → Service proxy → Pod Nginx → Service frontend | Service backend
        → backend Pod → Service db → PostgreSQL Pod (db-0) + PVC data-db-0
```

| Компонент | Ресурсы                                             | Реплики     | Доступ                               |
| ------------------ | ---------------------------------------------------------- | ------------------ | ------------------------------------------ |
| Traefik            | встроенный ingress controller k3s                | системный | 80/443 ноды                            |
| proxy              | Deployment + Service + ConfigMap `proxy-config`          | 1                  | ClusterIP                                  |
| frontend           | Deployment + Service                                       | 1                  | ClusterIP                                  |
| backend            | Deployment + Service                                       | 2                  | ClusterIP                                  |
| db                 | StatefulSet + headless Service + PVC (`local-path`, 2Gi) | 1                  | только внутри кластера |

Наружу приложение доступно только через Ingress. Сервисы находят друг друга по DNS-именам Service (`backend`, `frontend`, `db`). Параметры подключения к БД лежат в ConfigMap `app-config`, пароль в Secret `db-secret`.

### Манифесты

```
k8s/
├── 00-namespace.yaml     Namespace msa-v9-tugai
├── 01-app-config.yaml    ConfigMap app-config (DB_HOST, DB_PORT, DB_NAME, DB_USER)
├── 02-database.yaml      headless Service db + StatefulSet db
├── 03-backend.yaml       Deployment backend (2 реплики, probes, resources) + Service
├── 04-frontend.yaml      Deployment frontend + Service
├── 05-proxy-config.yaml  ConfigMap proxy-config (default.conf Nginx)
├── 06-proxy.yaml         Deployment proxy + Service
└── 07-ingress.yaml       Ingress app → proxy:80
```

Secret в репозиторий не входит и создается отдельной командой.

### Публикация образов

```
docker compose build
docker tag lab3-backend bogdan67/seat-reservation-backend:1.0.0
docker tag lab3-frontend bogdan67/seat-reservation-frontend:1.0.0
docker push bogdan67/seat-reservation-backend:1.0.0
docker push bogdan67/seat-reservation-frontend:1.0.0
```

Теги не перезаписываются: исправленная версия публикуется с новым тегом (`1.0.1`).

### Развертывание

```
kubectl apply -f k8s/00-namespace.yaml
kubectl config set-context --current --namespace=msa-v9-tugai

read -s DB_PASSWORD
kubectl create secret generic db-secret \
  --from-literal=POSTGRES_PASSWORD="$DB_PASSWORD" \
  --dry-run=client -o yaml | kubectl apply -f -
unset DB_PASSWORD

kubectl apply -f k8s/
kubectl rollout status statefulset/db --timeout=180s
kubectl wait --for=condition=Available deployment/backend deployment/frontend deployment/proxy --timeout=180s
kubectl get deployments,statefulsets,pods,services,pvc,ingress
```

На рабочей станции в `/etc/hosts`:

```
192.168.122.68 reservations.lab.local
```

Интерфейс: http://reservations.lab.local. API:

```
curl http://reservations.lab.local/api/reservations
curl -H "Host: reservations.lab.local" http://192.168.122.68/api/reservations
```

Если порт 80 ноды недоступен, для диагностики: `kubectl port-forward service/proxy 8080:80`.

### Probes

- readiness backend: `GET /health/ready` (`SELECT 1`). Pod без готовой БД исключается из endpoints Service.
- liveness backend: `GET /health/live`, к БД не обращается. Кратковременная недоступность PostgreSQL не вызывает перезапуск контейнера.
- readiness db: `pg_isready`.

### Обновление и откат

```
kubectl set image deployment/backend backend=docker.io/bogdan67/seat-reservation-backend:1.0.1
kubectl rollout status deployment/backend
kubectl rollout history deployment/backend
kubectl rollout undo deployment/backend
```

Стратегия RollingUpdate с `maxUnavailable: 0`, `maxSurge: 1`: при обновлении число готовых реплик не опускается ниже двух.

### Проверки

| Команда                                                                              | Что проверяет                                                                                    |
| ------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------ |
| `kubectl delete pod <backend-pod>`                                                        | Deployment восстанавливает 2 реплики                                                   |
| `kubectl run dns-test --rm -it --restart=Never --image=busybox:1.36 -- nslookup backend`  | Service сохраняет DNS-имя при смене Pod IP                                               |
| `kubectl scale deployment backend --replicas=3`                                           | Масштабирование отражается в Deployment и ReplicaSet                              |
| `kubectl get endpointslices -l kubernetes.io/service-name=backend`                        | Адреса готовых backend Pod                                                                      |
| `kubectl delete pod db-0`                                                                 | StatefulSet пересоздает `db-0`, PVC остается Bound, данные сохраняются |
| `kubectl exec -it db-0 -- psql -U appuser -d appdb -c "SELECT * FROM seat_reservations;"` | Данные в PostgreSQL                                                                                   |

Диагностика:

```
kubectl describe pod <pod>
kubectl logs <pod> --all-containers --tail=100
kubectl get events --sort-by=.lastTimestamp
sudo journalctl -u k3s -n 100 --no-pager
```

### Очистка

```
kubectl delete -f k8s/
kubectl get pvc          # PVC удаляется только вручную, если данные больше не нужны
kubectl delete namespace msa-v9-tugai
```

## ЛР № 5. gRPC, REST-фасад и API Gateway

Чтение и подтверждение брони вынесены в отдельный gRPC-сервис. Внешние клиенты работают с ним через REST-фасад по версионированному API `/api/v1`. Nginx выполняет роль API Gateway. Старый маршрут `/api/*` продолжает работать через backend.

### Архитектура

```
браузер → Traefik (TLS, reservations.lab.local) → Nginx
        ├── /api/v1/* → rest-facade:8000 → gRPC booking-grpc:50051 → db:5432
        ├── /api/*    → backend:8000 → db:5432
        └── /         → frontend:80
```

| Компонент | Ресурсы | Реплики | Порт |
| --- | --- | --- | --- |
| rest-facade | Deployment + Service | 1 | 8000, ClusterIP |
| booking-grpc | Deployment + Service | 2 | 50051, ClusterIP |

gRPC-сервис использует ту же таблицу `seat_reservations`, что и backend.

### Структура

```
proto/booking.proto        контракт BookingService
grpc_service/              gRPC-сервер, Dockerfile
rest_facade/               FastAPI-фасад и gRPC-клиент, Dockerfile
k8s/08-booking-grpc.yaml   Deployment + Service booking-grpc
k8s/09-rest-facade.yaml    Deployment + Service rest-facade
```

### API

| Метод | URI | gRPC | Ответы |
| --- | --- | --- | --- |
| GET | `/api/v1/bookings/{id}` | GetBooking | 200, 404, 503, 504 |
| POST | `/api/v1/bookings/{id}/confirm` | ConfirmBooking | 200, 400, 404, 409, 503, 504 |

| gRPC status | HTTP |
| --- | --- |
| INVALID_ARGUMENT | 400 |
| NOT_FOUND | 404 |
| FAILED_PRECONDITION | 409 |
| UNAVAILABLE | 503 |
| DEADLINE_EXCEEDED | 504 |
| остальные | 502 |

Подтверждение возможно только из статуса `held`, повторное подтверждение дает 409. При превышении лимита запросов Nginx отвечает 429.

```
curl -k https://reservations.lab.local/api/v1/bookings/<id>
curl -k -X POST https://reservations.lab.local/api/v1/bookings/<id>/confirm
```

### Надежность

- Deadline каждого вызова фасада к gRPC — 350 мс.
- `GetBooking` при `UNAVAILABLE` повторяется до 3 попыток. `ConfirmBooking` не повторяется.
- Nginx ограничивает `/api/v1/` до 8 запросов в секунду с одного IP (`burst=4`).
- `X-Request-ID` передается от Nginx в фасад и в gRPC metadata, поэтому один запрос можно найти в логах всех трех компонентов.

### Генерация кода

В образах код генерируется при сборке. Локально, для IDE:

```
pip install -r requirements.txt
python -m grpc_tools.protoc -I proto --python_out=grpc_service --grpc_python_out=grpc_service proto/booking.proto
python -m grpc_tools.protoc -I proto --python_out=rest_facade --grpc_python_out=rest_facade proto/booking.proto
```

Сгенерированные `*_pb2*.py` в Git не попадают.

### Сборка и публикация образов

Сборка выполняется из корня репозитория, чтобы образы видели `proto/`.

```
docker build -f grpc_service/Dockerfile -t bogdan67/seat-reservation-grpc:1.0.1 .
docker build -f rest_facade/Dockerfile -t bogdan67/seat-reservation-facade:1.0.1 .
docker push bogdan67/seat-reservation-grpc:1.0.1
docker push bogdan67/seat-reservation-facade:1.0.1
```

### Развертывание

TLS-сертификат для Ingress создается один раз и в репозиторий не попадает:

```
openssl req -x509 -newkey rsa:2048 -nodes -days 30 -keyout certs/tls.key -out certs/tls.crt \
  -subj "/CN=reservations.lab.local" -addext "subjectAltName=DNS:reservations.lab.local"
kubectl create secret tls reservations-tls --cert=certs/tls.crt --key=certs/tls.key
```

```
kubectl apply -f k8s/
kubectl rollout restart deployment/proxy
kubectl rollout status deployment/booking-grpc
kubectl rollout status deployment/rest-facade
kubectl exec deploy/proxy -- nginx -t
```

Перезапуск proxy обязателен: конфигурация Nginx смонтирована через `subPath` и сама в Pod не обновляется.

### Переменные окружения

| Сервис | Переменная | Назначение |
| --- | --- | --- |
| rest-facade | `GRPC_TARGET` | адрес gRPC-сервиса, по умолчанию `booking-grpc:50051` |
| rest-facade | `GRPC_DEADLINE` | deadline вызова в секундах, по умолчанию `0.35` |
| booking-grpc | `DB_*` | подключение к PostgreSQL, из `app-config` и `db-secret` |
| booking-grpc | `TEST_DELAY_MS` | искусственная задержка обработчика, по умолчанию `0` |
| booking-grpc | `TEST_FAIL_UNAVAILABLE` | `1` — сервис отвечает UNAVAILABLE на каждый вызов |

Тестовые переменные применяются только в учебном окружении:

```
kubectl set env deployment/booking-grpc TEST_DELAY_MS=1000
kubectl set env deployment/booking-grpc TEST_DELAY_MS=0
```

### Проверки

| Команда | Что проверяет |
| --- | --- |
| `kubectl run grpcurl --rm -it --restart=Never --image=fullstorydev/grpcurl -- -plaintext booking-grpc:50051 list` | gRPC-сервис доступен, reflection включен |
| `curl -k -H 'X-Request-ID: test-01' https://reservations.lab.local/api/v1/bookings/<id>` | сквозной запрос через gateway |
| `kubectl logs -l app.kubernetes.io/name=booking-grpc --prefix \| grep test-01` | request ID дошел до gRPC-сервиса |
| `kubectl scale deployment/booking-grpc --replicas=0` | фасад отвечает 503 вместо зависания |
| `seq 1 20 \| xargs -P10 -I{} curl -k -s -o /dev/null -w '%{http_code}\n' https://reservations.lab.local/api/v1/bookings/<id> \| sort \| uniq -c` | часть запросов получает 429 |
