#!/usr/bin/env python3
"""
control-zgamma (bb-side Zγ) sample-OVERLAP diagnostic.

Plots the ZGto2QG datasets that the pmap `Zgamma` group stacks together, each a
different color, to show they overlap in phase space (multi-count):
  - ZGto2QG-1Jets              : FULLY inclusive (all photon pT)          [red]
  - ZGto2QG-1Jets_Bin-PTG-100  : inclusive photon pT > 100               [blue ramp]
  - ...-PTG-200 / -400 / -600  : inclusive > 200 / 400 / 600

MC-only (no data / no other backgrounds): the point is to show these samples
pile on top of each other. Each is self-normalized via load_samples' finalWeight
(= weight / sum_genweights, xsec*lumi already in `weight`).

Usage (from fitting/):
  python make_zgamma_overlap.py --year 2024 --tag 24Aug07_v15 \
      --data-dir /eos/uscms/store/group/lpchbbrun3/gmachado/24Aug07_v15/2024 \
      --outdir plots/zgamma_overlap/ [--bb-only]
"""
from __future__ import annotations

import argparse
import warnings
from pathlib import Path

import hist
import matplotlib.pyplot as plt
import mplhep as hep
import numpy as np

from hbb import utils
from hbb.common_vars import LUMI

hep.style.use("CMS")

# Each ZGto2QG dataset, its own color/label. Inclusive one in red to stand out.
SAMPLES = [
    ("ZGto2QG-1Jets",             "#E74C3C", "ZGto2QG-1Jets (fully inclusive)"),
    ("ZGto2QG-1Jets_Bin-PTG-100", "#08306B", "Bin-PTG-100 (>100)"),
    ("ZGto2QG-1Jets_Bin-PTG-200", "#2171B5", "Bin-PTG-200 (>200)"),
    ("ZGto2QG-1Jets_Bin-PTG-400", "#6BAED6", "Bin-PTG-400 (>400)"),
    ("ZGto2QG-1Jets_Bin-PTG-600", "#C6DBEF", "Bin-PTG-600 (>600)"),
]

COLS = ["weight", "GenFlavor", "Photon0_pt", "FatJet0_pt", "FatJet0_msd"]

VARS = [
    ("Photon0_pt", np.linspace(50, 650, 31), r"Photon $p_T$ [GeV]"),
    ("FatJet0_msd", np.linspace(40, 200, 33), r"FatJet $m_{SD}$ [GeV]"),
]


def make_plot(events, var, bins, xlabel, year, outpath, bb_only):
    plt.rcParams.update({"font.size": 22})
    fig, ax = plt.subplots(figsize=(10, 8))

    hists, colors, labels = [], [], []
    for name, color, label in SAMPLES:
        if name not in events:
            continue
        df = events[name]
        if bb_only:
            df = df[df["GenFlavor"] == 3]  # 3 = bb
        if df.empty:
            continue
        vals = df[var].fillna(-999).values
        w = df["finalWeight"].astype(float).values
        h = hist.Hist(hist.axis.Variable(bins, label=xlabel), storage=hist.storage.Weight())
        h.fill(vals, weight=w)
        hists.append(h); colors.append(color)
        labels.append(f"{label}  [{h.values().sum():.0f}]")

    if not hists:
        plt.close(fig); return

    hep.histplot(hists, stack=True, histtype="fill", label=labels, color=colors, ax=ax)
    ax.set_ylabel("Events / bin")
    ax.set_xlabel(xlabel)
    ax.set_yscale("log")
    ax.legend(fontsize="x-small", loc="upper right")
    sub = "GenFlavor=bb (signal template)" if bb_only else "all GenFlavor"
    ax.text(0.04, 0.95, f"control-zγ  —  ZGto2QG overlap  ({sub})",
            transform=ax.transAxes, fontsize=15, va="top")
    lumi_val = round(LUMI.get(year, 0) / 1000.0, 2)
    hep.cms.label(ax=ax, data=False, lumi=lumi_val, year=year, com=13.6)
    outpath.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(outpath, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved: {outpath}")


def main(args):
    data_dir = Path(args.data_dir) if args.data_dir else Path(
        f"/eos/uscms/store/group/lpchbbrun3/gmachado/{args.tag}/{args.year}")
    outdir = Path(args.outdir)
    region = "control-zgamma"
    print(f"\n=== control-zgamma ZGto2QG overlap: {args.year} [{data_dir}] ===\n")

    events = {}
    for name, _, _ in SAMPLES:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            loaded = utils.load_samples(
                data_dir=data_dir, samples={name: [name]}, columns=COLS, region=region)
        if loaded and name in loaded and not loaded[name].empty:
            events[name] = loaded[name]
            print(f"  Loaded {name}: {len(loaded[name]):,} events")
        else:
            print(f"  [skip] {name}: no parquets")

    if not events:
        print("ERROR: nothing loaded."); return

    tag = "_bb" if args.bb_only else "_allflav"
    for var, bins, xlabel in VARS:
        make_plot(events, var, bins, xlabel, args.year,
                  outdir / args.year / f"zgamma_overlap_{var}{tag}.png", args.bb_only)
    print(f"\nDone. Plots in: {outdir / args.year}/")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--year", required=True)
    p.add_argument("--tag", required=True)
    p.add_argument("--data-dir", default=None)
    p.add_argument("--outdir", default="plots/zgamma_overlap/")
    p.add_argument("--bb-only", action="store_true",
                   help="Restrict to GenFlavor==bb (the actual zgammabb signal template)")
    main(p.parse_args())
