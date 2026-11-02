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
import uproot

from hbb import utils

from cr_plotting import make_stack_plot, describe_df_weight, min_dr_photon_muon

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
# For the mumu+GAMMA reference we want the DEDICATED Z(->ll)+gamma sample DYGto2LG
# (the mumu analog of the Zgamma->bb region's ZGto2QG). Inclusive DYto2Mu under-models
# hard-photon radiation (gives z_norm~2.9 artifact), so use DYGto2LG for consistency
# with the Zgamma->bb side. PTG bins >=100 all pass the offline Photon0_pt>120 cut.
#
# We load TWO leptonic-DY components as SEPARATE stack entries so the
# VGammaLep-vs-VJets_lep_NLO split is visible (group-meeting diagnostic):
#   Zmm_Zgamma = VGammaLep    = DYGto2LG  (Z->ll + gamma, matrix-element photon)
#   Zmm_DY     = VJets_lep_NLO = plain DYto2Mu (photons only from FSR/parton shower)
# In the photon-selected category BOTH contribute -> the Z(mumu)+gamma phase space
# is double-produced (overlap). Showing them separately quantifies that overlap;
# the actual overlap removal (gen-photon veto on plain DY) is a later step.
# NOTE: plain DY is PLOT-ONLY for now — it is intentionally NOT in
# DATACARD_PROC_MAP, so --save-root still writes the DYGto2LG-only reference card.
# Selected with --DY-comp dyg.
# ---------------------------------------------------------------------------
DY_GROUPS_DYG = {
    "Zmm_Zgamma": {
        "datasets": [
            "DYGto2LG-1Jets_Bin-MLL-50-PTG-100",
            "DYGto2LG-1Jets_Bin-MLL-50-PTG-200",
            "DYGto2LG-1Jets_Bin-MLL-50-PTG-400",
            "DYGto2LG-1Jets_Bin-MLL-50-PTG-600",
        ],
        "color": "#2471A3",
        "label": r"Z($\mu\mu$)$\gamma$ (DYG, ME)",
    },
    # Plain Drell-Yan (VJets_lep_NLO). Jet-multiplicity-split muon channel only
    # (0J/1J/2J) — do NOT also add the PTLL-binned DYto2L samples, that would
    # double-count DY within this group (see note above).
    "Zmm_DY": {
        "datasets": [
            "DYto2Mu-2Jets_MLL-50_0J",
            "DYto2Mu-2Jets_MLL-50_1J",
            "DYto2Mu-2Jets_MLL-50_2J",
        ],
        "color": "#AED6F1",
        "label": r"Z($\mu\mu$) DY (FSR $\gamma$)",
    },
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
    "Zll_DYto2Mu","Zll_DYto2E",
    "Zmm_Zgamma", "Zmm_DY",
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
PROC_STYLE_DYG: dict[str, dict] = {
    **{k: {"color": v["color"], "label": v["label"]} for k, v in DY_GROUPS_DYG.items()},
    **OTHER_PROCESSES,
}

# ---------------------------------------------------------------------------
# Columns to load from parquet
# ---------------------------------------------------------------------------
COLS = [
    "weight",
    "GenFlavor",
    "Zmm_MuonLead_pt",
    "Zmm_MuonLead_eta",
    "Zmm_MuonLead_phi",
    "Zmm_MuonSublead_pt",
    # NB: skim casing is inconsistent — pt is "Sublead", eta/phi are "SubLead"
    # (see categorizer.py output_array_zmm). Match the parquet spelling exactly.
    "Zmm_MuonSubLead_eta",
    "Zmm_MuonSubLead_phi",
    "Zmm_MuonPair_mll",
    "Zmm_MuonPair_pt",
    "Zmm_ntightPhotons",
    "Zmm_nak8",
    "Photon0_pt",
    "Photon0_eta",
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
    # Diagnostic for muon-FSR contamination: small ΔR = photon collinear with a
    # muon (FSR); large ΔR = genuine wide-angle (ISR/prompt) Z+gamma topology.
    ("dr_photon_muon",    np.linspace(0, 5, 26),     r"min $\Delta R(\gamma, \mu)$"),
]

# ---------------------------------------------------------------------------
# ROOT histogram export (for make_zmmcr_datacard.py)
# ---------------------------------------------------------------------------
# Fit observable: mll in [60, 120] GeV with 30 bins (2 GeV/bin)
MLL_FIT_BINS = np.linspace(60, 120, 31)

# Map plotter process names → datacard process names
# All DY sub-groups are merged into a single "Zjets"
DATACARD_PROC_MAP = {
    "Muondata":          "data_obs",
    "Zmm_Zgamma":        "Zjets",
    "Wjets":             "Wjets",
    "ttbar":             "ttbar",
    "VV":                "VV",
    "singlet":           "singlet",
}


def save_root_histograms(
    all_events: dict[str, pd.DataFrame],
    selection_mask: dict[str, pd.Series],
    year: str,
    outpath: Path,
    proc_map: dict[str, str] = DATACARD_PROC_MAP,
) -> None:
    """
    Write mll histograms to a ROOT file in the format expected by
    make_zmmcr_datacard.py:
        zmmcr_inclusive_pt1_{proc}_nominal
    """
    # Accumulate sumw and sumw2 per datacard process
    merged: dict[str, tuple[np.ndarray, np.ndarray]] = {}

    for plotter_proc, dc_proc in proc_map.items():
        if plotter_proc not in all_events:
            continue
        df   = all_events[plotter_proc]
        mask = selection_mask.get(plotter_proc)
        if mask is not None:
            df = df[mask]
        if df.empty:
            continue

        mll_vals = df["Zmm_MuonPair_mll"].values
        is_data  = "data" in plotter_proc.lower()
        weights  = np.ones(len(df)) if is_data else df["finalWeight"].astype(float).values

        sumw, _  = np.histogram(mll_vals, bins=MLL_FIT_BINS, weights=weights)
        sumw2, _ = np.histogram(mll_vals, bins=MLL_FIT_BINS, weights=weights ** 2)

        if dc_proc in merged:
            merged[dc_proc] = (merged[dc_proc][0] + sumw, merged[dc_proc][1] + sumw2)
        else:
            merged[dc_proc] = (sumw, sumw2)

    outpath.parent.mkdir(parents=True, exist_ok=True)
    with uproot.recreate(outpath) as f:
        for dc_proc, (sumw, sumw2) in merged.items():
            key = f"zmmcr_inclusive_pt1_{dc_proc}_nominal"
            f[key] = (sumw, MLL_FIT_BINS)
            print(f"  [{dc_proc:12s}]  yield = {sumw.sum():.1f}  → {key}")

    print(f"\n  ROOT file written: {outpath}")

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
    stack_order = STACK_ORDER
    proc_map = DATACARD_PROC_MAP

    # The DYG-specific options and the datacard export need the DYGto2LG grouping
    if args.DY_comp != "dyg" and (args.dyg_bins or args.split_dyg_ptg or args.save_root):
        print(f"  [DY-comp] --dyg-bins/--split-dyg-ptg/--save-root need DYGto2LG: "
              f"switching --DY-comp {args.DY_comp} -> dyg")
        args.DY_comp = "dyg"

    if args.DY_comp == "flavor-binned":
        DY_GROUPS = DY_GROUPS_FLAVOR
        PROC_STYLE = PROC_STYLE_FLAVOR
        outdir = Path(f"{args.outdir}/DY_flavor/") 
        
    elif args.DY_comp == "pt-binned":
        DY_GROUPS = DY_GROUPS_PT
        PROC_STYLE = PROC_STYLE_PT
        outdir = Path(f"{args.outdir}/DY_pt/") 

    elif args.DY_comp == "dyg":
        DY_GROUPS = {k: dict(v) for k, v in DY_GROUPS_DYG.items()}
        PROC_STYLE = PROC_STYLE_DYG
        outdir = Path(f"{args.outdir}/DY_dyg/")

        # --- Optional: restrict which DYGto2LG PTG bins go into the merged Z(μμ)γ ---
        # e.g. --dyg-bins 100 -> use ONLY PTG-100 (the inclusive photon-pT>100 sample),
        # to test whether the 4 samples are inclusive-above (stacking double-counts)
        # vs exclusive bins. Ignored when --split-dyg-ptg is set.
        if args.dyg_bins and not args.split_dyg_ptg:
            bins = [b.strip() for b in args.dyg_bins.split(",") if b.strip()]
            DY_GROUPS["Zmm_Zgamma"]["datasets"] = [
                f"DYGto2LG-1Jets_Bin-MLL-50-PTG-{b}" for b in bins
            ]
            DY_GROUPS["Zmm_Zgamma"]["label"] = rf"Z($\mu\mu$)$\gamma$ (PTG-{'+'.join(bins)})"
            PROC_STYLE = {
                **{k: {"color": v["color"], "label": v["label"]} for k, v in DY_GROUPS.items()},
                **OTHER_PROCESSES,
            }
            print(f"  [dyg-bins] merged Z(μμ)γ uses DYGto2LG PTG bins: {bins}")

        # --- Optional: split DYGto2LG into its 4 PTG bins (stitching diagnostic) ---
        # Each PTG bin gets its own color (dark->light blue ramp) so the Photon0_pt
        # stack shows whether the bins tile cleanly at 100/200/400/600 with no
        # gap or double-count at the boundaries. Plain DY recolored gray to stand
        # apart from the ramp. All PTG bins still map to Zjets in the datacard.
        if args.split_dyg_ptg:
            ptgs = ["100", "200", "400", "600"]
            ramp = ["#08306B", "#2171B5", "#6BAED6", "#C6DBEF"]
            new_groups = {
                f"Zmm_DYG_PTG{p}": {
                    "datasets": [f"DYGto2LG-1Jets_Bin-MLL-50-PTG-{p}"],
                    "color": col,
                    "label": rf"DYG PTG-{p}",
                }
                for p, col in zip(ptgs, ramp)
            }
            new_groups["Zmm_DY"] = {**DY_GROUPS["Zmm_DY"], "color": "#95A5A6"}
            DY_GROUPS = new_groups
            dyg_keys = [f"Zmm_DYG_PTG{p}" for p in ptgs]
            stack_order = (
                ["Zgamma", "Wgamma", "VV", "singlet", "Wjets", "ttbar"]
                + dyg_keys + ["Zmm_DY"]
            )
            PROC_STYLE = {
                **{k: {"color": v["color"], "label": v["label"]} for k, v in DY_GROUPS.items()},
                **OTHER_PROCESSES,
            }
            proc_map = {
                "Muondata": "data_obs",
                **{k: "Zjets" for k in dyg_keys},
                "Wjets": "Wjets", "ttbar": "ttbar", "VV": "VV", "singlet": "singlet",
            }
            print("  [split-dyg-ptg] DYGto2LG split into 4 PTG-bin components")


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
            # Optional photon-muon separation cut: removes muon-FSR photons
            # (photon collinear with a muon), biasing toward the genuine
            # wide-angle Z+gamma topology. NaN ΔR (no photon) -> comparison
            # is False, which is fine since those events fail has_photon anyway.
            if args.dr_gamma_mu is not None:
                mindr = min_dr_photon_muon(df)
                has_photon = has_photon & (mindr > args.dr_gamma_mu)
            gamma_mask[proc] = has_photon
        else:
            no_photon_mask[proc] = pd.Series(True, index=df.index)
            gamma_mask[proc] = pd.Series(False, index=df.index)

    if args.dr_gamma_mu is not None:
        print(f"  [gamma cut] min ΔR(γ, μ) > {args.dr_gamma_mu} applied")

    # --- Save ROOT histograms for datacard ---
    if args.save_root:
        root_outdir = Path(args.outdir_root) if args.outdir_root else outdir / "root"
        if args.gamma:
            # mumu+gamma (Zgamma->mumu) selection: same production as Zgamma->bb
            root_mask = gamma_mask
            root_path = root_outdir / f"fitting_{year}_zmmcr_gamma_mll.root"
            sel_label = "mumu+gamma (>=1 tight photon, Photon0_pt>120)"
        else:
            root_mask = no_photon_mask
            root_path = root_outdir / f"fitting_{year}_zmmcr_mll.root"
            sel_label = "no-photon (plain DY)"
        print(f"\n--- Saving ROOT histograms ({year}) [{sel_label}] ---")
        save_root_histograms(all_events, root_mask, year, root_path, proc_map)

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
            year, outpath, stack_order, PROC_STYLE
        )

    # --- Gamma category ---
    print(f"\n--- Gamma category ({year}) ---")
    region_label = f"Z(μμ) CR — $\geq$1 tight $\gamma$ ($p_T>${PHOTON_PT_CUT:.0f} GeV)"
    for var, bins, xlabel in VARS_BOTH + VARS_GAMMA:
        outpath = outdir / year / f"zmumu_gamma_{var}.png"
        make_stack_plot(
            all_events, gamma_mask, var, bins, region_label, xlabel,
            year, outpath, stack_order, PROC_STYLE
        )

    print(f"\nDone. Plots in: {outdir / year}/")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Z(μμ) CR stack plots")
    parser.add_argument("--year",    required=True,
                        help="Year: 2022, 2022EE, 2023, 2023BPix, 2024")
    parser.add_argument("--tag",     required=True, help="Skim tag, e.g. Test_v15")
    parser.add_argument(
        "--DY-comp",
        help="Which Drell-Yan process groups to plot: flavor-binned, pt-binned, "
             "or dyg (DYGto2LG Z(μμ)γ + plain DYto2Mu, used for the datacard export)",
        type=str,
        default="flavor-binned",
        choices=["flavor-binned", "pt-binned", "dyg"],
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
    parser.add_argument(
        "--save-root", action="store_true",
        help="Also write mll ROOT histograms for make_zmmcr_datacard.py (implies --DY-comp dyg)",
    )
    parser.add_argument(
        "--outdir-root", default=None,
        help="Directory for ROOT output (default: <outdir>/root/)",
    )
    parser.add_argument(
        "--dyg-bins", type=str, default=None,
        help="Comma-separated DYGto2LG PTG bins to use in the merged Z(μμ)γ, "
             "e.g. '100' for PTG-100 only, or '100,200,400,600' (default = all four). "
             "Ignored if --split-dyg-ptg is set. Implies --DY-comp dyg.",
    )
    parser.add_argument(
        "--split-dyg-ptg", action="store_true",
        help="Split DYGto2LG into its 4 PTG bins (100/200/400/600), each its own "
             "color, to check the photon-pT stitching. Default: merged as one Z(μμ)γ. "
             "Implies --DY-comp dyg.",
    )
    parser.add_argument(
        "--dr-gamma-mu", type=float, default=None,
        help="If set, require min ΔR(photon, muon) > this value in the gamma "
             "category (removes muon-FSR photons). Default: no ΔR cut. Use the "
             "'min ΔR(γ, μ)' diagnostic plot to choose a threshold (e.g. 0.4).",
    )
    parser.add_argument(
        "--gamma", action="store_true",
        help="Save the datacard ROOT using the mumu+gamma (>=1 tight photon, "
             "Photon0_pt>120) selection instead of the no-photon one. This makes "
             "the Z->mumu CR the SAME production (Zgamma) as the Z+gamma->bb signal, "
             "so z_norm absorbs the Zgamma normalization (see METHOD_NOTE_tagsf.md §4b).",
    )
    args = parser.parse_args()
    main(args)
