#!/usr/bin/env python3
import argparse, csv, os, time, collections
from onoslib import Onos
import block, ratelimit


def port_rx_map(o, dev):
    out = {}
    st = o.get(f"/statistics/ports/{dev}")
    for s in st.get("statistics", []):
        for p in s.get("ports", []):
            port = p.get("port")
            if str(port).isdigit():
                out[int(port)] = p.get("packetsReceived", 0)
    return out


def mitigate(o, dev, port, defense, rate):
    if defense == "block":
        block.install(o, dev, port)
    else:
        ratelimit.install(o, dev, port, rate)


def mitigation_present(o, dev, defense):
    app = block.APP if defense == "block" else ratelimit.APP
    return any(f.get("appId") == app and f.get("state") in (None, "ADDED", "PENDING_ADD")
               for f in o.get(f"/flows/{dev}").get("flows", []))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--defense", choices=["block", "ratelimit"], default="ratelimit")
    ap.add_argument("--rate", type=int, default=150, help="cap for rate limiting")
    ap.add_argument("--threshold", type=int, default=300, help="pkt/s to trigger")
    ap.add_argument("--window", type=float, default=10.0,
                    help="seconds of history to average the rate over")
    ap.add_argument("--interval", type=float, default=1.0)
    ap.add_argument("--duration", type=int, default=60)
    ap.add_argument("--once", action="store_true", help="exit after first mitigation")
    ap.add_argument("--out", default="")
    ap.add_argument("--label", default="run")
    a = ap.parse_args()

    o = Onos(host=a.host)
    dev = o.first_device()
    hist = collections.deque()
    start = time.time()
    triggered = False
    detect_s = mitig_s = hit_port = hit_rate = verified = ""

    print(f"[detector] watching {dev}, threshold {a.threshold} pkt/s, "
          f"window {a.window}s, defense={a.defense}")
    while time.time() - start < a.duration:
        now = time.time()
        cur = port_rx_map(o, dev)
        hist.append((now, cur))
        while len(hist) > 1 and now - hist[0][0] > a.window:
            hist.popleft()
        t0, old = hist[0]
        span = now - t0
        if span >= a.window * 0.6:
            for port, rx in cur.items():
                if port not in old:
                    continue
                rate = (rx - old[port]) / span
                if rate > a.threshold and not triggered:
                    detect_s = round(now - start, 2)
                    hit_port, hit_rate = port, round(rate)
                    print(f"[detector] ATTACK on port {port}: {rate:.0f} pkt/s "
                          f"(detected at {detect_s}s)")
                    mitigate(o, dev, port, a.defense, a.rate)
                    mitig_s = round(time.time() - start, 2)
                    time.sleep(0.5)
                    verified = int(mitigation_present(o, dev, a.defense))
                    triggered = True
                    print(f"[detector] mitigated with {a.defense} at {mitig_s}s "
                          f"(flow verified: {bool(verified)})")
                    break
        if triggered and a.once:
            break
        time.sleep(a.interval)

    if a.out:
        os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
        fresh = not os.path.exists(a.out)
        with open(a.out, "a", newline="") as f:
            w = csv.writer(f)
            if fresh:
                w.writerow(["label", "threshold", "defense", "triggered",
                            "detect_s", "mitigate_s", "verified", "port", "rate_pkts"])
            w.writerow([a.label, a.threshold, a.defense, int(triggered),
                        detect_s, mitig_s, verified, hit_port, hit_rate])
    if not triggered:
        print(f"[detector] no attack detected (threshold {a.threshold} pkt/s)")


if __name__ == "__main__":
    main()