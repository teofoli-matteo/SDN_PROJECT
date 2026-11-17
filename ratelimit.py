#!/usr/bin/env python3
import argparse, time
from onoslib import Onos

APP = "org.saturation.ratelimit"
PRIORITY = 60000


def meter_body(dev, rate):
    return {"deviceId": dev, "unit": "PKTS_PER_SEC", "burst": False,
            "bands": [{"type": "DROP", "rate": int(rate), "burstSize": 0}]}


def flow_body(dev, port, meter_id):
    return {
        "priority": PRIORITY, "isPermanent": True, "deviceId": dev,
        "treatment": {"instructions": [
            {"type": "METER", "meterId": str(meter_id)},
            {"type": "OUTPUT", "port": "NORMAL"},   # forward in datapath, metered
        ]},
        "selector": {"criteria": [{"type": "IN_PORT", "port": int(port)}]},
    }


def _usable_id(mid):
    return mid is not None and str(mid) not in ("0", "None", "")


def find_meter_id(o, dev, rate):
    for _ in range(10):
        meters = o.get(f"/meters/{dev}").get("meters", [])
        for m in meters:
            mid = m.get("id")
            bands = m.get("bands", [])
            if _usable_id(mid) and any(
                    str(b.get("rate")) == str(rate) and b.get("type") == "DROP"
                    for b in bands):
                return str(mid)
        time.sleep(1)
    ids = [str(m.get("id")) for m in o.get(f"/meters/{dev}").get("meters", [])
           if _usable_id(m.get("id"))]
    return ids[-1] if ids else None


def install(o, dev, port, rate):
    resp = o.post(f"/meters/{dev}", meter_body(dev, rate))
    meter_id = str(resp.get("id")) if _usable_id(resp.get("id")) else None
    if not meter_id:
        meter_id = find_meter_id(o, dev, rate)
    if not meter_id:
        raise SystemExit(
            "[ratelimit] could not get a meter id -- your OVS probably does not "
            "honor OF1.3 meters. Use the OVS ingress-policing fallback (README).")
    print(f"[ratelimit] meter {meter_id} @ {rate} pkt/s on {dev}")
    o.post(f"/flows/{dev}?appId={APP}", flow_body(dev, port, meter_id))
    print(f"[ratelimit] port {port} capped to {rate} pkt/s")


def remove(o, dev):
    for f in o.get(f"/flows/{dev}").get("flows", []):
        if f.get("appId") == APP:
            o.delete(f"/flows/{dev}/{f['id']}")
    for m in o.get(f"/meters/{dev}").get("meters", []):
        try:
            o.delete(f"/meters/{dev}/{m['id']}")
        except Exception:
            pass
    print("[ratelimit] removed meter + flow")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, required=True, help="attacker SWITCH port")
    ap.add_argument("--rate", type=int, default=200, help="allowed pkt/s")
    ap.add_argument("--install", action="store_true")
    ap.add_argument("--remove", action="store_true")
    a = ap.parse_args()

    o = Onos(host=a.host)
    dev = o.first_device()
    if a.remove:
        remove(o, dev)
    else:
        install(o, dev, a.port, a.rate)


if __name__ == '__main__':
    main()
