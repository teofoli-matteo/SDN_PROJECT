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


def _meter_id_decimal(mid):
    """ONOS serialises MeterId with toString() (hex); the REST flow/delete
    endpoints parse the id as a decimal long."""
    s = str(mid)
    try:
        return int(s, 16)
    except ValueError:
        return int(s)


def find_meter_id(o, dev, rate):
    for _ in range(10):
        for m in o.get(f"/meters/{dev}").get("meters", []):
            mid = m.get("id")
            if _usable_id(mid) and any(
                    str(b.get("rate")) == str(rate) and b.get("type") == "DROP"
                    for b in m.get("bands", [])):
                return _meter_id_decimal(mid)
        time.sleep(1)
    ids = []
    for m in o.get(f"/meters/{dev}").get("meters", []):
        try:
            if _usable_id(m.get("id")):
                ids.append(_meter_id_decimal(m["id"]))
        except (TypeError, ValueError):
            pass
    return ids[-1] if ids else None


def install(o, dev, port, rate):
    resp = o.post(f"/meters/{dev}", meter_body(dev, rate))
    raw_id = resp.get("id") if isinstance(resp, dict) else None
    meter_id = _meter_id_decimal(raw_id) if _usable_id(raw_id) else None
    if meter_id is None:
        meter_id = find_meter_id(o, dev, rate)
    if not meter_id:
        raise SystemExit("[ratelimit] could not get a meter id -- OVS may not honor "
                         "OF1.3 meters. Use the OVS ingress-policing fallback (README).")
    print(f"[ratelimit] meter {meter_id} @ {rate} pkt/s on {dev}")
    o.post(f"/flows/{dev}?appId={APP}", flow_body(dev, port, meter_id))
    for _ in range(6):
        if any(f.get("appId") == APP for f in o.get(f"/flows/{dev}").get("flows", [])):
            print(f"[ratelimit] port {port} capped to {rate} pkt/s")
            return
        time.sleep(0.5)
    raise SystemExit("[ratelimit] ONOS accepted the request but no flow is present")


def install_forward_only(o, dev, port):
    o.post(f"/flows/{dev}?appId={APP}", flow_body_forward_only(dev, port))
    print(f"[ratelimit] FORWARD-ONLY flow on port {port} (NORMAL, no meter) -- control run")


def remove(o, dev):
    # delete only OUR flows (by appId), and only the meters THOSE flows reference
    # (ids are normalised with _meter_id_decimal: ONOS mixes hex and decimal)
    meter_ids = set()
    n = 0
    for f in o.get(f"/flows/{dev}").get("flows", []):
        if f.get("appId") == APP:
            for ins in f.get("treatment", {}).get("instructions", []):
                if ins.get("type") == "METER" and ins.get("meterId"):
                    try:
                        meter_ids.add(_meter_id_decimal(ins["meterId"]))
                    except (TypeError, ValueError):
                        pass
            o.delete(f"/flows/{dev}/{f['id']}")
            n += 1
    m = 0
    for meter in o.get(f"/meters/{dev}").get("meters", []):
        if not _usable_id(meter.get("id")):
            continue
        if _meter_id_decimal(meter["id"]) in meter_ids:
            try:
                o.delete(f"/meters/{dev}/{_meter_id_decimal(meter['id'])}")
                m += 1
            except Exception as e:
                print(f"[ratelimit] could not delete meter {meter.get('id')}: {e}")
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