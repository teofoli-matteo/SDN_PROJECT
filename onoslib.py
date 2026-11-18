#!/usr/bin/env python3
import json, base64, urllib.request, urllib.error


class Onos:
    def __init__(self, host="127.0.0.1", port=8181, user="onos", pw="rocks"):
        self.base = f"http://{host}:{port}/onos/v1"
        tok = base64.b64encode(f"{user}:{pw}".encode()).decode()
        self.auth = "Basic " + tok

    def _req(self, method, path, body=None):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.base + path, data=data, method=method)
        req.add_header("Authorization", self.auth)
        req.add_header("Accept", "application/json")
        if data is not None:                       
            req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                raw = r.read().decode()
                return json.loads(raw) if raw.strip() else {}
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"{method} {path} -> {e.code} {e.read().decode()[:200]}")

    def get(self, path):            return self._req("GET", path)
    def post(self, path, body=None): return self._req("POST", path, body)
    def delete(self, path):         return self._req("DELETE", path)

    def first_device(self):
        devs = self.get("/devices").get("devices", [])
        if not devs:
            raise RuntimeError("No OpenFlow device yet -- is Mininet connected to ONOS?")
        return devs[0]["id"]

    def port_rx_packets(self, device_id, port):
        st = self.get(f"/statistics/ports/{device_id}/{port}")
        for s in st.get("statistics", []):
            for p in s.get("ports", []):
                if str(p.get("port")) == str(port):
                    return p.get("packetsReceived", 0)
        return None
