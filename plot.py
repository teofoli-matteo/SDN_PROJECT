#!/usr/bin/env python3
import os, re
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

R = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")


def parse(scn):
    m = re.match(r"(transblock|transratelimit|baseline|attack|block|ratelimit)(\d*)", str(scn))
    if not m:
        return ("other", 0)
    return (m.group(1), int(m.group(2)) if m.group(2) else 0)


def load():
    onos = pd.read_csv(os.path.join(R, "onos.csv"))
    legit = pd.read_csv(os.path.join(R, "legit.csv"))
    for c in ("cpu_pct", "mem_mb", "rest_ms", "elapsed"):
        if c in onos:
            onos[c] = pd.to_numeric(onos[c], errors="coerce")
    for c in ("steady_rtt_ms", "loss", "elapsed"):
        if c in legit:
            legit[c] = pd.to_numeric(legit[c], errors="coerce")
    onos[["kind", "rate"]] = onos["scenario"].apply(lambda s: pd.Series(parse(s)))
    legit[["kind", "rate"]] = legit["scenario"].apply(lambda s: pd.Series(parse(s)))
    return onos, legit


def save(fig_name):
    plt.tight_layout()
    plt.savefig(os.path.join(R, fig_name))
    plt.clf()
    print(f"  wrote {fig_name}")


def series_by_rate(df, kind, col):
    return df[df["kind"] == kind].groupby("rate")[col].mean().sort_index()


def main():
    onos, legit = load()

    o = onos.groupby("scenario").agg(
        cpu_pct=("cpu_pct", "mean"), mem_mb=("mem_mb", "mean"),
        rest_ms=("rest_ms", "mean")).round(1)
    l = legit.groupby("scenario").agg(
        steady_rtt_ms=("steady_rtt_ms", "mean"),
        loss_pct=("loss", lambda x: 100 * x.mean())).round(2)
    summary = o.join(l, how="outer")
    summary.to_csv(os.path.join(R, "summary.csv"))
    print(summary.to_string(), "\n")

    steady = onos[~onos["kind"].str.startswith("trans")]

    base = steady[steady["kind"] == "baseline"]["cpu_pct"].mean()
    plt.figure(figsize=(7, 4.5))
    for kind, label, mk in [("attack", "No defense", "o-"),
                            ("block", "Blocking", "s-"),
                            ("ratelimit", "Rate limiting", "^-")]:
        s = series_by_rate(steady, kind, "cpu_pct")
        if len(s):
            plt.plot(s.index, s.values, mk, label=label)
    if pd.notna(base):
        plt.axhline(base, ls="--", color="gray", label=f"Baseline ({base:.0f}%)")
    plt.xlabel("Attack rate (pkt/s)"); plt.ylabel("ONOS CPU %")
    plt.title("Control-plane CPU vs attack rate"); plt.legend(); plt.grid(alpha=.3)
    save("fig_cpu_curve.png")

    plt.figure(figsize=(7, 4.5))
    atk = steady[steady["kind"] == "attack"]
    for rate, g in atk.groupby("rate"):
        ts = g.groupby("elapsed")["cpu_pct"].mean()
        plt.plot(ts.index, ts.values, label=f"{rate} pkt/s")
    if len(atk):
        plt.xlabel("Time (s)"); plt.ylabel("ONOS CPU %")
        plt.title("CPU over time during the attack"); plt.legend(); plt.grid(alpha=.3)
        save("fig_cpu_timeseries.png")
    else:
        plt.clf(); print("  skip fig_cpu_timeseries (no attack data)")

    rates = sorted(steady[steady["kind"] == "attack"]["rate"].unique())
    if rates:
        import numpy as np
        x = np.arange(len(rates)); w = 0.25
        plt.figure(figsize=(7, 4.5))
        for i, (kind, label) in enumerate([("attack", "No defense"),
                                           ("block", "Blocking"),
                                           ("ratelimit", "Rate limiting")]):
            s = series_by_rate(steady, kind, "cpu_pct")
            vals = [s.get(r, 0) for r in rates]
            plt.bar(x + (i - 1) * w, vals, w, label=label)
        plt.xticks(x, [str(r) for r in rates]); plt.xlabel("Attack rate (pkt/s)")
        plt.ylabel("ONOS CPU %"); plt.title("CPU by defense, per attack rate")
        plt.legend(); plt.grid(axis="y", alpha=.3)
        save("fig_defense_bars.png")

        atk_s = series_by_rate(steady, "attack", "cpu_pct")
        plt.figure(figsize=(7, 4.5))
        for i, (kind, label) in enumerate([("block", "Blocking"),
                                           ("ratelimit", "Rate limiting")]):
            s = series_by_rate(steady, kind, "cpu_pct")
            red = [100 * (atk_s.get(r, 0) - s.get(r, 0)) / atk_s.get(r, 1)
                   if atk_s.get(r, 0) else 0 for r in rates]
            plt.bar(x + (i - 0.5) * w, red, w, label=label)
        plt.xticks(x, [str(r) for r in rates]); plt.xlabel("Attack rate (pkt/s)")
        plt.ylabel("CPU reduction vs no defense (%)")
        plt.title("Defense effectiveness"); plt.legend(); plt.grid(axis="y", alpha=.3)
        save("fig_defense_effectiveness.png")

    s = series_by_rate(steady, "attack", "rest_ms")
    if len(s) and s.notna().any():
        plt.figure(figsize=(7, 4.5))
        plt.plot(s.index, s.values, "o-", color="firebrick")
        plt.xlabel("Attack rate (pkt/s)"); plt.ylabel("REST API latency (ms)")
        plt.title("Controller responsiveness under attack"); plt.grid(alpha=.3)
        save("fig_rest_latency.png")

    ls = legit[~legit["kind"].str.startswith("trans")]
    s = series_by_rate(ls, "attack", "steady_rtt_ms")
    if len(s) and s.notna().any():
        plt.figure(figsize=(7, 4.5))
        plt.plot(s.index, s.values, "o-", color="green")
        plt.xlabel("Attack rate (pkt/s)"); plt.ylabel("Legit ping RTT (ms)")
        plt.title("Data-plane health (established flow stays fast)")
        plt.ylim(bottom=0); plt.grid(alpha=.3)
        save("fig_ping_health.png")

    s = series_by_rate(steady, "attack", "mem_mb")
    if len(s) and s.notna().any():
        plt.figure(figsize=(7, 4.5))
        plt.plot(s.index, s.values, "o-", color="purple")
        plt.xlabel("Attack rate (pkt/s)"); plt.ylabel("ONOS memory (MB)")
        plt.title("ONOS memory vs attack rate (not the bottleneck)")
        plt.ylim(bottom=0); plt.grid(alpha=.3)
        save("fig_memory.png")

    trans = onos[onos["kind"].str.startswith("trans")]
    if len(trans):
        events = {}
        ev_path = os.path.join(R, "events.csv")
        if os.path.exists(ev_path):
            for _, row in pd.read_csv(ev_path).iterrows():
                events[row["scenario"]] = row["applied_elapsed"]
        plt.figure(figsize=(7, 4.5))
        for scn, g in trans.groupby("scenario"):
            ts = g.groupby("elapsed")["cpu_pct"].mean()
            line, = plt.plot(ts.index, ts.values, label=str(scn))
            if scn in events:
                plt.axvline(events[scn], ls="--", color=line.get_color(), alpha=.6)
        plt.xlabel("Time (s)"); plt.ylabel("ONOS CPU %")
        plt.title("Defense applied mid-attack (dashed = applied)")
        plt.legend(); plt.grid(alpha=.3)
        save("fig_transition.png")

    print("\nAll figures written to results/.")


if __name__ == '__main__':
    main()