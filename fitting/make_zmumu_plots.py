#!/usr/bin/env python3
"""
Z(μμ) control region stack plots, split by photon presence.
DY split into pT(ll) bins (PTLL-binned samples only — no inclusive 0J/1J/2J
to avoid double-counting in the boosted regime).

MC statistical uncertainty uses sum(w²) via hist.Hist.variances(),
consistent with python/plotting.py. Plot style matches python/plotting.py.

Produces:
  - No-photon category:  lead μ pT, sublead μ pT, pt(μμ), MET, n(AK8 jets)
  - Gamma category (>=1 tight photon, pT>120 GeV):
                         lead μ pT, sublead μ pT, pt(μμ), MET, n(AK8 jets),
                         photon pT, Δφ(γ, lead μ)

Usage (from fitting/):
  # 2024 (personal EOS path):
  python make_zmumu_plots.py --year 2024 --tag Test_v15 --outdir plots/zmumu/ --personal-path

  # Older years (personal EOS path, different tag):
  for year in 2022 2022EE 2023 2023BPix; do
      python make_zmumu_plots.py --year $year --tag Test_v15_v14_private --outdir plots/zmumu/ --personal-path
  done
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

from cr_plotting import make_stack_plot, describe_df_weight

hep.style.use("CMS")

# ---------------------------------------------------------------------------
# DY (Zll) sub-groups split by pT(ll)
#
# NOTE: ONLY PTLL-binned samples are used — NOT the inclusive 0J/1J/2J samples.
# The inclusive jet-multiplicity samples already cover all pT(ll); stacking them
# together with the PTLL-binned samples double-counts DY at high pT(ll) (the
# boosted regime where our selection lives), causing ~2x MC over-prediction.
# ---------------------------------------------------------------------------
DY_GROUPS_PT = {
    "Zll_PTLL_100to200": {
        "datasets": [
            "DYto2L-2Jets_MLL-50_PTLL-100to200_1J",
            "DYto2L-2Jets_MLL-50_PTLL-100to200_2J",
        ],
        "color": "#2471A3",
        "label": r"DY $p_T^{ll}$ 100–200",
    },
    "Zll_PTLL_200to400": {
        "datasets": [
            "DYto2L-2Jets_MLL-50_PTLL-200to400_1J",
            "DYto2L-2Jets_MLL-50_PTLL-200to400_2J",
        ],
        "color": "#2E86C1",
        "label": r"DY $p_T^{ll}$ 200–400",
    },
    "Zll_PTLL_400to600": {
        "datasets": [
            "DYto2L-2Jets_MLL-50_PTLL-400to600_1J",
            "DYto2L-2Jets_MLL-50_PTLL-400to600_2J",
        ],
        "color": "#5DADE2",
        "label": r"DY $p_T^{ll}$ 400–600",
    },
    "Zll_PTLL_600": {
        "datasets": [
            "DYto2L-2Jets_MLL-50_PTLL-600_1J",
            "DYto2L-2Jets_MLL-50_PTLL-600_2J",
        ],
        "color": "#AED6F1",
        "label": r"DY $p_T^{ll}$ >600",
    },
}

DY_GROUPS_FLAVOR = {
    "Zll_DYto2E": {
        "datasets": [
            "DYto2E-2Jets_MLL-50_0J",
            "DYto2E-2Jets_MLL-50_1J",
            "DYto2E-2Jets_MLL-50_2J",
        ],
        "color": "#2471A3",
        "label": r"DY to 2E",
    },
    "Zll_DYto2Mu": {
        "datasets": [
            "DYto2Mu-2Jets_MLL-50_0J",
            "DYto2Mu-2Jets_MLL-50_1J",
            "DYto2Mu-2Jets_MLL-50_2J",
        ],
        "color": "#2E86C1",
        "label": r"DY to 2Mu",
    }
}

# ---------------------------------------------------------------------------
# Other MC processes — loaded via pmap_run3.json
# ---------------------------------------------------------------------------
OTHER_PROCESSES = {
    "Wjets":   {"color": "#28B463", "label": "W+jets"},
    "ttbar":   {"color": "#E74C3C", "label": r"$t\bar{t}$"},
    "singlet": {"color": "#F39C12", "label": "Single t"},
    "VV":      {"color": "#9B59B6", "label": "VV"},
    "Wgamma":  {"color": "#82E0AA", "label": r"W$\gamma$"},
    "Zgamma":  {"color": "#85C1E9", "label": r"Z$\gamma$"},
}

# Stack order: smallest contribution on top; lowest pT bin at bottom
STACK_ORDER = [
    "Zgamma", "Wgamma", "VV", "singlet", "Wjets", "ttbar",
    "Zll_PTLL_600", "Zll_PTLL_400to600", "Zll_PTLL_200to400", "Zll_PTLL_100to200",
    "Zll_DYto2Mu","Zll_DYto2E"
]

# Combined style lookup
PROC_STYLE_PT: dict[str, dict] = {
    **{k: {"color": v["color"], "label": v["label"]} for k, v in DY_GROUPS_PT.items()},
    **OTHER_PROCESSES,
}
PROC_STYLE_FLAVOR: dict[str, dict] = {
    **{k: {"color": v["color"], "label": v["label"]} for k, v in DY_GROUPS_FLAVOR.items()},
    **OTHER_PROCESSES,
}

# ---------------------------------------------------------------------------
# Columns to load from parquet
# ---------------------------------------------------------------------------
COLS = [
    "weight",
    "GenFlavor",
    "Zmm_MuonLead_pt",
    "Zmm_MuonLead_phi",
    "Zmm_MuonSublead_pt",
    "Zmm_MuonPair_mll",
    "Zmm_MuonPair_pt",
    "Zmm_ntightPhotons",
    "Zmm_nak8",
    "Photon0_pt",
    "Photon0_phi",
    "MET",
    "genWeight"
]

# ---------------------------------------------------------------------------
# Variable definitions: (column_or_derived, bins, xlabel)
# ---------------------------------------------------------------------------
NAK8_BINS = np.array([-0.5, 0.5, 1.5, 2.5, 3.5, 4.5])

VARS_BOTH = [
    ("Zmm_MuonPair_mll",   np.linspace(80, 100, 21), r"$m(\mu\mu)$ [GeV]"),
    ("Zmm_MuonLead_pt",    np.linspace(0, 500, 26),  r"Lead muon $p_T$ [GeV]"),
    ("Zmm_MuonSublead_pt", np.linspace(0, 400, 26),  r"Sublead muon $p_T$ [GeV]"),
    ("Zmm_MuonPair_pt",    np.linspace(0, 600, 31),  r"$p_T(\mu\mu)$ [GeV]"),
    ("MET",                np.linspace(0, 300, 31),   r"MET [GeV]"),
    ("Zmm_nak8",           NAK8_BINS,                 r"Number of AK8 jets"),
    ("genWeight",           np.linspace(-10000,0,100),                 r"genWeight"),
]

VARS_GAMMA = [
    ("Photon0_pt",        np.linspace(100, 600, 26), r"Photon $p_T$ [GeV]"),
    ("dphi_photon_muon",  np.linspace(0, np.pi, 32), r"$\Delta\phi(\gamma, \mu_\mathrm{lead})$"),
]

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(args: argparse.Namespace) -> None:
    year   = args.year
    tag    = args.tag

    if args.data_dir:
        data_dir = Path(args.data_dir)
    elif args.personal_path:
        data_dir = Path(f"/eos/uscms/store/group/lpchbbrun3/gmachado/{tag}/{year}")
    else:
        data_dir = Path(f"/eos/uscms/store/group/lpchbbrun3/skims/{tag}/{year}")

    region = "control-zmumu"
    print(f"\n=== Z(μμ) CR plots: {year}  [{data_dir}] ===\n")

    all_events: dict[str, pd.DataFrame] = {}
    
    if args.DY_comp == "flavor-binned":
        DY_GROUPS = DY_GROUPS_FLAVOR
        PROC_STYLE = PROC_STYLE_FLAVOR
        outdir = Path(f"{args.outdir}/DY_flavor/") 
        
    elif args.DY_comp == "pt-binned":
        DY_GROUPS = DY_GROUPS_PT
        PROC_STYLE = PROC_STYLE_PT
        outdir = Path(f"{args.outdir}/DY_pt/") 
        

    # --- Load DY pT-bin sub-groups (inline dataset lists) ---
    for proc, info in DY_GROUPS.items():
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            loaded = utils.load_samples(
                data_dir=data_dir,
                samples={proc: info["datasets"]},
                columns=COLS,
                region=region,
            )
        if loaded and proc in loaded and not loaded[proc].empty:
            all_events[proc] = loaded[proc]
            print(f"  Loaded {proc}: {len(loaded[proc]):,} events")
        else:
            print(f"  [skip] {proc}: no parquets found")

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

    # --- Photon-split category masks ---
    # Note: mll and pT(mumu)>300 cuts are already applied at processor level.
    PHOTON_PT_CUT = 120.0
    no_photon_mask: dict[str, pd.Series] = {}
    gamma_mask:     dict[str, pd.Series] = {}

    for proc, df in all_events.items():
        if "Zmm_ntightPhotons" in df.columns:
            no_photon_mask[proc] = df["Zmm_ntightPhotons"] == 0
            has_photon = df["Zmm_ntightPhotons"] >= 1
            if "Photon0_pt" in df.columns:
                has_photon = has_photon & (df["Photon0_pt"] > PHOTON_PT_CUT)
            gamma_mask[proc] = has_photon
        else:
            no_photon_mask[proc] = pd.Series(True, index=df.index)
            gamma_mask[proc] = pd.Series(False, index=df.index)

    if args.debug:
        print("-------------------------------------")
        for proc, df in all_events.items():
            describe_df_weight(proc, df)
        print("-------------------------------------")

        for proc, df in all_events.items():
            mask = no_photon_mask.get(proc, pd.Series(True, index=df.index))
            sw = df.loc[mask, "finalWeight"].sum()
            sw = df.loc[mask, "finalWeight"].sum()
            print(f"{proc}: {mask.sum():,} events, sum(finalWeight) = {sw:.2f}")
        
        print("-------------------------------------")
        
    # --- No-photon category ---
    print(f"\n--- No-photon category ({year}) ---")
    region_label = f"Z(μμ) CR — No photon"
    for var, bins, xlabel in VARS_BOTH:
        outpath = outdir / year / f"zmumu_nophoton_{var}.png"
        outpath.parent.mkdir(parents=True, exist_ok=True)
        make_stack_plot(
            all_events, no_photon_mask, var, bins, region_label, xlabel,
            year, outpath, STACK_ORDER, PROC_STYLE
        )

    # --- Gamma category ---
    print(f"\n--- Gamma category ({year}) ---")
    region_label = f"Z(μμ) CR — $\geq$1 tight $\gamma$ ($p_T>${PHOTON_PT_CUT:.0f} GeV)"
    for var, bins, xlabel in VARS_BOTH + VARS_GAMMA:
        outpath = outdir / year / f"zmumu_gamma_{var}.png"
        make_stack_plot(
            all_events, gamma_mask, var, bins, region_label, xlabel,
            year, outpath, STACK_ORDER, PROC_STYLE
        )

    print(f"\nDone. Plots in: {outdir / year}/")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Z(μμ) CR stack plots")
    parser.add_argument("--year",    required=True,
                        help="Year: 2022, 2022EE, 2023, 2023BPix, 2024")
    parser.add_argument("--tag",     required=True, help="Skim tag, e.g. Test_v15")
    parser.add_argument(
        "--DY-comp",
        help="Which Drell-Yan process groups to plot: flavor-binned or pt-binned",
        type=str,
        default="flavor-binned",
        choices=["flavor-binned", "pt-binned"],
    )
    parser.add_argument("--outdir",  default="plots/zmumu/", help="Output directory")
    parser.add_argument("--debug", action="store_true", help="Enter debug mode")
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
