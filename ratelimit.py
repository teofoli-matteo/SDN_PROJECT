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
            {"type": "OUTPUT", "port": "NORMAL"},
        ]},
        "selector": {"criteria": [{"type": "IN_PORT", "port": int(port)}]},
    }


def flow_body_forward_only(dev, port):
    return {
        "priority": PRIORITY, "isPermanent": True, "deviceId": dev,
        "treatment": {"instructions": [{"type": "OUTPUT", "port": "NORMAL"}]},
        "selector": {"criteria": [{"type": "IN_PORT", "port": int(port)}]},
    }


def _usable_id(mid):
    return mid is not None and str(mid) not in ("0", "None", "")


def find_meter_id(o, dev, rate):
    for _ in range(10):
        for m in o.get(f"/meters/{dev}").get("meters", []):
            mid = m.get("id")
            if _usable_id(mid) and any(
                    str(b.get("rate")) == str(rate) and b.get("type") == "DROP"
                    for b in m.get("bands", [])):
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
        raise SystemExit("[ratelimit] could not get a meter id -- OVS may not honor "
                         "OF1.3 meters. Use the OVS ingress-policing fallback (README).")
    print(f"[ratelimit] meter {meter_id} @ {rate} pkt/s on {dev}")
    o.post(f"/flows/{dev}?appId={APP}", flow_body(dev, port, meter_id))
    print(f"[ratelimit] port {port} capped to {rate} pkt/s")


def install_forward_only(o, dev, port):
    o.post(f"/flows/{dev}?appId={APP}", flow_body_forward_only(dev, port))
    print(f"[ratelimit] FORWARD-ONLY flow on port {port} (NORMAL, no meter) -- control run")


def remove(o, dev):
    # delete only OUR flows (by appId), and only the meters THOSE flows reference
    meter_ids = set()
    n = 0
    for f in o.get(f"/flows/{dev}").get("flows", []):
        if f.get("appId") == APP:
            for ins in f.get("treatment", {}).get("instructions", []):
                if ins.get("type") == "METER" and ins.get("meterId"):
                    meter_ids.add(str(ins["meterId"]))
            o.delete(f"/flows/{dev}/{f['id']}")
            n += 1
    m = 0
    for meter in o.get(f"/meters/{dev}").get("meters", []):
        if str(meter.get("id")) in meter_ids:
            try:
                o.delete(f"/meters/{dev}/{meter['id']}")
                m += 1
            except Exception:
                pass
    print(f"[ratelimit] removed {n} flow(s) and {m} meter(s) (ours only)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, required=True, help="attacker SWITCH port")
    ap.add_argument("--rate", type=int, default=200, help="allowed pkt/s")
    ap.add_argument("--install", action="store_true")
    ap.add_argument("--remove", action="store_true")
    ap.add_argument("--no-meter", action="store_true",
                    help="install the NORMAL forwarding flow without a meter (control)")
    a = ap.parse_args()

    o = Onos(host=a.host)
    dev = o.first_device()
    if a.remove:
        remove(o, dev)
    elif a.no_meter:
        install_forward_only(o, dev, a.port)
    else:
        install(o, dev, a.port, a.rate)


if __name__ == '__main__':
    main()