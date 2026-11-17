# SDN Controller Saturation Attacks — Group 2

Implementation and analysis of a **control-plane saturation attack** (Packet-In
flooding) against a resource-limited **ONOS** controller, plus two
countermeasures — **blocking** vs. **rate-limiting** — evaluated on their impact
and their effect on legitimate traffic.

> Course: *Security of Software Defined Networking*.

## Research question

As the Packet-In flooding rate increases against a CPU-limited ONOS controller,
**at what rate does the controller start to degrade, what breaks first**
(CPU, RAM, control-plane responsiveness, data-plane latency), and **how do
blocking and rate-limiting compare** at reducing the impact without harming
legitimate traffic?

## Threat model

- One malicious host inside the network sends a flood of packets with **fake,
  random source IP/MAC** addresses.
- Every packet looks like a brand-new flow, so the switch sends a new **Packet-In**
  to ONOS.
- At a high enough rate the ONOS CPU saturates and the control plane can no
  longer serve the network.
- We study **only control-plane (resource) saturation** — we do *not* flood the
  data links.

## Topology

```
          ONOS (Docker, CPU-limited)
                 |  OpenFlow 1.3 (tcp/6653)
              [ s1 ]  Open vSwitch
             /   |   \
          h1    h2    h3
       server  client  attacker
       (port1) (port2) (port3 = s1-eth3)
```

- **h1** — legitimate server.
- **h2** — legitimate client (the victim we measure: steady ping + loss).
- **h3** — attacker, runs the Scapy flood.

## Repository layout

| File | Role |
|------|------|
| `start_onos.sh` | Launch a **CPU-limited** ONOS in Docker and activate `openflow` + `fwd` (reactive forwarding). |
| `topology.py` | Mininet network (h1/h2/h3 + s1), for the live demo. |
| `flood.py` | Scapy attack: random src MAC/IP → one Packet-In per packet. Runs in `h3`. |
| `legit.py` | Victim workload in `h2`: steady ping RTT + loss. |
| `monitor.py` | Samples ONOS CPU%, RAM and REST-API latency → CSV. |
| `block.py` | Countermeasure 1 — DROP everything from the attacker's ingress port. |
| `ratelimit.py` | Countermeasure 2 — cap the attacker's port to N pkt/s with an ONOS meter. |
| `onoslib.py` | Tiny ONOS REST helper (stdlib only). |
| `run_experiment.py` | Automated driver: all scenarios, 3 repetitions, writes