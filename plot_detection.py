#!/usr/bin/env python3
import os
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

R = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")


def main():
    df = pd.read_csv(os.path.join(R, "detection.csv")).sort_values("threshold")
    for c in ("threshold", "triggered", "detect_s", "mitigate_s"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    trig = df[df["triggered"] == 1]
    missed = df[df["triggered"] == 0]

    plt.figure(figsize=(7, 4.5))
    if len(trig):
        plt.plot(trig["threshold"], trig["mitigate_s"], "o-", color="firebrick",
                 label="Time to mitigation")
    if len(missed):
        plt.scatter(missed["threshold"], [0] * len(missed), marker="x",
                    color="gray", s=80, label="Not detected (attack succeeds)")
    plt.xlabel("Detection threshold (pkt/s)")
    plt.ylabel("Time to mitigation (s)")
    plt.title("Autonomous detection: reaction vs threshold")
    plt.ylim(bottom=0); plt.grid(alpha=.3); plt.legend()
    plt.tight_layout()
    plt.savefig(os.path.join(R, "fig_detection.png"))
    print("wrote fig_detection.png")
    print(df[["label", "threshold", "triggered", "detect_s",
              "mitigate_s", "rate_pkts"]].to_string(index=False))


if __name__ == "__main__":
    main()