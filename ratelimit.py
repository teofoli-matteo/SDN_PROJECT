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


def _find_matching_meter(o, dev, rate):
    """A usable meter already carrying exactly this DROP rate, if any."""
    for m in o.get(f"/meters/{dev}").get("meters", []):
        mid = m.get("id")
        if _usable_id(mid) and any(
                str(b.get("rate")) == str(rate) and b.get("type") == "DROP"
                for b in m.get("bands", [])):
            return _meter_id_decimal(mid)
    return None


def _create_meter(o, dev, rate, settle=12):
    """POST the meter ONCE, then read the id back from the meter list.
    ONOS 2.7 answers 201 with an EMPTY body, so the id is never in the POST
    response. Re-POSTing (the old behaviour) just created duplicate meters and
    wasted ~15s per call, which also caused the 21s detection outliers."""
    try:
        o.post(f"/meters/{dev}", meter_body(dev, rate))
    except RuntimeError as e:
        print(f"[ratelimit] meter POST returned an error ({e}); reading meters back anyway")
    for _ in range(settle):
        mid = _find_matching_meter(o, dev, rate)
        if mid is not None:
            return mid
        time.sleep(1)
    return None


def _wait_added(o, dev, app, tries=60, delay=0.5):
    """Wait until OUR flow is actually ADDED on the switch (not PENDING_ADD)."""
    for _ in range(tries):
        for f in o.get(f"/flows/{dev}").get("flows", []):
            if f.get("appId") == app and f.get("state") == "ADDED":
                return True
        time.sleep(delay)
    return False


def install(o, dev, port, rate):
    # reuse an identical leftover meter if there is one, else create
    meter_id = _find_matching_meter(o, dev, rate)
    if meter_id is None:
        meter_id = _create_meter(o, dev, rate)
    if not meter_id:
        raise SystemExit("[ratelimit] could not get a meter id -- OVS may not honor "
                         "OF1.3 meters. Use the OVS ingress-policing fallback (README).")
    print(f"[ratelimit] meter {meter_id} @ {rate} pkt/s on {dev}")
    o.post(f"/flows/{dev}?appId={APP}", flow_body(dev, port, meter_id))
    if _wait_added(o, dev, APP):
        print(f"[ratelimit] port {port} capped to {rate} pkt/s")
        return
    raise SystemExit("[ratelimit] flow never reached ADDED state on the switch")


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