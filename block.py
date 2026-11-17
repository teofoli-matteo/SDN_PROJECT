#!/usr/bin/env python3
import argparse, time
from onoslib import Onos

APP = "org.saturation.block"
PRIORITY = 60000


def flow_body(device_id, port):
    return {
        "priority": PRIORITY, "isPermanent": True, "deviceId": device_id,
        "treatment": {"instructions": []},                
        "selector": {"criteria": [{"type": "IN_PORT", "port": int(port)}]},
    }


def install(o, dev, port):
    o.post(f"/flows/{dev}?appId={APP}", flow_body(dev, port))
    print(f"[block] DROP rule installed on {dev} in_port={port}")


def remove(o, dev):
    n = 0
    for f in o.get(f"/flows/{dev}").get("flows", []):
        if f.get("appId") == APP:
            o.delete(f"/flows/{dev}/{f['id']}")
            n += 1
    print(f"[block] removed {n} rule(s)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1", help="ONOS REST host")
    ap.add_argument("--port", type=int, required=True, help="attacker SWITCH port")
    ap.add_argument("--install", action="store_true")
    ap.add_argument("--remove", action="store_true")
    ap.add_argument("--auto", action="store_true", help="watch rate, trigger itself")
    ap.add_argument("--threshold", type=int, default=300, help="pkt/s to trigger")
    a = ap.parse_args()

    o = Onos(host=a.host)
    dev = o.first_device()

    if a.remove:
        remove(o, dev); return
    if a.install:
        install(o, dev, a.port); return
    if a.auto:
        print(f"[block] watching {dev} port {a.port}, threshold {a.threshold} pkt/s")
        prev = o.port_rx_packets(dev, a.port); t0 = time.time()
        while True:
            time.sleep(1)
            cur = o.port_rx_packets(dev, a.port); t1 = time.time()
            if prev is not None and cur is not None:
                rate = (cur - prev) / (t1 - t0)
                print(f"[block] port {a.port} rx {rate:.0f} pkt/s")
                if rate > a.threshold:
                    install(o, dev, a.port); return
            prev, t0 = cur, t1


if __name__ == '__main__':
    main()