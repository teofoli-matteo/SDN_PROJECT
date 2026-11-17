#!/usr/bin/env python3
import argparse, csv, os, subprocess, time, re

RTT_RE = re.compile(r'time=([\d.]+) ms')


def ping_once(dst, timeout=1):
    try:
        out = subprocess.run(["ping", "-c", "1", "-W", str(timeout), dst],
                             capture_output=True, text=True, timeout=timeout + 1)
        m = RTT_RE.search(out.stdout)
        return float(m.group(1)) if m else None
    except Exception:
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--server", default="10.0.0.1")
    ap.add_argument("--alias-base", default="10.0.0.")
    ap.add_argument("--alias-start", type=int, default=101)
    ap.add_argument("--alias-count", type=int, default=150)
    ap.add_argument("--interval", type=float, default=1.0)
    ap.add_argument("--duration", type=int, default=0, help="0 = until Ctrl-C")
    ap.add_argument("--out", default="results/legit.csv")
    ap.add_argument("--scenario", default="run")
    a = ap.parse_args()

    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    fresh = not os.path.exists(a.out)
    f = open(a.out, "a", newline="")
    w = csv.writer(f)
    if fresh:
        w.writerow(["ts", "scenario", "steady_rtt_ms", "newconn_ms", "loss"])

    i = 0
    end = time.time() + a.duration if a.duration else None
    print(f"[legit] logging to {a.out} (scenario={a.scenario})")
    try:
        while end is None or time.time() < end:
            steady = ping_once(a.server)
            alias = a.alias_base + str(a.alias_start + (i % a.alias_count))
            newc = ping_once(alias)
            w.writerow([f"{time.time():.1f}", a.scenario,
                        steady if steady is not None else "",
                        newc if newc is not None else "",
                        0 if steady is not None else 1])
            f.flush()
            i += 1
            time.sleep(a.interval)
    except KeyboardInterrupt:
        pass
    finally:
        f.close()


if __name__ == '__main__':
    main()