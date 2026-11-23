#!/usr/bin/env python3
import argparse, os, sys, subprocess, time
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


def clean(ctrl, port):
    subprocess.run([PY, f"{HERE}/block.py", "--host", ctrl,
                    "--port", str(port), "--remove"], check=True)
    subprocess.run([PY, f"{HERE}/ratelimit.py", "--host", ctrl,
                    "--port", str(port), "--remove"], check=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--controller", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=6653)
    ap.add_argument("--rate", type=int, default=500)
    ap.add_argument("--defense", choices=["block", "ratelimit"], default="ratelimit")
    ap.add_argument("--thresholds", default="100,200,300,500,800")
    ap.add_argument("--duration", type=int, default=30)
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
            print(f"\n=== threshold {th} pkt/s ===")
            clean(a.controller, port)
            det = subprocess.Popen([PY, f"{HERE}/detector.py",
                "--host", a.controller, "--defense", a.defense,
                "--threshold", str(th), "--once", "--duration", str(a.duration),
                "--out", out, "--label", f"th{th}"])
            flood_log = open(f"{RESULTS}/flood_detection_th{th}.log", "w")
            try:
                atk = h3.popen([PY, f"{HERE}/flood.py",
                    "--iface", h3.defaultIntf().name,
                    "--dst-ip", "10.0.0.1", "--rate", str(a.rate),
                    "--duration", str(a.duration)],
                    stdout=flood_log, stderr=subprocess.STDOUT)
                atk_rc = atk.wait()
            finally:
                flood_log.close()
            if atk_rc != 0:
                raise RuntimeError(f"flood.py failed with exit code {atk_rc}")
            det_rc = det.wait()
            if det_rc != 0:
                raise RuntimeError(f"detector.py failed with exit code {det_rc}")
            clean(a.controller, port)
            time.sleep(3)
    finally:
        net.stop()
    print(f"\nDone -> {out}. Run: python3 plot_detection.py")


if __name__ == "__main__":
    main()
