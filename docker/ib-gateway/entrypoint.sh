#!/bin/bash
set -e

# Write IBC config from env (IBKR_USERNAME / IBKR_PASSWORD)
cat > /opt/ibc/config.ini <<EOF
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

# Start IB Gateway via IBC
/opt/ibc/bin/ibcstart.sh --tws-path=/root/IBGateway --user-home=/root --mode=bot &

# Wait until API port is ready (max 120s)
echo "Waiting for IB Gateway API port 4002..."
for i in $(seq 1 120); do
  if nc -z 127.0.0.1 4002 2>/dev/null; then
    echo "IB Gateway ready on port 4002 (attempt $i)"
    break
  fi
  sleep 1
done

# Keep alive until closed (or timeout)
wait
