#!/usr/bin/env python3
import os, re
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

R = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")


def main():
    path = os.path.join(R, "detection.csv")
    if not os.path.exists(path):
        raise SystemExit(
            f"{path} is missing -- run eval_detection.py first, "
            "or pass --out to detector.py.")
    df = pd.read_csv(path)
    for c in ("threshold", "triggered", "detect_s", "mitigate_s", "verified"):
        if c in df:
            df[c] = pd.to_numeric(df[c], errors="coerce")

    fp = df[df["label"].astype(str).str.startswith("fp")]
    sweep = df[~df["label"].astype(str).str.startswith("fp")].copy()

    agg = sweep.groupby("threshold").agg(
        detect_rate=("triggered", "mean"),
        mitigate_s=("mitigate_s", "mean"),
        verified=("verified", "mean"),
        runs=("triggered", "size"),
    ).reset_index().sort_values("threshold")
    detected = agg[agg["detect_rate"] >= 0.5]
    missed = agg[agg["detect_rate"] < 0.5]

    plt.figure(figsize=(7, 4.5))
    if len(detected):
        plt.plot(detected["threshold"], detected["mitigate_s"], "o-",
                 color="firebrick", label="Time to mitigation (mean)")
    if len(missed):
        plt.scatter(missed["threshold"], [0] * len(missed), marker="x",
                    color="gray", s=80, label="Not detected (attack succeeds)")
    plt.xlabel("Detection threshold (pkt/s)")
    plt.ylabel("Time to mitigation (s)")
    plt.title("Autonomous detection: reaction vs threshold")
    plt.ylim(bottom=0); plt.grid(alpha=.3); plt.legend()
    plt.tight_layout()
    plt.savefig(os.path.join(R, "fig_detection.png"))
    print("wrote fig_detection.png\n")
    print(agg.to_string(index=False))
    if len(fp):
        print("\nFalse-positive control (legitimate burst, no attack):")
        print(fp[["label", "threshold", "triggered", "mitigate_s", "verified", "port"]].to_string(index=False))
        if (fp["triggered"] == 1).any():
            print(">> the detector triggered on legitimate traffic: a false positive, "
                  "because it keys on port packet rate, not Packet-In rate.")


if __name__ == "__main__":
    main()