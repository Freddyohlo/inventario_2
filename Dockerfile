# Bodega — imagen de la app para correrla en cualquier lado.
# Multi-stage: se instalan las dependencias en un builder y solo se copian al
# runtime, que corre como usuario sin privilegios.
FROM python:3.12-slim AS builder

WORKDIR /build
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt


FROM python:3.12-slim

# Usuario sin privilegios: la app no necesita root para nada.
RUN useradd --create-home --uid 10001 appuser
ENV PATH="/install/bin:${PATH}" \
    PYTHONPATH="/install/lib/python3.12/site-packages" \
    PYTHONUNBUFFERED=1 \
    DB_PATH=/app/data/inventario.db
COPY --from=builder /install /install

WORKDIR /app
COPY app ./app
COPY static ./static
COPY scripts ./scripts

# El directorio de datos queda escribible por el usuario de la app.
RUN mkdir -p /app/data && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s \
    CMD python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8000/health').read()" || exit 1

# Siembra datos de ejemplo solo si la base está vacía, y luego arranca.
CMD ["sh", "-c", "python -m app.seed && uvicorn app.api:app --host 0.0.0.0 --port 8000"]
