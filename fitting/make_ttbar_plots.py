#!/usr/bin/env python3
"""
Z(μμ) control region stack plots, split by photon presence.
DY split into pT(ll) bins (PTLL-binned samples only — no inclusive 0J/1J/2J
to avoid double-counting in the boosted regime).

MC statistical uncertainty uses sum(w²) via hist.Hist.variances(),
consistent with python/plotting.py. Plot style matches python/plotting.py.

"""

from __future__ import annotations

import argparse
import json
import warnings
from pathlib import Path

import mplhep as hep
import numpy as np
import pandas as pd

from hbb import utils
from cr_plotting import make_stack_plot

hep.style.use("CMS")

# ---------------------------------------------------------------------------
# DY (Zll) sub-groups split by pT(ll)
#
# NOTE: ONLY PTLL-binned samples are used — NOT the inclusive 0J/1J/2J samples.
# The inclusive jet-multiplicity samples already cover all pT(ll); stacking them
# together with the PTLL-binned samples double-counts DY at high pT(ll) (the
# boosted regime where our selection lives), causing ~2x MC over-prediction.
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Other MC processes — loaded via pmap_run3.json
# ---------------------------------------------------------------------------
OTHER_PROCESSES = {
    "Wjets":   {"color": "#28B463", "label": "W+jets"},
    "ttbar":   {"color": "#E74C3C", "label": r"$t\bar{t}$"},
    "singlet": {"color": "#F39C12", "label": "Single t"},
    "VV":      {"color": "#9B59B6", "label": "VV"},
    "Zjets":  {"color": "#82E0AA", "label": r"Zjets"},
    "QCD":  {"color": "#85C1E9", "label": r"QCD"},
}

# Stack order: smallest contribution on top; lowest pT bin at bottom
STACK_ORDER = [
    "Wjets", "Zjets", "VV", "QCD",  "singlet",  "ttbar"
]

# Combined style lookup
PROC_STYLE: dict[str, dict] = {
    **OTHER_PROCESSES,
}

# ---------------------------------------------------------------------------
# Columns to load from parquet
# ---------------------------------------------------------------------------
COLS = [
    "weight",
    "GenFlavor",
    "GenBoson_pt",
    "nFatJet",
    "nJet",
    "nJet_outsideFatJet0",
    "nJet_opphemFatJet0",
    "nJet_outsideFatJet0_medBtag",
    "FatJet0_pt",
    "FatJet0_phi",
    "FatJet0_eta",
    "FatJet0_msd",
    "FatJet0_msdmatched",
    "FatJet1_pt",
    "FatJet1_phi",
    "FatJet1_eta",
    "FatJet1_msd",
    "VBFPair_mjj",
    "VBFPair_deta",
    "MET",
    "genWeight"
]

# ---------------------------------------------------------------------------
# Variable definitions: (column_or_derived, bins, xlabel)
# ---------------------------------------------------------------------------
NAK8_BINS = np.array([-0.5, 0.5, 1.5, 2.5, 3.5, 4.5])

VARS_BOTH = [
    ("FatJet0_pt",    np.linspace(450, 1200, 31),  r"$p_T(AK8)$ [GeV]"),
    ("FatJet0_msd",    np.linspace(40, 201, 23),  r"$m_{SD}(AK8)$ [GeV]"),
    ("MET",                np.linspace(0, 300, 31),   r"MET [GeV]"),
]

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(args: argparse.Namespace) -> None:
    year   = args.year
    tag    = args.tag
    outdir = Path(args.outdir)

    if args.data_dir:
        data_dir = Path(args.data_dir)
    elif args.personal_path:
        data_dir = Path(f"/eos/uscms/store/group/lpchbbrun3/gmachado/{tag}/{year}")
    else:
        data_dir = Path(f"/eos/uscms/store/group/lpchbbrun3/skims/{tag}/{year}")

    region = "control-tt"
    print(f"\n=== tt CR plots: {year}  [{data_dir}] ===\n")

    all_events: dict[str, pd.DataFrame] = {}

    # --- Load other MC + data via pmap ---
    with open(Path(__file__).parent / "pmap_run3.json") as f:
        pmap = json.load(f)

    for proc in list(OTHER_PROCESSES.keys()) + ["Muondata"]:
        if proc not in pmap:
            print(f"  [skip] {proc}: not in pmap")
            continue
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            loaded = utils.load_samples(
                data_dir=data_dir,
                samples={proc: pmap[proc]},
                columns=COLS,
                region=region,
            )
        if loaded and proc in loaded and not loaded[proc].empty:
            all_events[proc] = loaded[proc]
            print(f"  Loaded {proc}: {len(loaded[proc]):,} events")
        else:
            print(f"  [skip] {proc}: no parquets found")

    if not all_events:
        print("ERROR: No events loaded. Check --tag / --year / --personal-path.")
        return
    
    common_mask: dict[str, pd.Series] = {}
    for proc, df in all_events.items():
        common_mask[proc] = (df["FatJet0_pt"] >= 450) & (df["FatJet0_pt"] <= 1200) & (df["FatJet0_msd"] >= 40)  & (df["FatJet0_msd"] <= 201)
        

    print(f"\n--- Making Plots ({year}) ---")
    region_label = f"tt CR"
    for var, bins, xlabel in VARS_BOTH:
        outpath = outdir / year / f"ttbar_{var}.png"
        outpath.parent.mkdir(parents=True, exist_ok=True)
        make_stack_plot(
            all_events, common_mask, var, bins, region_label, xlabel,
            year, outpath, STACK_ORDER, PROC_STYLE, ylog=True
        )

    print(f"\nDone. Plots in: {outdir / year}/")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Z(μμ) CR stack plots")
    parser.add_argument("--year",    required=True,
                        help="Year: 2022, 2022EE, 2023, 2023BPix, 2024")
    parser.add_argument("--tag",     required=True, help="Skim tag, e.g. Test_v15")
    parser.add_argument("--outdir",  default="plots/ttbar/", help="Output directory")
    parser.add_argument(
        "--personal-path", action="store_true",
        help="Use personal EOS path (.../gmachado/...) instead of shared path",
    )
    parser.add_argument(
        "--data-dir",
        default=None,
        help="Full path to the directory containing the parquets for this year, "
             "e.g. /eos/uscms/store/group/lpchbbrun3/lara/MyTag/2024 "
             "Overrides --tag and --personal-path.",
    )
    args = parser.parse_args()
    main(args)
