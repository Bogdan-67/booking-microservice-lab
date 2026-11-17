import logging
import uuid

import grpc
from fastapi import FastAPI, HTTPException, Request
from google.protobuf.json_format import MessageToDict

from grpc_client import confirm_booking, get_booking

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("rest-facade")

app = FastAPI()

STATUS_TO_HTTP = {
    grpc.StatusCode.INVALID_ARGUMENT: 400,
    grpc.StatusCode.NOT_FOUND: 404,
    grpc.StatusCode.FAILED_PRECONDITION: 409,
    grpc.StatusCode.DEADLINE_EXCEEDED: 504,
    grpc.StatusCode.UNAVAILABLE: 503,
}


def call_grpc(rpc, booking_id: str, request: Request):
    request_id = request.headers.get("x-request-id", str(uuid.uuid4()))
    try:
        reply = rpc(booking_id, request_id)
    except grpc.RpcError as exc:
        log.info("request_id=%s rpc=%s grpc_code=%s", request_id, rpc.__name__, exc.code().name)
        raise HTTPException(
            status_code=STATUS_TO_HTTP.get(exc.code(), 502),
            detail={"grpc_code": exc.code().name, "request_id": request_id},
        )
    log.info("request_id=%s rpc=%s grpc_code=OK", request_id, rpc.__name__)
    
    return MessageToDict(reply, preserving_proto_field_name=True)


@app.get("/health/live")
def health_live():
    return {"status": "ok"}


@app.get("/api/v1/bookings/{booking_id}")
def read_booking(booking_id: str, request: Request):
    return call_grpc(get_booking, booking_id, request)


@app.post("/api/v1/bookings/{booking_id}/confirm")
def confirm(booking_id: str, request: Request):
    return call_grpc(confirm_booking, booking_id, request)
