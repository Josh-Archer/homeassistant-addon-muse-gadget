FROM debian:bookworm-slim

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

# Install system dependencies including BlueZ, D-Bus, and Python bindings
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    python3-pip \
    python3-venv \
    python3-dbus \
    python3-gi \
    bluez \
    curl \
    jq \
    git \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Create unprivileged muse user for safe command execution
RUN useradd -m -s /bin/bash muse

# Install Meta Muse Gadget Linux SDK
RUN pip3 install --break-system-packages \
    git+https://github.com/facebookincubator/muse-gadget-sdk.git#subdirectory=linux

WORKDIR /app

# Copy add-on logic and scripts
COPY ble_patch.py /app/ble_patch.py
COPY ha_bridge.py /app/ha_bridge.py
COPY entrypoint.py /app/entrypoint.py
COPY ha-ctl /usr/local/bin/ha-ctl
COPY muse-notify /usr/local/bin/muse-notify

RUN chmod +x /app/entrypoint.py /usr/local/bin/ha-ctl /usr/local/bin/muse-notify \
    && mkdir -p /data \
    && chown -R muse:muse /data

EXPOSE 8099

ENTRYPOINT ["python3", "-u", "/app/entrypoint.py"]
