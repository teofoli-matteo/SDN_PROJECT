#!/usr/bin/env python3
import argparse, base64, csv, os, re, subprocess, time, urllib.request

REST_TIMEOUT_S = 5
REST_TIMEOUT_MS = REST_TIMEOUT_S * 1000


def docker_sample(name):
    out = subprocess.run(
        ["docker", "stats", "--no-stream",
         "--format", "{{.CPUPerc}};{{.MemUsage}};{{.MemPerc}}", name],
        capture_output=True, text=True)
    line = out.stdout.strip()
    if not line or ";" not in line:
        return None
    cpu, mem, memp = line.split(";")
    return cpu.strip().rstrip("%"), mem.strip(), memp.strip().rstrip("%")


def mem_to_mb(mem_usage):
    used = mem_usage.split("/")[0].strip()         
    try:
        num = float(re.findall(r"[\d.]+", used)[0])
        unit = re.findall(r"[A-Za-z]+", used)[0].lower()
    except IndexError:
        return ""
    if unit.startswith("g"):
        return round(num * 1024, 1)
    if unit.startswith("m"):
        return round(num, 1)
    if unit.startswith("k"):
        return round(num / 1024, 1)
    return round(num / 1024 / 1024, 1)               


def rest_latency_ms(url, auth):
    t = time.monotonic()
    try:
        req = urllib.request.Request(url)
        req.add_header("Authorization", auth)
        urllib.request.urlopen(req, timeout=REST_TIMEOUT_S).read()
        return round((time.monotonic() - t) * 1000, 1)
    except Exception:
        return REST_TIMEOUT_MS                       

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", default="onos")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--interval", type=float, default=1.0)
    ap.add_argument("--duration", type=int, default=0, help="0 = until Ctrl-C")
    ap.add_argument("--out", default="results/onos.csv")
    ap.add_argument("--scenario", default="run")
    ap.add_argument("--rep", type=int, default=1)
    a = ap.parse_args()

    url = f"http://{a.host}:8181/onos/v1/devices"
    auth = "Basic " + base64.b64encode(b"onos:rocks").decode()

    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    fresh = not os.path.exists(a.out)
    f = open(a.out, "a", newline="")
    w = csv.writer(f)
    if fresh:
        w.writerow(["ts", "scenario", "rep", "elapsed", "cpu_pct", "mem_mb",
                    "mem_pct", "rest_ms"])

    start = time.time()
    end = start + a.duration if a.duration else None
    print(f"[monitor] {a.name} -> {a.out} (scenario={a.scenario} rep={a.rep})")
    try:
        while end is None or time.time() < end:
            s = docker_sample(a.name)
            rest = rest_latency_ms(url, auth)
            elapsed = round(time.time() - start, 1)
            if s:
                w.writerow([f"{time.time():.1f}", a.scenario, a.rep, elapsed,
                            s[0], mem_to_mb(s[1]), s[2], rest])
                f.flush()
                print(f"[monitor] t={elapsed:5.1f}s CPU {s[0]:>6}%  REST {rest} ms")
            time.sleep(a.interval)
    except KeyboardInterrupt:
        pass
    finally:
        f.close()


if __name__ == '__main__':
    main()