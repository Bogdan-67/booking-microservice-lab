import os
from typing import Literal
from uuid import uuid4

from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel, Field

SERVICE_NAME = os.getenv("SERVICE_NAME", "seat-reservation-service")
SERVICE_VERSION = os.getenv("SERVICE_VERSION", "0.1.0")
app = FastAPI(title=SERVICE_NAME, version=SERVICE_VERSION)


class ReservationCreate(BaseModel):
    event_id: str = Field(min_length=1)
    seat: str = Field(pattern=r"^[A-Z]-\d{1,3}$")
    customer_id: str = Field(min_length=1)


class Reservation(ReservationCreate):
    id: str
    status: Literal["held", "confirmed", "cancelled"] = "held"


store: dict[str, Reservation] = {
    "reservation-001": Reservation(id="reservation-001", event_id="concert-7", seat="A-12", customer_id="customer-1")
}


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": SERVICE_NAME, "version": SERVICE_VERSION}


@app.get("/reservations", response_model=list[Reservation])
def list_reservations() -> list[Reservation]:
    return list(store.values())


@app.get("/reservations/{reservation_id}", response_model=Reservation)
def get_reservation(reservation_id: str) -> Reservation:
    if reservation_id not in store:
        raise HTTPException(status_code=404, detail="Reservation not found")
    return store[reservation_id]


@app.post("/reservations", response_model=Reservation, status_code=status.HTTP_201_CREATED)
def create_reservation(payload: ReservationCreate) -> Reservation:
    # TODO: создать held-бронь; активная бронь места одного события должна быть уникальной.
    raise HTTPException(status_code=501, detail="Implement create_reservation")


@app.post("/reservations/{reservation_id}/confirm", response_model=Reservation)
def confirm_reservation(reservation_id: str) -> Reservation:
    # TODO: held -> confirmed; повторное подтверждение вернуть как 409.
    raise HTTPException(status_code=501, detail="Implement confirm_reservation")

