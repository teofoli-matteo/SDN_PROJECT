#!/usr/bin/env python3
import argparse
from mininet.net import Mininet
from mininet.node import RemoteController, OVSSwitch
from mininet.cli import CLI
from mininet.link import TCLink
from mininet.log import setLogLevel


def build(controller_ip, controller_port=6653):
    net = Mininet(controller=None, switch=OVSSwitch, link=TCLink, autoSetMacs=True)
    c0 = net.addController('c0', controller=RemoteController,
                           ip=controller_ip, port=controller_port)
    s1 = net.addSwitch('s1', protocols='OpenFlow13')
    h1 = net.addHost('h1', ip='10.0.0.1/24')
    h2 = net.addHost('h2', ip='10.0.0.2/24')
    h3 = net.addHost('h3', ip='10.0.0.3/24')
    for h in (h1, h2, h3):
        net.addLink(h, s1)
    net.build()
    c0.start()
    s1.start([c0])
    return net


if __name__ == '__main__':
    setLogLevel('info')
    ap = argparse.ArgumentParser()
    ap.add_argument('--controller', default='127.0.0.1')
    ap.add_argument('--port', type=int, default=6653)
    args = ap.parse_args()
    net = build(args.controller, args.port)
    print("\n[topology] h1=server  h2=client  h3=attacker")
    print("[topology] attacker interface = h3-eth0 ; attacker switch port = 3")
    print("[topology] type 'exit' to quit.\n")
    CLI(net)
    net.stop()