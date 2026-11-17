import logging
import os
import time
from concurrent import futures
from time import perf_counter

import grpc
from grpc_health.v1 import health, health_pb2, health_pb2_grpc
from grpc_reflection.v1alpha import reflection

import booking_pb2 as pb2
import booking_pb2_grpc as pb2_grpc
import repository

TEST_DELAY_MS = int(os.getenv("TEST_DELAY_MS", "0"))
TEST_FAIL_UNAVAILABLE = os.getenv("TEST_FAIL_UNAVAILABLE") == "1"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("booking-grpc")


def to_reply(item):
    return pb2.BookingReply(
        id=item.id, event_id=item.event_id, seat=item.seat,
        customer_id=item.customer_id, status=item.status,
        instance=os.getenv("HOSTNAME", "local"),
    )


def inject_test_faults(context):
    if TEST_FAIL_UNAVAILABLE:
        context.abort(grpc.StatusCode.UNAVAILABLE, "test: service unavailable")
    if TEST_DELAY_MS:
        time.sleep(TEST_DELAY_MS / 1000)


def logged(method):
    def wrapper(self, request, context):
        started = perf_counter()
        try:
            return method(self, request, context)
        finally:
            metadata = dict(context.invocation_metadata())
            log.info(
                "request_id=%s rpc_method=%s grpc_code=%s elapsed_ms=%.1f pod=%s attempt=%d",
                metadata.get("x-request-id", "-"),
                method.__name__,
                (context.code() or grpc.StatusCode.OK).name,
                (perf_counter() - started) * 1000,
                os.getenv("HOSTNAME", "local"),
                int(metadata.get("grpc-previous-rpc-attempts", "0")) + 1,
            )
    return wrapper


class BookingService(pb2_grpc.BookingServiceServicer):
    @logged
    def GetBooking(self, request, context):
        inject_test_faults(context)
        item = repository.get(request.id)
        if item is None:
            context.abort(grpc.StatusCode.NOT_FOUND, "booking not found")
        return to_reply(item)

    @logged
    def ConfirmBooking(self, request, context):
        inject_test_faults(context)
        if not request.id:
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, "id required")
        if repository.get(request.id) is None:
            context.abort(grpc.StatusCode.NOT_FOUND, "booking not found")
        if not context.is_active():
            context.abort(grpc.StatusCode.DEADLINE_EXCEEDED, "deadline exceeded before commit")
        if not repository.confirm(request.id):
            context.abort(grpc.StatusCode.FAILED_PRECONDITION, "booking is not in held status")
        return to_reply(repository.get(request.id))


def serve():
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    pb2_grpc.add_BookingServiceServicer_to_server(BookingService(), server)

    health_servicer = health.HealthServicer()
    health_pb2_grpc.add_HealthServicer_to_server(health_servicer, server)
    health_servicer.set("", health_pb2.HealthCheckResponse.SERVING)

    service_names = (
        pb2.DESCRIPTOR.services_by_name["BookingService"].full_name,
        health.SERVICE_NAME,
        reflection.SERVICE_NAME,
    )
    reflection.enable_server_reflection(service_names, server)
    server.add_insecure_port("[::]:50051")
    server.start()
    server.wait_for_termination()


if __name__ == "__main__":
    serve()
