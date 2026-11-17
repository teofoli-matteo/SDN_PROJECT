#!/usr/bin/env bash
# Launch a RESOURCE-LIMITED ONOS controller in Docker and activate the apps
# we need for REACTIVE forwarding (so every new flow hits the control plane).
#
# The CPU cap is the whole point of the experiment: a constrained control plane
# saturates at a few hundred Packet-In/s instead of needing millions. Lower
# CPU_LIMIT => saturates sooner. Keep MEM_LIMIT >= 1.5g or the JVM won't boot.
set -euo pipefail

ONOS_VERSION="${ONOS_VERSION:-2.7-latest}"
CPU_LIMIT="${CPU_LIMIT:-1.0}"     # cores for ONOS  (try 0.5 if you want it fragile)
MEM_LIMIT="${MEM_LIMIT:-2g}"
NAME="${NAME:-onos}"

echo "[start_onos] (re)starting container '$NAME' cpus=$CPU_LIMIT mem=$MEM_LIMIT"
docker rm -f "$NAME" >/dev/null 2>&1 || true

docker run -d --name "$NAME" \
  --cpus="$CPU_LIMIT" \
  --memory="$MEM_LIMIT" \
  -p 6653:6653 -p 8181:8181 -p 8101:8101 \
  onosproject/onos:"$ONOS_VERSION" >/dev/null

echo "[start_onos] waiting for the REST API (can take ~30-60s on first boot)..."
for i in $(seq 1 60); do
  if curl -s -u onos:rocks http://localhost:8181/onos/v1/devices >/dev/null 2>&1; then
    echo "[start_onos] REST is up."
    break
  fi
  sleep 3
done

# openflow = speak OpenFlow to the switches ; fwd = reactive forwarding
curl -s -u onos:rocks -X POST \
  http://localhost:8181/onos/v1/applications/org.onosproject.openflow/active >/dev/null
curl -s -u onos:rocks -X POST \
  http://localhost:8181/onos/v1/applications/org.onosproject.fwd/active >/dev/null

echo "[start_onos] activated org.onosproject.openflow + org.onosproject.fwd"
echo "[start_onos] controller IP for Mininet = 127.0.0.1 (same host) on port 6653"