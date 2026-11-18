#!/usr/bin/env python3
import argparse, csv, os, shutil, sys, time, subprocess
from mininet.net import Mininet
from mininet.node import RemoteController, OVSSwitch
from mininet.link import TCLink
from mininet.log import setLogLevel

HERE = os.path.dirname(os.path.abspath(__file__))
RESULTS = os.path.join(HERE, "results")
PY = sys.executable
sys.path.insert(0, HERE)


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


def wait_for_control_plane(ctrl, timeout=90):
    """Wait until ONOS sees the switch and reactive forwarding is active."""
    from onoslib import Onos
    o = Onos(host=ctrl)
    deadline = time.time() + timeout
    last = "no response"
    while time.time() < deadline:
        try:
            dev = o.first_device()
            state = o.get("/applications/org.onosproject.fwd").get("state")
            if state == "ACTIVE":
                return dev
            last = f"fwd state={state}"
        except Exception as e:
            last = str(e)
        time.sleep(2)
    raise SystemExit(
        f"ONOS control plane not ready after {timeout}s ({last}). "
        "Run ./start_onos.sh first and check the fwd application.")


def wait_for_rest_stable(ctrl, timeout=60, threshold_ms=100.0):
    """Wait for the REST API to settle so the baseline is not polluted by boot."""
    from onoslib import Onos
    o = Onos(host=ctrl)
    calm = 0
    last = None
    deadline = time.time() + timeout
    while time.time() < deadline:
        t0 = time.monotonic()
        try:
            o.get("/devices")
            last = (time.monotonic() - t0) * 1000.0
        except Exception:
            last = None
        if last is not None and last < threshold_ms:
            calm += 1
            if calm >= 3:
                print(f"[run] ONOS REST stable ({last:.0f} ms)")
                return
        else:
            calm = 0
        time.sleep(1.0)
    print(f"[run] WARNING: REST latency still {last} ms after {timeout}s; starting anyway")


def archive_previous_results():
    """Move the previous run's CSVs aside instead of silently appending to them."""
    names = ("onos.csv", "legit.csv", "events.csv")
    present = [n for n in names if os.path.exists(os.path.join(RESULTS, n))]
    if not present:
        return
    dest = os.path.join(RESULTS, time.strftime("previous-%Y%m%d-%H%M%S"))
    os.makedirs(dest, exist_ok=True)
    for name in present:
        shutil.move(os.path.join(RESULTS, name), os.path.join(dest, name))
    print(f"[run] previous results moved to {dest}")


def prepare_results(append):
    os.makedirs(RESULTS, exist_ok=True)
    if not append:
        archive_previous_results()


def apply_defense(ctrl, port, defense, rate):
    if defense == "block":
        subprocess.run([PY, f"{HERE}/block.py", "--host", ctrl,
                        "--port", str(port), "--install"], check=True)
    elif defense == "ratelimit":
        subprocess.run([PY, f"{HERE}/ratelimit.py", "--host", ctrl,
                        "--port", str(port),
                        "--rate", str(max(100, rate // 4)),
                        "--install"], check=True)


def clean_defenses(ctrl, port):
    subprocess.run([PY, f"{HERE}/block.py", "--host", ctrl,
                    "--port", str(port), "--remove"], check=True)
    subprocess.run([PY, f"{HERE}/ratelimit.py", "--host", ctrl,
                    "--port", str(port), "--remove"], check=True)


def start_obs(h2, name, rep, duration):
    mon = subprocess.Popen([PY, f"{HERE}/monitor.py", "--name", "onos",
                            "--out", f"{RESULTS}/onos.csv", "--scenario", name,
                            "--rep", str(rep), "--duration", str(duration)])
    legit = h2.popen([PY, f"{HERE}/legit.py", "--server", "10.0.0.1",
                      "--out", f"{RESULTS}/legit.csv", "--scenario", name,
                      "--rep", str(rep), "--duration", str(duration)])
    return mon, legit


def stop_obs(mon, legit, duration):
    try:
        mon.wait(timeout=duration + 15)
    except Exception:
        mon.terminate()
        try:
            mon.wait(timeout=5)
        except Exception:
            mon.kill()
    legit.terminate()
    try:
        legit.wait(timeout=5)
    except Exception:
        legit.kill()


def run_steady(h2, h3, s1, name, rate, defense, rep, ctrl, duration):
    print(f"\n=== {name} rep{rep} (rate={rate}, defense={defense}) ===")
    port = attacker_port(h3, s1)
    if defense != "none":
        apply_defense(ctrl, port, defense, rate)
    mon, legit = start_obs(h2, name, rep, duration)
    try:
        h2.cmd("ping -c1 -W1 10.0.0.1")
        if rate > 0:
            flood_log = open(f"{RESULTS}/flood_{name}_rep{rep}.log", "w")
            try:
                atk = h3.popen([PY, f"{HERE}/flood.py", "--iface", h3.defaultIntf().name,
                                "--dst-ip", "10.0.0.1", "--rate", str(rate),
                                "--duration", str(duration)],
                               stdout=flood_log, stderr=subprocess.STDOUT)
                rc = atk.wait()
            finally:
                flood_log.close()
            if rc != 0:
                raise RuntimeError(f"flood.py failed with exit code {rc}")
    finally:
        stop_obs(mon, legit, duration)
        clean_defenses(ctrl, port)
    time.sleep(3)


def run_transition(h2, h3, s1, name, rate, defense, ctrl, duration, delay, events):
    print(f"\n=== {name} (rate={rate}, defense={defense} @ {delay}s) ===")
    port = attacker_port(h3, s1)
    mon, legit = start_obs(h2, name, 1, duration)
    try:
        h2.cmd("ping -c1 -W1 10.0.0.1")
        flood_log = open(f"{RESULTS}/flood_{name}_rep1.log", "w")
        try:
            atk = h3.popen([PY, f"{HERE}/flood.py", "--iface", h3.defaultIntf().name,
                            "--dst-ip", "10.0.0.1", "--rate", str(rate),
                            "--duration", str(duration)],
                           stdout=flood_log, stderr=subprocess.STDOUT)
            time.sleep(delay)
            apply_defense(ctrl, port, defense, rate)
            events.writerow([name, delay])
            rc = atk.wait()
        finally:
            flood_log.close()
        if rc != 0:
            raise RuntimeError(f"flood.py failed with exit code {rc}")
    finally:
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
    ap.add_argument("--append", action="store_true",
                    help="append to the existing CSVs instead of archiving them")
    a = ap.parse_args()

    setLogLevel('warning')
    net, h2, h3, s1 = build(a.controller, a.port)
    try:
        time.sleep(3)
        dev = wait_for_control_plane(a.controller)
        print(f"[run] ONOS sees switch {dev}; reactive forwarding is ACTIVE")
        wait_for_rest_stable(a.controller)
        prepare_results(a.append)

        ev_path = f"{RESULTS}/events.csv"
        fresh_events = (not a.append) or (not os.path.exists(ev_path))
        ev = open(ev_path, "a" if a.append else "w", newline="")
        events = csv.writer(ev)
        if fresh_events:
            events.writerow(["scenario", "applied_elapsed"])

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
    finally:
        net.stop()
    print("\nDone. CSVs in results/. Run:  python3 plot.py")


if __name__ == "__main__":
    main()
