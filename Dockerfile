FROM python:3.12-slim-bullseye

ARG DEBIAN_MIRROR=https://mirrors.aliyun.com

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN printf '%s\n' \
        "deb ${DEBIAN_MIRROR}/debian bullseye main" \
        "deb ${DEBIAN_MIRROR}/debian bullseye-updates main" \
        "deb ${DEBIAN_MIRROR}/debian-security bullseye-security main" \
        > /etc/apt/sources.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl unixodbc-dev \
    && curl -fsSLo /tmp/packages-microsoft-prod.deb \
        https://packages.microsoft.com/config/debian/11/packages-microsoft-prod.deb \
    && dpkg -i /tmp/packages-microsoft-prod.deb \
    && rm -f /tmp/packages-microsoft-prod.deb \
    && apt-get update \
    && ACCEPT_EULA=Y apt-get install -y --no-install-recommends msodbcsql18 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN python -m pip install --upgrade pip \
    && python -m pip install -r requirements.txt

COPY main.py ./
COPY src ./src

EXPOSE 8000

CMD ["python", "main.py"]
