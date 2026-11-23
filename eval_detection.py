#!/usr/bin/env python3
import argparse, os, time, subprocess
from mininet.net import Mininet
from mininet.node import RemoteController, OVSSwitch
from mininet.link import TCLink
from mininet.log import setLogLevel

HERE = os.path.dirname(os.path.abspath(__file__))
RESULTS = os.path.join(HERE, "results")


def build(ctrl, port):
    net = Mininet(controller=None, switch=OVSSwitch, link=TCLink, autoSetMacs=True)
    c0 = net.addController('c0', controller=RemoteController, ip=ctrl, port=port)
    s1 = net.addSwitch('s1', protocols='OpenFlow13')
    h1 = net.addHost('h1', ip='10.0.0.1/24')
    h2 = net.addHost('h2', ip='10.0.0.2/24')
    h3 = net.addHost('h3', ip='10.0.0.3/24')
    for h in (h1, h2, h3):
        net.addLink(h, s1)
    net.build(); c0.start(); s1.start([c0])
    return net, h2, h3, s1


def clean_all(ctrl):
    # remove our flows/meters on ANY port (both scripts delete by appId)
    subprocess.run(["python3", f"{HERE}/block.py", "--host", ctrl, "--port", "1", "--remove"])
    subprocess.run(["python3", f"{HERE}/ratelimit.py", "--host", ctrl, "--port", "1", "--remove"])


def run_detector(ctrl, defense, threshold, duration, out, label):
    return subprocess.Popen(["python3", f"{HERE}/detector.py", "--host", ctrl,
                             "--defense", defense, "--threshold", str(threshold),
                             "--once", "--duration", str(duration),
                             "--out", out, "--label", label])


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
    time.sleep(3)
    h2.cmd("ping -c1 -W1 10.0.0.1")

    thresholds = [int(t) for t in a.thresholds.split(",") if t.strip()]
    try:
        for th in thresholds:
            for rep in range(1, a.reps + 1):
                label = f"th{th}" if a.reps == 1 else f"th{th}_r{rep}"
                print(f"\n=== threshold {th} pkt/s, rep {rep} ===")
                clean_all(a.controller)
                det = run_detector(a.controller, a.defense, th, a.duration, out, label)
                atk = h3.popen(["python3", f"{HERE}/flood.py", "--iface", h3.defaultIntf().name,
                                "--dst-ip", "10.0.0.1", "--rate", str(a.rate),
                                "--duration", str(a.duration)])
                atk.wait(); det.wait()
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