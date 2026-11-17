import json
import os

import grpc

import booking_pb2 as pb2
import booking_pb2_grpc as pb2_grpc

GRPC_CONFIG = {
    "methodConfig": [{
        "name": [{"service": "booking.v1.BookingService", "method": "GetBooking"}],
        "timeout": "0.8s",
        "retryPolicy": {
            "maxAttempts": 3,
            "initialBackoff": "0.1s",
            "maxBackoff": "0.4s",
            "backoffMultiplier": 2,
            "retryableStatusCodes": ["UNAVAILABLE"],
        },
    }]
}

channel = grpc.insecure_channel(
    os.getenv("GRPC_TARGET", "booking-grpc:50051"),
    options=(("grpc.service_config", json.dumps(GRPC_CONFIG)),),
)
stub = pb2_grpc.BookingServiceStub(channel)


def get_booking(booking_id: str, request_id: str):
    return stub.GetBooking(
        pb2.GetBookingRequest(id=booking_id),
        timeout=float(os.getenv("GRPC_DEADLINE", "0.35")),
        metadata=(("x-request-id", request_id),),
    )


def confirm_booking(booking_id: str, request_id: str):
    return stub.ConfirmBooking(
        pb2.ConfirmBookingRequest(id=booking_id),
        timeout=float(os.getenv("GRPC_DEADLINE", "0.35")),
        metadata=(("x-request-id", request_id),),
    )
