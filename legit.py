#!/usr/bin/env python3
import argparse, csv, os, subprocess, time, re

# \s also matches the non-breaking space some ping versions print before "ms".
RTT_RE = re.compile(r'time=([\d.]+)\s*ms')
# ping output is localised ("temps=" in French); force the C locale.
PING_ENV = {**os.environ, "LC_ALL": "C", "LANG": "C"}


def ping_once(dst, timeout=1):
    try:
        out = subprocess.run(["ping", "-c", "1", "-W", str(timeout), dst],
                             capture_output=True, text=True, timeout=timeout + 1,
                             env=PING_ENV)
        m = RTT_RE.search(out.stdout)
        return float(m.group(1)) if m else None
    except Exception:
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--server", default="10.0.0.1")
    ap.add_argument("--interval", type=float, default=1.0)
    ap.add_argument("--duration", type=int, default=0, help="0 = until Ctrl-C")
    ap.add_argument("--out", default="results/legit.csv")
    ap.add_argument("--scenario", default="run")
    ap.add_argument("--rep", type=int, default=1)
    a = ap.parse_args()

    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    fresh = not os.path.exists(a.out)
    f = open(a.out, "a", newline="")
    w = csv.writer(f)
    if fresh:
        w.writerow(["ts", "scenario", "rep", "elapsed", "steady_rtt_ms", "loss"])

    start = time.monotonic()
    end = start + a.duration if a.duration else None
    print(f"[legit] -> {a.out} (scenario={a.scenario} rep={a.rep})")
    try:
        while end is None or time.monotonic() < end:
            rtt = ping_once(a.server)
            elapsed = round(time.monotonic() - start, 1)
            w.writerow([f"{time.time():.1f}", a.scenario, a.rep, elapsed,
                        rtt if rtt is not None else "",
                        0 if rtt is not None else 1])
            f.flush()
            time.sleep(a.interval)
    except KeyboardInterrupt:
        pass
    finally:
        f.close()


if __name__ == '__main__':
    main()