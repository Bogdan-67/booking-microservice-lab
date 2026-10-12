import pytest
from fastapi.testclient import TestClient

from main import active_seats, app, store

client = TestClient(app)

NEW = {"event_id": "concert-7", "seat": "B-5", "customer_id": "customer-2"}


@pytest.fixture(autouse=True)
def restore_store():
    saved = {k: v.model_copy(deep=True) for k, v in store.items()}
    saved_seats = set(active_seats)
    yield
    store.clear()
    store.update(saved)
    active_seats.clear()
    active_seats.update(saved_seats)


def test_create_reservation_returns_201_and_is_readable() -> None:
    response = client.post("/reservations", json=NEW)
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "held"
    assert body["seat"] == "B-5"
    assert client.get(f"/reservations/{body['id']}").json() == body


def test_invalid_seat_returns_422_without_changing_store() -> None:
    before = {k: v.model_copy(deep=True) for k, v in store.items()}
    response = client.post("/reservations", json={**NEW, "seat": "12A"})
    assert response.status_code == 422
    assert response.json()["detail"]
    assert store == before


def test_taken_seat_returns_409_without_changing_store() -> None:
    before = {k: v.model_copy(deep=True) for k, v in store.items()}
    response = client.post(
        "/reservations",
        json={"event_id": "concert-7", "seat": "A-12", "customer_id": "customer-2"},
    )
    assert response.status_code == 409
    assert response.json()["detail"] == "Seat is already reserved"
    assert store == before


def test_same_seat_in_other_event_returns_201() -> None:
    response = client.post(
        "/reservations",
        json={"event_id": "concert-8", "seat": "A-12", "customer_id": "customer-2"},
    )
    assert response.status_code == 201
    assert response.json()["event_id"] == "concert-8"


def test_confirm_reservation_changes_status() -> None:
    response = client.post("/reservations/reservation-001/confirm")
    assert response.status_code == 200
    assert response.json()["status"] == "confirmed"
    assert client.get("/reservations/reservation-001").json()["status"] == "confirmed"


def test_repeated_confirm_returns_409_without_changing_reservation() -> None:
    first = client.post("/reservations/reservation-001/confirm")
    saved = store["reservation-001"].model_copy(deep=True)
    second = client.post("/reservations/reservation-001/confirm")
    assert first.status_code == 200
    assert second.status_code == 409
    assert second.json()["detail"] == "Reservation is not in held status"
    assert store["reservation-001"] == saved


def test_confirm_unknown_reservation_returns_404() -> None:
    before = {k: v.model_copy(deep=True) for k, v in store.items()}
    response = client.post("/reservations/missing/confirm")
    assert response.status_code == 404
    assert response.json()["detail"] == "Reservation not found"
    assert store == before
