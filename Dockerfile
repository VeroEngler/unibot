FROM python:3.12-slim

LABEL maintainer="VeroEngler"
LABEL description="UNAHUR Discord Community Bot"

# Evita archivos .pyc y asegura salida inmediata de logs en stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Capa de dependencias (aprovecha caché de Docker si requirements.txt no cambia)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Usuario no-root por seguridad
RUN useradd --create-home --shell /bin/bash botuser

# Copia del código fuente y archivos de configuración
COPY --chown=botuser:botuser . .

USER botuser

CMD ["python", "main.py"]