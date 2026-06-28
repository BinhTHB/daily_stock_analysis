#!/bin/bash
set -e

# Write IBC config from env (IBKR_USERNAME / IBKR_PASSWORD)
mkdir -p $HOME/ibc
cat > $HOME/ibc/config.ini <<EOF
[Settings]
IbLoginId=${IBKR_USERNAME}
IbPassword=${IBKR_PASSWORD}
PasswordEncrypted=no
StoreSettingsOnServer=no

[IBController]
IbControllerPort=7462
TradingMode=${IBKR_TRADING_MODE:-paper}
AcceptNonBrokerageSessions=yes
ClosedownAt=221500
MinimizeMainWindow=Yes

[Logging]
LogPath=/tmp
EOF

echo "IBC config written. Starting Xvfb + IB Gateway..."

# Virtual display (headless)
Xvfb :99 -screen 0 1280x1024x24 &
sleep 1
export DISPLAY=:99

# Start IB Gateway via IBC using gatewaystart.sh
GW_VER=$(ls /root/Jts/ibgateway/ 2>/dev/null | head -1)
TWS_MAJOR_VRSN=${GW_VER:-1045}
echo "Configuring gatewaystart.sh with Gateway version $TWS_MAJOR_VRSN..."
sed -i "s/TWS_MAJOR_VRSN=1019/TWS_MAJOR_VRSN=$TWS_MAJOR_VRSN/g" /opt/ibc/gatewaystart.sh
sed -i "s/TRADING_MODE=/TRADING_MODE=${IBKR_TRADING_MODE:-paper}/g" /opt/ibc/gatewaystart.sh

# Patch: do not block on 'read' when IBC errors — print log to stdout instead
sed -i 's/^read$/cat "${log_file}" 2>\/dev\/null; exit 1/' /opt/ibc/scripts/displaybannerandlaunch.sh

echo "IB Gateway $TWS_MAJOR_VRSN configured. Launching..."

/opt/ibc/gatewaystart.sh -inline &

# Wait until API port is ready (max 120s)
echo "Waiting for IB Gateway API port 4002..."
for i in $(seq 1 120); do
  if nc -z 127.0.0.1 4002 2>/dev/null; then
    echo "IB Gateway ready on port 4002 (attempt $i)"
    break
  fi
  sleep 1
done

# If port is still not open, print diagnostic logs
if ! nc -z 127.0.0.1 4002 2>/dev/null; then
  echo "❌ IB Gateway port 4002 not open! Printing IBC logs..."
  cat /root/ibc/logs/*.txt || true
  exit 1
fi

# Keep alive until closed (or timeout)
wait
