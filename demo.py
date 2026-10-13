from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


def show(number: int, title: str, response, value: str) -> None:
    print(f"{number}. {title:<28} HTTP {response.status_code}  {value}")


booking = {"event_id": "demo-event", "seat": "A-1", "customer_id": "customer-1"}

response = client.post("/reservations", json=booking)
reservation_id = response.json()["id"]
show(1, "Создание брони", response, f"status={response.json()['status']}")

response = client.post(f"/reservations/{reservation_id}/confirm")
show(2, "Подтверждение брони", response, f"status={response.json()['status']}")

response = client.post(f"/reservations/{reservation_id}/confirm")
show(3, "Повторное подтверждение", response, response.json()["detail"])

response = client.post("/reservations", json={**booking, "seat": "12A"})
show(4, "Некорректное место", response, response.json()["detail"][0]["msg"])

response = client.post("/reservations", json=booking)
show(5, "Занятое место", response, response.json()["detail"])

response = client.post(f"/reservations/{reservation_id}/cancel")
show(6, "Отмена брони", response, f"status={response.json()['status']}")

response = client.post("/reservations", json=booking)
show(7, "Бронь освободившегося места", response, f"status={response.json()['status']}")

response = client.post("/reservations/missing/confirm")
show(8, "Неизвестная бронь", response, response.json()["detail"])
