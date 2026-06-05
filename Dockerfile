ARG PYTHON_IMAGE=docker.m.daocloud.io/library/python:3.12-slim
FROM ${PYTHON_IMAGE} AS runtime

ARG DEBIAN_MIRROR=http://mirrors.tuna.tsinghua.edu.cn

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple \
    PIP_TRUSTED_HOST=pypi.tuna.tsinghua.edu.cn

WORKDIR /app

RUN set -eux; \
    if [ -f /etc/apt/sources.list.d/debian.sources ]; then \
        sed -i \
            -e "s|http://deb.debian.org/debian|${DEBIAN_MIRROR}/debian|g" \
            -e "s|http://deb.debian.org/debian-security|${DEBIAN_MIRROR}/debian-security|g" \
            -e "s|http://security.debian.org/debian-security|${DEBIAN_MIRROR}/debian-security|g" \
            /etc/apt/sources.list.d/debian.sources; \
    fi; \
    if [ -f /etc/apt/sources.list ]; then \
        sed -i \
            -e "s|http://deb.debian.org/debian|${DEBIAN_MIRROR}/debian|g" \
            -e "s|http://deb.debian.org/debian-security|${DEBIAN_MIRROR}/debian-security|g" \
            -e "s|http://security.debian.org/debian-security|${DEBIAN_MIRROR}/debian-security|g" \
            /etc/apt/sources.list; \
    fi; \
    apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates git \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./

RUN pip install --upgrade pip \
    && pip install -r requirements.txt

COPY pyproject.toml README.md ./
COPY xhh_onebot ./xhh_onebot
COPY scripts ./scripts

RUN pip install --no-deps .

RUN mkdir -p /app/data \
    && chmod +x /app/scripts/docker-hot-update.sh \
    && ln -sf /app/scripts/docker-hot-update.sh /usr/local/bin/xhh-update

VOLUME ["/app/data"]

ENTRYPOINT ["python", "-m", "xhh_onebot"]
CMD ["start"]

