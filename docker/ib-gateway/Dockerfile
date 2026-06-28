# Stable IB Gateway Docker with IBC for unattended login.
FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

# Install dependencies
RUN apt-get update && apt-get install -y \
    wget \
    unzip \
    xvfb \
    libxrender1 \
    libxtst6 \
    libxi6 \
    socat \
    netcat-openbsd \
    python3 \
    && rm -rf /var/lib/apt/lists/*

# Install IB Gateway
WORKDIR /opt
RUN wget -q https://download2.interactivebrokers.com/installers/ibgateway/stable-standalone/ibgateway-stable-standalone-linux-x64.sh -O ibgateway.sh \
    && chmod +x ibgateway.sh \
    && yes "" | ./ibgateway.sh \
    && rm ibgateway.sh

# Install IBC
RUN wget -q https://github.com/IbcAlpha/IBC/releases/download/3.18.0/IBCLinux-3.18.0.zip -O ibc.zip \
    && mkdir -p /opt/ibc \
    && unzip ibc.zip -d /opt/ibc \
    && rm ibc.zip \
    && chmod +x /opt/ibc/*.sh /opt/ibc/bin/*.sh

# Configuration templates
COPY config.ini /opt/ibc/config.ini
COPY entrypoint.sh /opt/entrypoint.sh
RUN chmod +x /opt/entrypoint.sh

EXPOSE 4001 4002

ENTRYPOINT ["/opt/entrypoint.sh"]
