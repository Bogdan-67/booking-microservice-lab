import os
from time import perf_counter
from typing import Literal, Optional
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Query, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field

SERVICE_NAME = os.getenv("SERVICE_NAME", "seat-reservation-service")
SERVICE_VERSION = os.getenv("SERVICE_VERSION", "0.1.0")
app = FastAPI(title=SERVICE_NAME, version=SERVICE_VERSION)


SEAT_PATTERN = r"^[A-Z]-\d{1,3}$"
ReservationStatus = Literal["held", "confirmed", "cancelled"]


class ReservationCreate(BaseModel):
    event_id: str = Field(min_length=1)
    seat: str = Field(pattern=SEAT_PATTERN)
    customer_id: str = Field(min_length=1)


class ReservationPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    seat: str = Field(default=None, pattern=SEAT_PATTERN)


class Reservation(ReservationCreate):
    id: str
    status: ReservationStatus = "held"


store: dict[str, Reservation] = {
    "reservation-001": Reservation(id="reservation-001", event_id="concert-7", seat="A-12", customer_id="customer-1")
}


ACTIVE_STATUSES = ("held", "confirmed")
active_seats: set[tuple[str, str]] = {
    (r.event_id, r.seat) for r in store.values() if r.status in ACTIVE_STATUSES
}


@app.middleware("http")
async def add_diagnostic_headers(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID", str(uuid4()))
    started = perf_counter()
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Process-Time-ms"] = f"{(perf_counter() - started) * 1000:.2f}"
    return response


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": SERVICE_NAME, "version": SERVICE_VERSION}


@app.get("/reservations", response_model=list[Reservation], tags=["reservations"])
def list_reservations(
    reservation_status: Optional[ReservationStatus] = Query(None, alias="status"),
    event_id: Optional[str] = Query(None, min_length=1),
    seat: Optional[str] = Query(None, pattern=SEAT_PATTERN),
) -> list[Reservation]:
    if seat is not None and event_id is None:
        raise HTTPException(status_code=400, detail="seat filter requires event_id")
    reservations = list(store.values())
    if reservation_status is not None:
        reservations = [r for r in reservations if r.status == reservation_status]
    if event_id is not None:
        reservations = [r for r in reservations if r.event_id == event_id]
    if seat is not None:
        reservations = [r for r in reservations if r.seat == seat]
    return reservations


@app.get("/reservations/{reservation_id}", response_model=Reservation)
def get_reservation(reservation_id: str) -> Reservation:
    if reservation_id not in store:
        raise HTTPException(status_code=404, detail="Reservation not found")
    return store[reservation_id]


@app.post("/reservations", response_model=Reservation, status_code=status.HTTP_201_CREATED)
def create_reservation(payload: ReservationCreate, response: Response) -> Reservation:
    key = (payload.event_id, payload.seat)
    if key in active_seats:
        raise HTTPException(status_code=409, detail="Seat is already reserved")
    reservation = Reservation(id=str(uuid4()), status="held", **payload.model_dump())
    store[reservation.id] = reservation
    active_seats.add(key)
    response.headers["Location"] = f"/reservations/{reservation.id}"
    return reservation


@app.patch("/reservations/{reservation_id}", response_model=Reservation, tags=["reservations"])
def patch_reservation(reservation_id: str, payload: ReservationPatch) -> Reservation:
    reservation = store.get(reservation_id)
    if reservation is None:
        raise HTTPException(status_code=404, detail="Reservation not found")
    if reservation.status != "held":
        raise HTTPException(status_code=409, detail="Only held reservation can be changed")
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(status_code=400, detail="At least one field is required")
    old_key = (reservation.event_id, reservation.seat)
    new_key = (reservation.event_id, changes["seat"])
    if new_key != old_key and new_key in active_seats:
        raise HTTPException(status_code=409, detail="Seat is already reserved")
    updated = reservation.model_copy(update=changes)
    store[reservation_id] = updated
    active_seats.discard(old_key)
    active_seats.add(new_key)
    return updated


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
