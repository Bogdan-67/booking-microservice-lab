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


def snapshot():
    return {k: v.model_copy(deep=True) for k, v in store.items()}


def test_lab1_confirm_then_repeated_confirm_returns_409() -> None:
    assert client.post("/reservations/reservation-001/confirm").status_code == 200
    second = client.post("/reservations/reservation-001/confirm")
    assert second.status_code == 409
    assert second.json()["detail"] == "Reservation is not in held status"


def test_filter_by_status() -> None:
    client.post("/reservations/reservation-001/confirm")
    client.post("/reservations", json=NEW)
    response = client.get("/reservations", params={"status": "confirmed"})
    assert response.status_code == 200
    assert [r["id"] for r in response.json()] == ["reservation-001"]


def test_filter_by_event_and_seat_combined() -> None:
    client.post("/reservations", json=NEW)
    client.post("/reservations", json={**NEW, "event_id": "concert-8"})
    response = client.get("/reservations", params={"event_id": "concert-7", "seat": "B-5"})
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert (body[0]["event_id"], body[0]["seat"]) == ("concert-7", "B-5")


def test_filter_unknown_status_returns_422() -> None:
    response = client.get("/reservations", params={"status": "archived"})
    assert response.status_code == 422


def test_filter_seat_without_event_returns_400() -> None:
    response = client.get("/reservations", params={"seat": "A-12"})
    assert response.status_code == 400
    assert response.json()["detail"] == "seat filter requires event_id"


def test_patch_changes_only_seat() -> None:
    before = store["reservation-001"]
    response = client.patch("/reservations/reservation-001", json={"seat": "C-3"})
    assert response.status_code == 200
    body = response.json()
    assert body["seat"] == "C-3"
    assert body["event_id"] == before.event_id
    assert body["customer_id"] == before.customer_id
    assert body["status"] == "held"
    assert store["reservation-001"].seat == "C-3"


def test_patch_empty_body_returns_400_without_changes() -> None:
    before = snapshot()
    response = client.patch("/reservations/reservation-001", json={})
    assert response.status_code == 400
    assert store == before


def test_patch_confirmed_reservation_returns_409_without_changes() -> None:
    client.post("/reservations/reservation-001/confirm")
    before = snapshot()
    response = client.patch("/reservations/reservation-001", json={"seat": "C-3"})
    assert response.status_code == 409
    assert store == before


def test_patch_to_taken_seat_returns_409_without_changes() -> None:
    created = client.post("/reservations", json=NEW).json()
    before = snapshot()
    response = client.patch(f"/reservations/{created['id']}", json={"seat": "A-12"})
    assert response.status_code == 409
    assert response.json()["detail"] == "Seat is already reserved"
    assert store == before


def test_patch_unknown_reservation_returns_404() -> None:
    response = client.patch("/reservations/missing", json={"seat": "C-3"})
    assert response.status_code == 404


@pytest.mark.parametrize(
    "body",
    [{"seat": "12A"}, {"seat": None}, {"seat": "C-3", "status": "confirmed"}, {"event_id": "x"}],
)
def test_patch_invalid_body_returns_422_without_changes(body) -> None:
    before = snapshot()
    response = client.patch("/reservations/reservation-001", json=body)
    assert response.status_code == 422
    assert store == before


def test_patch_to_same_seat_is_idempotent() -> None:
    response = client.patch("/reservations/reservation-001", json={"seat": "A-12"})
    assert response.status_code == 200
    assert response.json()["seat"] == "A-12"


def test_patch_releases_old_seat_and_takes_new_one() -> None:
    client.patch("/reservations/reservation-001", json={"seat": "C-3"})
    old = client.post("/reservations", json={**NEW, "seat": "A-12"})
    new = client.post("/reservations", json={**NEW, "seat": "C-3"})
    assert old.status_code == 201
    assert new.status_code == 409


def test_create_returns_201_and_location() -> None:
    response = client.post("/reservations", json=NEW)
    assert response.status_code == 201
    location = response.headers["location"]
    assert location == f"/reservations/{response.json()['id']}"
    assert client.get(location).json() == response.json()


def test_request_id_is_returned_from_request() -> None:
    response = client.get("/health", headers={"X-Request-ID": "lab2-check"})
    assert response.headers["x-request-id"] == "lab2-check"
    assert float(response.headers["x-process-time-ms"]) >= 0


def test_request_id_is_generated_when_missing_and_present_on_errors() -> None:
    response = client.get("/reservations/missing")
    assert response.status_code == 404
    assert len(response.headers["x-request-id"]) == 36
    assert float(response.headers["x-process-time-ms"]) >= 0
