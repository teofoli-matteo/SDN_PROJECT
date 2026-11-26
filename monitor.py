#!/usr/bin/env python3
import argparse, base64, csv, os, re, subprocess, time, urllib.request

REST_TIMEOUT_S = 5
REST_TIMEOUT_MS = REST_TIMEOUT_S * 1000


def container_cpu_usage_u(cnt):
    """cgroup v2 CPU accounting of the container, in usec.

    `docker stats --no-stream` is CPU averaged since container start on some
    podman deployments, which makes it useless for sampling. The cgroup counter
    is exact and works the same for Docker and podman. Returns None if the
    container or its cgroup cannot be found."""
    try:
        r = subprocess.run(
            ["docker", "inspect", "--format", "{{.State.Pid}}", cnt],
            capture_output=True, text=True, timeout=10)
        pid = r.stdout.strip()
        if r.returncode != 0 or not pid.isdigit() or pid == "0":
            return None
        with open(f"/proc/{pid}/cgroup") as cg:
            line = cg.read().strip().splitlines()[0]
        rel = line.split("::", 1)[1] if "::" in line else line.split(":", 2)[-1]
        with open(f"/sys/fs/cgroup{rel}/cpu.stat") as f:
            for l in f:
                if l.startswith("usage_usec"):
                    return int(l.split()[1])
    except Exception:
        return None
    return None


def cpu_pct_from_cgroup(cnt, prev_usage, prev_t):
    """Instantaneous CPU % of one core between two cgroup samples, or None."""
    now = time.monotonic()
    usage = container_cpu_usage_u(cnt)
    if usage is None or prev_usage is None or now <= prev_t:
        return usage, now, None
    pct = (usage - prev_usage) / ((now - prev_t) * 1.0e6) * 100.0
    return usage, now, pct


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

    start = time.monotonic()
    end = start + a.duration if a.duration else None
    print(f"[monitor] {a.name} -> {a.out} (scenario={a.scenario} rep={a.rep})")
    prev_usage, prev_t, _ = cpu_pct_from_cgroup(a.name, None, 0.0)
    try:
        while end is None or time.monotonic() < end:
            prev_usage, prev_t, cpu = cpu_pct_from_cgroup(a.name, prev_usage, prev_t)
            s = docker_sample(a.name)   # memory (deltas not needed)
            rest = rest_latency_ms(url, auth)
            elapsed = round(time.monotonic() - start, 1)
            if cpu is None and s:
                cpu = s[0]              # fallback (Docker without cgroup v2)
            if cpu is not None and s:
                w.writerow([f"{time.time():.1f}", a.scenario, a.rep, elapsed,
                            round(float(cpu), 2), mem_to_mb(s[1]), s[2], rest])
                f.flush()
                print(f"[monitor] t={elapsed:5.1f}s CPU {cpu:>6}%  REST {rest} ms")
            time.sleep(a.interval)
    except KeyboardInterrupt:
        pass
    finally:
        f.close()


if __name__ == '__main__':
    main()