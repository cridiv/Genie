FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src:/app

WORKDIR /app

# System libraries for OpenCV, pyzbar (libzbar0), and pylibdmtx (libdmtx0b)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    libglib2.0-0 \
    libgomp1 \
    libzbar0 \
    libdmtx0b \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY src ./src
COPY training ./training
COPY configs ./configs

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir --only-binary=:all: opencv-python-headless numpy scipy scikit-learn onnxruntime \
    && pip install --no-cache-dir . aiosqlite greenlet

EXPOSE 8000

CMD ["uvicorn", "genie.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
