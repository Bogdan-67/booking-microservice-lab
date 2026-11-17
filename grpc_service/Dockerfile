FROM python:3.12-slim AS codegen
RUN pip install --no-cache-dir grpcio-tools==1.85.1
WORKDIR /src
COPY proto/ ./proto/
RUN mkdir /out && python -m grpc_tools.protoc -I proto --python_out=/out --grpc_python_out=/out proto/booking.proto

FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY grpc_service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY grpc_service/*.py ./
COPY --from=codegen /out/ ./
EXPOSE 50051
CMD ["python", "server.py"]
