import os
from datetime import datetime

from sqlalchemy import DateTime, String, create_engine, func, update
from sqlalchemy.engine import URL
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

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
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


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


def get(reservation_id):
    with SessionLocal() as db:
        return db.get(ReservationRow, reservation_id)


def confirm(reservation_id):
    with SessionLocal() as db:
        result = db.execute(
            update(ReservationRow)
            .where(ReservationRow.id == reservation_id, ReservationRow.status == "held")
            .values(status="confirmed")
        )
        db.commit()
        return result.rowcount == 1
