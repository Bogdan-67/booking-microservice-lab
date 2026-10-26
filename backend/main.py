import os
from contextlib import asynccontextmanager
from datetime import datetime
from time import perf_counter
from typing import Literal, Optional
from uuid import uuid4
from dotenv import load_dotenv

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import DateTime, String, create_engine, func, select, text
from sqlalchemy.engine import URL
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

load_dotenv()

SERVICE_NAME = os.getenv("SERVICE_NAME", "seat-reservation-service")
SERVICE_VERSION = os.getenv("SERVICE_VERSION", "0.1.0")

engine = create_engine(
    URL.create(
        "postgresql+psycopg",
        host=os.environ["DB_HOST"],
        port=int(os.environ["DB_PORT"]),
        database=os.environ["DB_NAME"],
        username=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
    )
)
SessionLocal = sessionmaker(bind=engine)


class Base(DeclarativeBase):
    pass


class ReservationRow(Base):
    __tablename__ = "seat_reservations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    event_id: Mapped[str] = mapped_column(String(120), nullable=False)
    seat: Mapped[str] = mapped_column(String(10), nullable=False)
    customer_id: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="held")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())



@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(engine)
    yield


app = FastAPI(title=SERVICE_NAME, version=SERVICE_VERSION, lifespan=lifespan)


def get_db():
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


SEAT_PATTERN = r"^[A-Z]-\d{1,3}$"
ReservationStatus = Literal["held", "confirmed", "cancelled"]
ACTIVE_STATUSES = ("held", "confirmed")


class ReservationCreate(BaseModel):
    event_id: str = Field(min_length=1)
    seat: str = Field(pattern=SEAT_PATTERN)
    customer_id: str = Field(min_length=1)


class ReservationPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    seat: str = Field(default=None, pattern=SEAT_PATTERN)


class Reservation(ReservationCreate):
    model_config = ConfigDict(from_attributes=True)

    id: str
    status: ReservationStatus = "held"


def get_row(db: Session, reservation_id: str) -> ReservationRow:
    row = db.get(ReservationRow, reservation_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Reservation not found")
    return row


def seat_is_taken(db: Session, event_id: str, seat: str, exclude_id: Optional[str] = None) -> bool:
    query = select(ReservationRow.id).where(
        ReservationRow.event_id == event_id,
        ReservationRow.seat == seat,
        ReservationRow.status.in_(ACTIVE_STATUSES),
    )
    if exclude_id is not None:
        query = query.where(ReservationRow.id != exclude_id)
    return db.scalar(query.limit(1)) is not None


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


@app.get("/health/live")
def health_live() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/ready")
def health_ready() -> dict[str, str]:
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except SQLAlchemyError:
        raise HTTPException(status_code=503, detail="Database is unavailable")
    return {"status": "ready"}


@app.get("/reservations", response_model=list[Reservation], tags=["reservations"])
def list_reservations(
    reservation_status: Optional[ReservationStatus] = Query(None, alias="status"),
    event_id: Optional[str] = Query(None, min_length=1),
    seat: Optional[str] = Query(None, pattern=SEAT_PATTERN),
    db: Session = Depends(get_db),
):
    if seat is not None and event_id is None:
        raise HTTPException(status_code=400, detail="seat filter requires event_id")
    query = select(ReservationRow).order_by(ReservationRow.created_at, ReservationRow.id)
    if reservation_status is not None:
        query = query.where(ReservationRow.status == reservation_status)
    if event_id is not None:
        query = query.where(ReservationRow.event_id == event_id)
    if seat is not None:
        query = query.where(ReservationRow.seat == seat)
    return db.scalars(query).all()


@app.get("/reservations/{reservation_id}", response_model=Reservation)
def get_reservation(reservation_id: str, db: Session = Depends(get_db)):
    return get_row(db, reservation_id)


@app.post("/reservations", response_model=Reservation, status_code=status.HTTP_201_CREATED)
def create_reservation(payload: ReservationCreate, response: Response, db: Session = Depends(get_db)):
    if seat_is_taken(db, payload.event_id, payload.seat):
        raise HTTPException(status_code=409, detail="Seat is already reserved")
    row = ReservationRow(id=str(uuid4()), status="held", **payload.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    response.headers["Location"] = f"/reservations/{row.id}"
    return row


@app.patch("/reservations/{reservation_id}", response_model=Reservation, tags=["reservations"])
def patch_reservation(reservation_id: str, payload: ReservationPatch, db: Session = Depends(get_db)):
    row = get_row(db, reservation_id)
    if row.status != "held":
        raise HTTPException(status_code=409, detail="Only held reservation can be changed")
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(status_code=400, detail="At least one field is required")
    if seat_is_taken(db, row.event_id, changes["seat"], exclude_id=row.id):
        raise HTTPException(status_code=409, detail="Seat is already reserved")
    row.seat = changes["seat"]
    db.commit()
    db.refresh(row)
    return row


@app.post("/reservations/{reservation_id}/confirm", response_model=Reservation)
def confirm_reservation(reservation_id: str, db: Session = Depends(get_db)):
    row = get_row(db, reservation_id)
    if row.status != "held":
        raise HTTPException(status_code=409, detail="Reservation is not in held status")
    row.status = "confirmed"
    db.commit()
    db.refresh(row)
    return row


@app.post("/reservations/{reservation_id}/cancel", response_model=Reservation)
def cancel_reservation(reservation_id: str, db: Session = Depends(get_db)):
    row = get_row(db, reservation_id)
    if row.status == "cancelled":
        raise HTTPException(status_code=409, detail="Reservation is already cancelled")
    row.status = "cancelled"
    db.commit()
    db.refresh(row)
    return row
