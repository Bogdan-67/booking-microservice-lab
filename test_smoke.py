from fastapi.testclient import TestClient
from main import app

client = TestClient(app)


def test_health() -> None:
    assert client.get("/health").status_code == 200


def test_seed_reservation_is_held() -> None:
    response = client.get("/reservations/reservation-001")
    assert response.status_code == 200
    assert response.json()["status"] == "held"

