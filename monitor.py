#!/usr/bin/env python3
import argparse, csv, os, subprocess, time


def sample(name):
    out = subprocess.run(
        ["docker", "stats", "--no-stream",
         "--format", "{{.CPUPerc}};{{.MemUsage}};{{.MemPerc}}", name],
        capture_output=True, text=True)
    line = out.stdout.strip()
    if not line:
        return None
    try:
        cpu, mem, memp = line.split(";")
    except ValueError:
        return None
    return cpu.strip().rstrip("%"), mem.strip(), memp.strip().rstrip("%")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", default="onos")
    ap.add_argument("--interval", type=float, default=1.0)
    ap.add_argument("--duration", type=int, default=0, help="0 = until Ctrl-C")
    ap.add_argument("--out", default="results/onos.csv")
    ap.add_argument("--scenario", default="run")
    a = ap.parse_args()

    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    fresh = not os.path.exists(a.out)
    f = open(a.out, "a", newline="")
    w = csv.writer(f)
    if fresh:
        w.writerow(["ts", "scenario", "cpu_pct", "mem_usage", "mem_pct"])

    end = time.time() + a.duration if a.duration else None
    print(f"[monitor] {a.name} -> {a.out} (scenario={a.scenario})")
    try:
        while end is None or time.time() < end:
            s = sample(a.name)
            if s:
                w.writerow([f"{time.time():.1f}", a.scenario, s[0], s[1], s[2]])
                f.flush()
                print(f"[monitor] CPU {s[0]}%  MEM {s[1]} ({s[2]}%)")
            time.sleep(a.interval)
    except KeyboardInterrupt:
        pass
    finally:
        f.close()


if __name__ == '__main__':
    main()