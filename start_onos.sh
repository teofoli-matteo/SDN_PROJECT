#!/usr/bin/env bash
set -euo pipefail

ONOS_VERSION="${ONOS_VERSION:-2.7-latest}"
# docker.io/ prefix also works with podman (avoids short-name resolution errors)
ONOS_IMAGE="${ONOS_IMAGE:-docker.io/onosproject/onos}"
# The image activates ONOS_APPS at boot via onos-service. Keep the apps the
# experiment needs; add gui2 if you want the web UI: openflow,fwd,gui2
ONOS_APPS="${ONOS_APPS:-openflow,fwd}"
CPU_LIMIT="${CPU_LIMIT:-1.0}"     # cores for ONOS  (try 0.5 if you want it fragile)
MEM_LIMIT="${MEM_LIMIT:-2g}"
NAME="onos"
REST="http://localhost:8181/onos/v1"

echo "[start_onos] (re)starting container '$NAME' cpus=$CPU_LIMIT mem=$MEM_LIMIT"
docker rm -f "$NAME" >/dev/null 2>&1 || true

docker run -d --name "$NAME" \
  --cpus="$CPU_LIMIT" \
  --memory="$MEM_LIMIT" \
  -e ONOS_APPS="$ONOS_APPS" \
  -p 6653:6653 -p 8181:8181 -p 8101:8101 \
  "$ONOS_IMAGE:$ONOS_VERSION" >/dev/null

echo "[start_onos] waiting for the REST API (can take ~30-120s on first boot)..."
ready=0
for _ in $(seq 1 60); do
  # -f is essential: without it curl succeeds on 404/503 and we would start too early
  if curl -sf -u onos:rocks "$REST/devices" >/dev/null 2>&1; then
    ready=1
    break
  fi
  sleep 3
done
if [ "$ready" -ne 1 ]; then
  echo "[start_onos] ERROR: REST API not ready after 180s." >&2
  docker logs --tail 80 "$NAME" >&2 || true
  exit 1
fi
echo "[start_onos] REST is up."

app_state() {
  curl -s -u onos:rocks "$REST/applications/$1" 2>/dev/null \
    | python3 -c 'import json, sys
try:
    print(json.load(sys.stdin).get("state", ""))
except Exception:
    print("")' 2>/dev/null || echo ""
}

# Safety net for images that do not honour ONOS_APPS.
for app in openflow fwd; do
  if [ "$(app_state "org.onosproject.$app")" != "ACTIVE" ]; then
    echo "[start_onos] activating org.onosproject.$app via REST"
    curl -sf -u onos:rocks -X POST \
      "$REST/applications/org.onosproject.$app/active" >/dev/null || true
  fi
done

# Never claim success without checking the state.
active=0
for _ in $(seq 1 30); do
  active=1
  for app in openflow fwd; do
    if [ "$(app_state "org.onosproject.$app")" != "ACTIVE" ]; then
      active=0
    fi
  done
  if [ "$active" -eq 1 ]; then
    echo "[start_onos] org.onosproject.openflow + org.onosproject.fwd are ACTIVE"
    break
  fi
  sleep 2
done
if [ "$active" -ne 1 ]; then
  echo "[start_onos] ERROR: required applications did not reach ACTIVE state." >&2
  for app in openflow fwd; do
    echo "  org.onosproject.$app = $(app_state "org.onosproject.$app")" >&2
  done
  docker logs --tail 80 "$NAME" >&2 || true
  exit 1
fi

echo "[start_onos] controller IP for Mininet = 127.0.0.1 (same host) on port 6653"
