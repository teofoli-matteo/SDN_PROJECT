#!/usr/bin/env python3
import os
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

R = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")


def main():
    onos = pd.read_csv(os.path.join(R, "onos.csv"))
    legit = pd.read_csv(os.path.join(R, "legit.csv"))
    onos["cpu_pct"] = pd.to_numeric(onos["cpu_pct"], errors="coerce")
    legit["newconn_ms"] = pd.to_numeric(legit["newconn_ms"], errors="coerce")

    cpu = onos.groupby("scenario")["cpu_pct"].mean()
    newconn = legit.groupby("scenario")["newconn_ms"].mean()
    loss = legit.groupby("scenario")["loss"].mean() * 100

    summary = pd.concat([
        cpu.rename("onos_cpu_pct"),
        newconn.rename("newconn_ms_mean"),
        loss.rename("legit_loss_pct"),
    ], axis=1).sort_index()
    summary.to_csv(os.path.join(R, "summary.csv"))
    print(summary.to_string())

    ax = cpu.sort_values().plot(kind="bar", title="ONOS CPU by scenario")
    ax.set_ylabel("CPU %")
    plt.tight_layout(); plt.savefig(os.path.join(R, "fig_cpu.png")); plt.clf()

    ax = newconn.plot(kind="bar", title="New-connection setup time by scenario")
    ax.set_ylabel("ms")
    plt.tight_layout(); plt.savefig(os.path.join(R, "fig_newconn.png"))
    print("\nWrote summary.csv, fig_cpu.png, fig_newconn.png in results/")


if __name__ == '__main__':
    main()