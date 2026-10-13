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


ACTIVE_STATUSES = ("held", "confirmed")
active_seats: set[tuple[str, str]] = {
    (r.event_id, r.seat) for r in store.values() if r.status in ACTIVE_STATUSES
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
    key = (payload.event_id, payload.seat)
    if key in active_seats:
        raise HTTPException(status_code=409, detail="Seat is already reserved")
    reservation = Reservation(id=str(uuid4()), status="held", **payload.model_dump())
    store[reservation.id] = reservation
    active_seats.add(key)
    return reservation


@app.post("/reservations/{reservation_id}/confirm", response_model=Reservation)
def confirm_reservation(reservation_id: str) -> Reservation:
    reservation = store.get(reservation_id)
    if reservation is None:
        raise HTTPException(status_code=404, detail="Reservation not found")
    if reservation.status != "held":
        raise HTTPException(status_code=409, detail="Reservation is not in held status")
    confirmed = reservation.model_copy(update={"status": "confirmed"})
    store[reservation_id] = confirmed
    return confirmed


@app.post("/reservations/{reservation_id}/cancel", response_model=Reservation)
def cancel_reservation(reservation_id: str) -> Reservation:
    reservation = store.get(reservation_id)
    if reservation is None:
        raise HTTPException(status_code=404, detail="Reservation not found")
    if reservation.status == "cancelled":
        raise HTTPException(status_code=409, detail="Reservation is already cancelled")
    cancelled = reservation.model_copy(update={"status": "cancelled"})
    store[reservation_id] = cancelled
    active_seats.discard((reservation.event_id, reservation.seat))
    return cancelled
