#!/usr/bin/env python3
import argparse, os, subprocess, sys, time
from mininet.net import Mininet
from mininet.node import RemoteController, OVSSwitch
from mininet.link import TCLink
from mininet.log import setLogLevel

HERE = os.path.dirname(os.path.abspath(__file__))
RESULTS = os.path.join(HERE, "results")
PY = sys.executable
sys.path.insert(0, HERE)

from run_experiment import (attacker_port, build, wait_for_control_plane,
                            wait_for_rest_stable)


def clean_all(ctrl):
    # remove our flows/meters on ANY port (both scripts delete by appId)
    subprocess.run([PY, f"{HERE}/block.py", "--host", ctrl,
                    "--port", "1", "--remove"], check=True)
    subprocess.run([PY, f"{HERE}/ratelimit.py", "--host", ctrl,
                    "--port", "1", "--remove"], check=True)


def run_detector(ctrl, defense, threshold, duration, out, label):
    return subprocess.Popen([PY, f"{HERE}/detector.py", "--host", ctrl,
                             "--defense", defense, "--threshold", str(threshold),
                             "--once", "--duration", str(duration),
                             "--out", out, "--label", label])


def start_flood(h3, rate, duration, log_name):
    flood_log = open(f"{RESULTS}/{log_name}", "w")
    atk = h3.popen([PY, f"{HERE}/flood.py",
                    "--iface", h3.defaultIntf().name,
                    "--dst-ip", "10.0.0.1", "--rate", str(rate),
                    "--duration", str(duration)],
                   stdout=flood_log, stderr=subprocess.STDOUT)
    return atk, flood_log


def wait_flood(atk, flood_log):
    try:
        rc = atk.wait()
    finally:
        flood_log.close()
    if rc != 0:
        raise RuntimeError(f"flood.py failed with exit code {rc}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--controller", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=6653)
    ap.add_argument("--rate", type=int, default=500)
    ap.add_argument("--defense", choices=["block", "ratelimit"], default="ratelimit")
    ap.add_argument("--thresholds", default="100,200,300,500,800")
    ap.add_argument("--duration", type=int, default=30)
    ap.add_argument("--reps", type=int, default=3)
    ap.add_argument("--fp-check", action="store_true",
                    help="add a legitimate-burst control run (no attack)")
    a = ap.parse_args()

    os.makedirs(RESULTS, exist_ok=True)
    out = f"{RESULTS}/detection.csv"
    if os.path.exists(out):
        os.remove(out)
    setLogLevel('warning')
    net, h2, h3, s1 = build(a.controller, a.port)
    try:
        wait_for_control_plane(a.controller)
        wait_for_rest_stable(a.controller)
        port = attacker_port(h3, s1)
        h2.cmd("ping -c1 -W1 10.0.0.1")

        thresholds = [int(t) for t in a.thresholds.split(",") if t.strip()]
        for th in thresholds:
            for rep in range(1, a.reps + 1):
                label = f"th{th}" if a.reps == 1 else f"th{th}_r{rep}"
                print(f"\n=== threshold {th} pkt/s, rep {rep} ===")
                clean_all(a.controller)
                det = run_detector(a.controller, a.defense, th, a.duration, out, label)
                atk, flood_log = start_flood(h3, a.rate, a.duration,
                                             f"flood_detection_th{th}_r{rep}.log")
                wait_flood(atk, flood_log)
                det_rc = det.wait()
                if det_rc != 0:
                    raise RuntimeError(f"detector.py failed with exit code {det_rc}")
                clean_all(a.controller)
                time.sleep(3)

        if a.fp_check:
            th = min(thresholds)
            print(f"\n=== false-positive control: legitimate burst, threshold {th} ===")
            clean_all(a.controller)
            det = run_detector(a.controller, a.defense, th, a.duration, out, "fp_legitburst")
            # one established flow, flooded as fast as possible: high data-plane rate,
            # almost no control-plane load. Should it trigger the detector?
            h2.cmd(f"ping -f -w {a.duration} 10.0.0.1")
            det.wait()
            clean_all(a.controller)
    finally:
        net.stop()
    print(f"\nDone -> {out}. Run: python3 plot_detection.py")


if __name__ == "__main__":
    main()
