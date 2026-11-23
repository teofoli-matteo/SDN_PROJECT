# SDN Controller Saturation Attacks (Group 2)

Implementation and analysis of a control-plane saturation attack (Packet-In
flooding) against a resource-limited ONOS controller, with two countermeasures,
port blocking and meter-based rate limiting, and an autonomous detector that
applies a mitigation on its own.

Course: Security of Software Defined Networking.

## Research question

As the Packet-In flooding rate rises against a CPU-limited ONOS controller, at
what rate does the controller start to degrade, what breaks first (CPU, RAM,
control-plane responsiveness or data-plane latency), and how do blocking and
rate limiting compare at reducing the impact without harming legitimate traffic?

## Threat model

An attacker controls one host already inside the network. From it, the attacker
floods the switch with packets whose source MAC and IP are random and change on
every packet. The switch has no matching flow rule for any of them, so it sends
a Packet-In to ONOS for each one. At a high enough rate the controller's CPU
saturates and it can no longer serve the rest of the network. No link is
overloaded; only table misses are generated. We study control-plane resource
exhaustion only.

## Topology

```
          ONOS (Docker, 1 CPU / 2 GB)
                 |  OpenFlow 1.3 (tcp/6653)
              [ s1 ]  Open vSwitch
             /   |   \
          h1    h2    h3
       server  client  attacker
       (port1) (port2) (port3 = s1-eth3)
```

h1 is a server, h2 the legitimate client we measure (steady ping and loss), and
h3 the attacker running the Scapy flood.

## Repository layout

| File | Role |
|------|------|
| `start_onos.sh` | Launch a CPU-limited ONOS in Docker and activate `openflow` + `fwd` (reactive forwarding). |
| `topology.py` | Mininet network (h1/h2/h3 + s1), for the live demo. |
| `flood.py` | Scapy attack: random src MAC/IP, one Packet-In per packet. Runs in h3. |
| `legit.py` | Victim workload in h2: steady ping RTT and loss. |
| `monitor.py` | Samples ONOS CPU%, RAM and REST-API latency to CSV. |
| `block.py` | Countermeasure 1: drop everything from the attacker's ingress port. |
| `ratelimit.py` | Countermeasure 2: cap the attacker's port to N pkt/s with an ONOS meter. |
| `detector.py` | Autonomous detector: watches per-port rates and triggers a mitigation by itself. |
| `eval_detection.py` | Sweeps detection thresholds and logs the detector's reaction time. |
| `onoslib.py` | Tiny ONOS REST helper (stdlib only). |
| `run_experiment.py` | Automated driver: all scenarios, 3 repetitions, writes `results/*.csv`. |
| `plot.py` | Turns the CSVs into `summary.csv` and the attack/defense figures. |
| `plot_detection.py` | Turns `detection.csv` into the detection figure. |
| `results/` | Collected CSVs and generated figures. |

## Requirements

A Linux host with Mininet, Open vSwitch, Docker, Python 3 and Scapy. The
plotting scripts also need pandas and matplotlib.

```bash
sudo apt install -y mininet openvswitch-switch python3-scapy docker.io curl
pip install pandas matplotlib
docker pull onosproject/onos:2.7-latest
```

## Starting ONOS (needed for everything below)

ONOS has to be fully booted, with its apps ACTIVE, before Mininet connects. If
Mininet starts first, the switch connects to a half-booted controller and never
registers. So start ONOS, wait, and check the app state.

```bash
sudo mn -c
sudo docker rm -f onos
sudo ./start_onos.sh
sleep 90
curl -s -u onos:rocks http://localhost:8181/onos/v1/applications/org.onosproject.openflow | grep -o '"state":"[A-Z]*"'
```

If that does not print `"ACTIVE"`, activate the apps and wait:

```bash
curl -u onos:rocks -X POST http://localhost:8181/onos/v1/applications/org.onosproject.openflow/active
curl -u onos:rocks -X POST http://localhost:8181/onos/v1/applications/org.onosproject.fwd/active
sleep 10
```

## Reproducing the results (the real experiment)

`run_experiment.py` builds the Mininet network itself and runs every scenario:
baseline, then each attack rate with no defense, with blocking, and with rate
limiting. Defenses are applied from the start of each run so the average is a
clean defended state, each scenario is repeated three times, and two transition
runs apply the defense mid-attack for the time-series figure.

Clear `results/` first so old data does not mix with the new run (the scripts
append to the CSVs), then run and plot. The full run takes about 20 minutes.

```bash
rm -f results/onos.csv results/legit.csv results/events.csv results/summary.csv
sudo python3 run_experiment.py --controller 127.0.0.1 --rates 200,500,1000 --duration 40 --reps 3 --trans-rate 1000 --trans-delay 20
sudo chown -R $USER:$USER results      # run_experiment writes as root; take the files back
python3 plot.py
```

## A quick check (about 3 minutes)

To confirm the whole pipeline works without waiting for the full run, use one
rate, a short duration and a single repetition. This overwrites `results/`, so
back it up first if it holds data you want to keep.

```bash
rm -f results/onos.csv results/legit.csv results/events.csv results/summary.csv
sudo python3 run_experiment.py --controller 127.0.0.1 --rates 500 --duration 15 --reps 1 --trans-rate 500 --trans-delay 8
sudo chown -R $USER:$USER results
python3 plot.py
```

## Autonomous detection

`eval_detection.py` sweeps a set of thresholds against a fixed attack. For each
threshold it runs the attack and the detector together; the detector watches
per-port rates over a sliding window, and when a port crosses the threshold it
installs a mitigation and logs how long it took.

```bash
sudo python3 eval_detection.py --controller 127.0.0.1 --rate 500 --defense ratelimit --thresholds 100,200,300,500,800
python3 plot_detection.py
```

To watch the detector react live instead, run it on its own and then start an
attack; the mitigation fires without any manual action:

```bash
python3 detector.py --defense ratelimit --threshold 300
# then, inside the Mininet CLI:
#   h3 python3 flood.py --iface h3-eth0 --dst-ip 10.0.0.1 --rate 500 --duration 120 &
```

## Live demo (manual)

Start ONOS as above, then the network, and drive the attack and defenses by hand.

```bash
sudo python3 topology.py --controller 127.0.0.1
# in the Mininet CLI (run pingall twice; the first run pays the reactive flow setup):
#   pingall
#   pingall
#   h2 python3 legit.py --server 10.0.0.1 --scenario demo &
#   h3 python3 flood.py --iface h3-eth0 --dst-ip 10.0.0.1 --rate 500 --duration 120 &
# in a side terminal, watch the CPU:
#   sudo python3 monitor.py --name onos --scenario demo
# then apply a defense (attacker is port 3):
#   python3 ratelimit.py --port 3 --rate 150 --install     # /  --remove
#   python3 block.py --port 3 --install                    # /  --remove
```

Teardown:

```bash
sudo mn -c
sudo docker rm -f onos
```

## Results

Means over three repetitions, on a one-CPU, 2 GB ONOS container.

| Scenario | ONOS CPU % | RAM (MB) | Legit ping (ms) | Loss % |
|----------|-----------:|---------:|----------------:|-------:|
| baseline      |   1.7 | 2006 | 0.10 | 0.0 |
| attack 200    |  42.1 | 2007 | 0.08 | 0.0 |
| attack 500    |  87.0 | 2014 | 0.08 | 0.0 |
| attack 1000   | 102.0 | 2019 | 0.08 | 0.0 |
| block 200     |   6.5 | 2011 | 0.09 | 0.0 |
| block 500     |  23.3 | 2013 | 0.09 | 0.0 |
| block 1000    |  46.9 | 2023 | 0.09 | 0.0 |
| ratelimit 200 |   1.7 | 2010 | 0.08 | 0.0 |
| ratelimit 500 |  16.9 | 2014 | 0.08 | 0.0 |
| ratelimit 1000|   8.4 | 2027 | 0.08 | 0.0 |

The control-plane CPU is what saturates: it climbs from 1.7% at rest to 42.1%,
87.0% and 102% at 200, 500 and 1000 pkt/s. RAM stays near 2 GB throughout, so it
is not the bottleneck, and the legitimate ping stays around 0.08 ms with no loss,
because an established flow is forwarded by the switch alone. Both defenses bring
the controller back; rate limiting protects it best, keeping CPU at or below
16.9% at every rate while blocking leaves 6.5% to 46.9% and weakens as the rate
rises.

![CPU vs attack rate](results/fig_cpu_curve.png)

![CPU by defense, per attack rate](results/fig_defense_bars.png)

![Defense applied mid-attack](results/fig_transition.png)

For the autonomous detector against a 500 pkt/s attack: thresholds of 100, 200
and 300 pkt/s detect and mitigate in about 6 seconds, 500 pkt/s in about 11
seconds, and 800 pkt/s never triggers, so the attack runs unchecked. A higher
threshold is crossed later, and one set above the attack rate misses the attack
entirely. The reaction time has a floor of a few seconds, set by how often ONOS
refreshes its port statistics plus the averaging window.

![Autonomous detection: reaction vs threshold](results/fig_detection.png)

Other figures in `results/`: `fig_cpu_timeseries.png`, `fig_defense_effectiveness.png`,
`fig_rest_latency.png`, `fig_ping_health.png`, `fig_memory.png`.

## Notes and known issues

- Start ONOS once and the topology once per session. Restarting the topology
  against the same ONOS leaves stale host entries, and some hosts then fail to
  ping. If that happens, restart ONOS (`docker rm -f onos` then `start_onos.sh`).
- Some Open vSwitch builds do not honor OpenFlow 1.3 meters. If `ratelimit.py`
  cannot get a meter id, cap the port in the datapath instead:
  ```bash
  sudo ovs-vsctl set interface s1-eth3 ingress_policing_rate=1000
  sudo ovs-vsctl set interface s1-eth3 ingress_policing_burst=100
  # remove: ingress_policing_rate=0
  ```
- Clear `results/` whenever you change the code, so old CSV rows (a different
  column layout) do not mix with new ones and break `plot.py`.
- `run_experiment.py` and `eval_detection.py` run under `sudo`, so they write
  `results/` as root. Run `sudo chown -R $USER:$USER results` before plotting
  from a virtualenv.
- REST latency barely moves under load (ONOS serves it on separate threads), so
  we rely on CPU, RAM and ping, not REST latency.
- Pure-Python Scapy tops out around 1 to 2k pkt/s; for higher rates use hping3.

## Authors

Group 2, Security of SDN. Repository: https://github.com/teofoli-matteo/SDN_PROJECT
