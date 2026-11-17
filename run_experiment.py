#!/usr/bin/env python3
import argparse, os, time, subprocess
from mininet.net import Mininet
from mininet.node import RemoteController, OVSSwitch
from mininet.link import TCLink
from mininet.log import setLogLevel

HERE = os.path.dirname(os.path.abspath(__file__))
RESULTS = os.path.join(HERE, "results")


def build(controller_ip, port):
    net = Mininet(controller=None, switch=OVSSwitch, link=TCLink, autoSetMacs=True)
    c0 = net.addController('c0', controller=RemoteController, ip=controller_ip, port=port)
    s1 = net.addSwitch('s1', protocols='OpenFlow13')
    h1 = net.addHost('h1', ip='10.0.0.1/24')
    h2 = net.addHost('h2', ip='10.0.0.2/24')
    h3 = net.addHost('h3', ip='10.0.0.3/24')
    for h in (h1, h2, h3):
        net.addLink(h, s1)
    net.build(); c0.start(); s1.start([c0])
    return net, h1, h2, h3, s1


def add_aliases(h1, count=150):
    intf = h1.defaultIntf()
    for i in range(count):
        h1.cmd(f"ip addr add 10.0.0.{101 + i}/24 dev {intf} 2>/dev/null")


def attacker_port(h3, s1):
    """OpenFlow port number of the switch interface wired to h3."""
    intf = h3.connectionsTo(s1)[0][1]
    return s1.ports[intf]


def clean_defenses(controller_ip, port):
    subprocess.run(["python3", f"{HERE}/block.py", "--host", controller_ip,
                    "--port", str(port), "--remove"])
    subprocess.run(["python3", f"{HERE}/ratelimit.py", "--host", controller_ip,
                    "--port", str(port), "--remove"])


def run_scenario(net, h1, h2, h3, s1, name, rate, defense,
                 controller_ip, duration, defense_delay):
    print(f"\n=== scenario {name} (rate={rate}, defense={defense}) ===")
    port = attacker_port(h3, s1)

    mon = subprocess.Popen(["python3", f"{HERE}/monitor.py", "--name", "onos",
                            "--out", f"{RESULTS}/onos.csv", "--scenario", name,
                            "--duration", str(duration)])
    legit = h2.popen(["python3", f"{HERE}/legit.py", "--server", "10.0.0.1",
                      "--out", f"{RESULTS}/legit.csv", "--scenario", name,
                      "--duration", str(duration)])
    h2.cmd("ping -c1 -W1 10.0.0.1")   # warm the steady flow

    atk = None
    if rate > 0:
        atk = h3.popen(["python3", f"{HERE}/flood.py", "--iface", h3.defaultIntf().name,
                        "--dst-ip", "10.0.0.1", "--rate", str(rate),
                        "--duration", str(duration)])

    if defense in ("block", "ratelimit"):
        time.sleep(defense_delay)
        if defense == "block":
            subprocess.run(["python3", f"{HERE}/block.py", "--host", controller_ip,
                            "--port", str(port), "--install"])
        else:
            subprocess.run(["python3", f"{HERE}/ratelimit.py", "--host", controller_ip,
                            "--port", str(port), "--rate", str(max(100, rate // 4)),
                            "--install"])

    if atk:
        atk.wait()
    try:
        mon.wait(timeout=duration + 5)
    except Exception:
        mon.terminate()
    legit.terminate()
    clean_defenses(controller_ip, port)
    time.sleep(3)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--controller", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=6653)
    ap.add_argument("--rates", default="200,500,1000")
    ap.add_argument("--duration", type=int, default=40)
    ap.add_argument("--defense-delay", type=int, default=15)
    a = ap.parse_args()

    os.makedirs(RESULTS, exist_ok=True)
    setLogLevel('warning')
    net, h1, h2, h3, s1 = build(a.controller, a.port)
    add_aliases(h1)
    time.sleep(3)

    rates = [int(r) for r in a.rates.split(",") if r.strip()]
    try:
        run_scenario(net, h1, h2, h3, s1, "baseline", 0, "none",
                     a.controller, a.duration, a.defense_delay)
        for r in rates:
            run_scenario(net, h1, h2, h3, s1, f"attack{r}", r, "none",
                         a.controller, a.duration, a.defense_delay)
            run_scenario(net, h1, h2, h3, s1, f"block{r}", r, "block",
                         a.controller, a.duration, a.defense_delay)
            run_scenario(net, h1, h2, h3, s1, f"ratelimit{r}", r, "ratelimit",
                         a.controller, a.duration, a.defense_delay)
    finally:
        net.stop()
    print("\nDone. CSVs are in results/. Run:  python3 plot.py")


if __name__ == '__main__':
    main()