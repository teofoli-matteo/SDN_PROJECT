#!/usr/bin/env python3
import argparse, csv, os, time, subprocess
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
    return net, h2, h3, s1


def attacker_port(h3, s1):
    return s1.ports[h3.connectionsTo(s1)[0][1]]


def apply_defense(ctrl, port, defense, rate):
    if defense == "block":
        subprocess.run(["python3", f"{HERE}/block.py", "--host", ctrl,
                        "--port", str(port), "--install"])
    elif defense == "ratelimit":
        subprocess.run(["python3", f"{HERE}/ratelimit.py", "--host", ctrl,
                        "--port", str(port), "--rate", str(max(100, rate // 4)),
                        "--install"])


def clean_defenses(ctrl, port):
    subprocess.run(["python3", f"{HERE}/block.py", "--host", ctrl,
                    "--port", str(port), "--remove"])
    subprocess.run(["python3", f"{HERE}/ratelimit.py", "--host", ctrl,
                    "--port", str(port), "--remove"])


def start_obs(h2, name, rep, duration):
    mon = subprocess.Popen(["python3", f"{HERE}/monitor.py", "--name", "onos",
                            "--out", f"{RESULTS}/onos.csv", "--scenario", name,
                            "--rep", str(rep), "--duration", str(duration)])
    legit = h2.popen(["python3", f"{HERE}/legit.py", "--server", "10.0.0.1",
                      "--out", f"{RESULTS}/legit.csv", "--scenario", name,
                      "--rep", str(rep), "--duration", str(duration)])
    return mon, legit


def stop_obs(mon, legit, duration):
    try:
        mon.wait(timeout=duration + 5)
    except Exception:
        mon.terminate()
    legit.terminate()


def run_steady(h2, h3, s1, name, rate, defense, rep, ctrl, duration):
    print(f"\n=== {name} rep{rep} (rate={rate}, defense={defense}) ===")
    port = attacker_port(h3, s1)
    if defense != "none":
        apply_defense(ctrl, port, defense, rate)
    mon, legit = start_obs(h2, name, rep, duration)
    h2.cmd("ping -c1 -W1 10.0.0.1")
    atk = None
    if rate > 0:
        atk = h3.popen(["python3", f"{HERE}/flood.py", "--iface", h3.defaultIntf().name,
                        "--dst-ip", "10.0.0.1", "--rate", str(rate),
                        "--duration", str(duration)])
    if atk:
        atk.wait()
    stop_obs(mon, legit, duration)
    clean_defenses(ctrl, port)
    time.sleep(3)


def run_transition(h2, h3, s1, name, rate, defense, ctrl, duration, delay, events):
    print(f"\n=== {name} (rate={rate}, defense={defense} @ {delay}s) ===")
    port = attacker_port(h3, s1)
    mon, legit = start_obs(h2, name, 1, duration)
    h2.cmd("ping -c1 -W1 10.0.0.1")
    atk = h3.popen(["python3", f"{HERE}/flood.py", "--iface", h3.defaultIntf().name,
                    "--dst-ip", "10.0.0.1", "--rate", str(rate),
                    "--duration", str(duration)])
    time.sleep(delay)
    apply_defense(ctrl, port, defense, rate)
    events.writerow([name, delay])
    atk.wait()
    stop_obs(mon, legit, duration)
    clean_defenses(ctrl, port)
    time.sleep(3)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--controller", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=6653)
    ap.add_argument("--rates", default="200,500,1000")
    ap.add_argument("--duration", type=int, default=40)
    ap.add_argument("--reps", type=int, default=3)
    ap.add_argument("--trans-rate", type=int, default=1000)
    ap.add_argument("--trans-delay", type=int, default=20)
    a = ap.parse_args()

    os.makedirs(RESULTS, exist_ok=True)
    ev = open(f"{RESULTS}/events.csv", "w", newline="")
    events = csv.writer(ev); events.writerow(["scenario", "applied_elapsed"])

    setLogLevel('warning')
    net, h2, h3, s1 = build(a.controller, a.port)
    time.sleep(3)
    rates = [int(r) for r in a.rates.split(",") if r.strip()]

    try:
        for rep in range(1, a.reps + 1):
            run_steady(h2, h3, s1, "baseline", 0, "none", rep, a.controller, a.duration)
            for r in rates:
                run_steady(h2, h3, s1, f"attack{r}", r, "none", rep, a.controller, a.duration)
                run_steady(h2, h3, s1, f"block{r}", r, "block", rep, a.controller, a.duration)
                run_steady(h2, h3, s1, f"ratelimit{r}", r, "ratelimit", rep, a.controller, a.duration)
        tr = a.trans_rate
        run_transition(h2, h3, s1, f"transblock{tr}", tr, "block",
                       a.controller, a.duration, a.trans_delay, events)
        run_transition(h2, h3, s1, f"transratelimit{tr}", tr, "ratelimit",
                       a.controller, a.duration, a.trans_delay, events)
    finally:
        ev.close()
        net.stop()
    print("\nDone. CSVs in results/. Run:  python3 plot.py")


if __name__ == '__main__':
    main()