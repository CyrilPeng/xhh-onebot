FROM docker.1ms.run/python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./

RUN pip install --upgrade pip \
    && pip install -r requirements.txt

COPY pyproject.toml README.md ./
COPY xhh_onebot ./xhh_onebot

RUN pip install --no-deps .

RUN mkdir -p /app/data

VOLUME ["/app/data"]

ENTRYPOINT ["python", "-m", "xhh_onebot"]
CMD ["start"]

