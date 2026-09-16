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

import hist
import matplotlib.pyplot as plt
import mplhep as hep
import numpy as np
import pandas as pd
import uproot
from hist.intervals import ratio_uncertainty

from hbb import utils
from hbb.common_vars import LUMI

hep.style.use("CMS")

# ---------------------------------------------------------------------------
# DY (Zll) sub-groups split by pT(ll)
#
# NOTE: ONLY PTLL-binned samples are used — NOT the inclusive 0J/1J/2J samples.
# The inclusive jet-multiplicity samples already cover all pT(ll); stacking them
# together with the PTLL-binned samples double-counts DY at high pT(ll) (the
# boosted regime where our selection lives), causing ~2x MC over-prediction.
# ---------------------------------------------------------------------------
# For the mumu+GAMMA reference we want the DEDICATED Z(->ll)+gamma sample DYGto2LG
# (the mumu analog of the Zgamma->bb region's ZGto2QG). Inclusive DYto2Mu under-models
# hard-photon radiation (gives z_norm~2.9 artifact), so use DYGto2LG for consistency
# with the Zgamma->bb side. PTG bins >=100 all pass the offline Photon0_pt>120 cut.
# (For the plain no-photon mumu card, swap back to DYto2Mu-2Jets_MLL-50_{0,1,2}J.)
#
# We now load TWO leptonic-DY components as SEPARATE stack entries so the
# VGammaLep-vs-VJets_lep_NLO split is visible (group-meeting diagnostic):
#   Zmm_Zgamma = VGammaLep    = DYGto2LG  (Z->ll + gamma, matrix-element photon)
#   Zmm_DY     = VJets_lep_NLO = plain DYto2Mu (photons only from FSR/parton shower)
# In the photon-selected category BOTH contribute -> the Z(mumu)+gamma phase space
# is double-produced (overlap). Showing them separately quantifies that overlap;
# the actual overlap removal (gen-photon veto on plain DY) is a later step.
# NOTE: plain DY is PLOT-ONLY for now — it is intentionally NOT in
# DATACARD_PROC_MAP, so --save-root still writes the DYGto2LG-only reference card.
DY_GROUPS = {
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

# Stack order: smallest contribution on top; largest DY at the bottom
STACK_ORDER = [
    "Zgamma", "Wgamma", "VV", "singlet", "Wjets", "ttbar",
    "Zmm_Zgamma", "Zmm_DY",
]

# Combined style lookup
PROC_STYLE: dict[str, dict] = {
    **{k: {"color": v["color"], "label": v["label"]} for k, v in DY_GROUPS.items()},
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
]

VARS_GAMMA = [
    ("Photon0_pt",        np.linspace(100, 600, 26), r"Photon $p_T$ [GeV]"),
    ("dphi_photon_muon",  np.linspace(0, np.pi, 32), r"$\Delta\phi(\gamma, \mu_\mathrm{lead})$"),
    # Diagnostic for muon-FSR contamination: small ΔR = photon collinear with a
    # muon (FSR); large ΔR = genuine wide-angle (ISR/prompt) Z+gamma topology.
    ("dr_photon_muon",    np.linspace(0, 5, 26),     r"min $\Delta R(\gamma, \mu)$"),
]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def dphi(phi1: pd.Series, phi2: pd.Series) -> pd.Series:
    """Compute |Δφ| wrapped to [0, π]."""
    raw = np.abs(phi1.values - phi2.values)
    return pd.Series(np.where(raw > np.pi, 2 * np.pi - raw, raw), index=phi1.index)


def _dr(eta1, phi1, eta2, phi2) -> np.ndarray:
    """ΔR = sqrt(Δη² + Δφ²), Δφ wrapped to [0, π]. Numpy arrays in/out."""
    deta = np.asarray(eta1) - np.asarray(eta2)
    dp = np.abs(np.asarray(phi1) - np.asarray(phi2))
    dp = np.where(dp > np.pi, 2 * np.pi - dp, dp)
    return np.sqrt(deta ** 2 + dp ** 2)


def min_dr_photon_muon(df: pd.DataFrame) -> pd.Series:
    """min ΔR(leading photon, {lead, sublead} muon). NaN where no photon."""
    dr_lead = _dr(df["Photon0_eta"], df["Photon0_phi"],
                  df["Zmm_MuonLead_eta"], df["Zmm_MuonLead_phi"])
    dr_sub = _dr(df["Photon0_eta"], df["Photon0_phi"],
                 df["Zmm_MuonSubLead_eta"], df["Zmm_MuonSubLead_phi"])
    return pd.Series(np.minimum(dr_lead, dr_sub), index=df.index)


def get_values(df: pd.DataFrame, var: str) -> pd.Series:
    if var == "dphi_photon_muon":
        return dphi(df["Photon0_phi"], df["Zmm_MuonLead_phi"])
    if var == "dr_photon_muon":
        return min_dr_photon_muon(df)
    return df[var]


def make_stack_plot(
    all_events: dict[str, pd.DataFrame],
    selection_mask: dict[str, pd.Series],
    var: str,
    bins: np.ndarray,
    xlabel: str,
    year: str,
    category_label: str,
    outpath: Path,
) -> None:
    """
    Stack histogram + Data/MC ratio plot.

    MC statistical uncertainty uses hist.Hist.variances() = sum(w²) per bin,
    consistent with python/plotting.py. Style matches plotting.py.
    """
    plt.rcParams.update({"font.size": 24})
    fig, (ax, rax) = plt.subplots(
        2, 1,
        figsize=(10, 10),
        gridspec_kw={"height_ratios": [3, 1]},
        sharex=True,
    )
    plt.subplots_adjust(hspace=0)

    # ------------------------------------------------------------------
    # Build hist.Hist objects for each MC process.
    # hist.Hist automatically accumulates sum(w²) in .variances() when
    # events are filled with weights — this is the correct MC stat unc.
    # ------------------------------------------------------------------
    h_mc: dict[str, hist.Hist] = {}
    for proc in STACK_ORDER:
        if proc not in all_events:
            continue
        df = all_events[proc]
        mask = selection_mask.get(proc)
        if mask is not None:
            df = df[mask]
        if df.empty:
            continue

        vals = get_values(df, var).fillna(-999).values
        weights = df["finalWeight"].astype(float).values

        h = hist.Hist(hist.axis.Variable(bins, label=xlabel), storage=hist.storage.Weight())
        h.fill(vals, weight=weights)
        h_mc[proc] = h

    if not h_mc:
        plt.close(fig)
        return

    mc_ordered = [p for p in STACK_ORDER if p in h_mc]
    tot_mc = sum(h_mc[p] for p in mc_ordered)
    bin_edges = tot_mc.axes[0].edges

    # Stack fill
    hep.histplot(
        [h_mc[p] for p in mc_ordered],
        stack=True,
        histtype="fill",
        label=[PROC_STYLE[p]["label"] for p in mc_ordered],
        color=[PROC_STYLE[p]["color"] for p in mc_ordered],
        ax=ax,
    )

    # MC stat uncertainty band — sqrt(sum(w²)) from hist.variances()
    mc_vals = tot_mc.values()
    mc_vars = tot_mc.variances()
    mc_err  = np.sqrt(np.where(mc_vars > 0, mc_vars, 0))
    ax.stairs(
        np.maximum(mc_vals + mc_err, 0),
        bin_edges,
        baseline=np.maximum(mc_vals - mc_err, 0),
        fill=True,
        color="gray",
        alpha=0.4,
        label="MC stat. unc.",
        zorder=3,
    )

    # Data — filled with weight=1, so variances() == values() == counts (Poisson)
    h_data: hist.Hist | None = None
    if "Muondata" in all_events:
        df_data = all_events["Muondata"]
        mask = selection_mask.get("Muondata")
        if mask is not None:
            df_data = df_data[mask]
        if not df_data.empty:
            vals_data = get_values(df_data, var).fillna(-999).values
            h_data = hist.Hist(hist.axis.Variable(bins, label=xlabel), storage=hist.storage.Weight())
            h_data.fill(vals_data)
            hep.histplot(
                h_data,
                histtype="errorbar",
                color="k",
                label="Data",
                xerr=True,
                ax=ax,
                zorder=4,
            )

    # Axes and labels
    ax.set_ylabel("Events / bin")
    ax.set_xlabel(None)
    ax.xaxis.grid(True, which="major")
    ax.yaxis.grid(True, which="major")

    # Legend — style from plotting.py
    handles, labels = ax.get_legend_handles_labels()
    ax.legend(
        handles,
        labels,
        ncol=2,
        fontsize="x-small",
        labelspacing=0.2,
        columnspacing=0.8,
        handlelength=1.0,
        handleheight=0.8,
        loc="upper right",
        markerscale=0.7,
    )
    hep.yscale_legend(ax, soft_fail=True)

    lumi_val = round(LUMI.get(year, 0) / 1000.0, 2)
    hep.cms.label(ax=ax, data=(h_data is not None), lumi=lumi_val, year=year, com=13.6)
    ax.text(
        0.05, 0.95, f"Z(μμ) CR — {category_label}",
        transform=ax.transAxes, fontsize=18,
        verticalalignment="top",
    )

    # ------------------------------------------------------------------
    # Ratio panel: Data/MC with Poisson uncertainty on data
    # Uses ratio_uncertainty() from hist.intervals — same as plotting.py
    # ------------------------------------------------------------------
    if h_data is not None and mc_vals.sum() > 0:
        data_vals = h_data.values()
        ratio = np.where(mc_vals > 0, data_vals / mc_vals, np.nan)
        yerr  = ratio_uncertainty(data_vals, mc_vals, "poisson")

        hep.histplot(
            ratio,
            bin_edges,
            ax=rax,
            yerr=yerr,
            histtype="errorbar",
            color="k",
            xerr=True,
            zorder=4,
        )
        rax.axhline(1, color="gray", ls="--", linewidth=1)
        rax.set_ylim(0, 2.2)
        rax.set_ylabel(r"$\frac{\mathrm{Data}}{\mathrm{Bkg}}$", y=0.5)
    else:
        rax.set_visible(False)

    rax.set_xlabel(xlabel)
    rax.xaxis.grid(True, which="major")
    rax.yaxis.grid(True, which="major")

    # Auto-zoom x-axis: skip leading/trailing empty bins
    combined = mc_vals.copy()
    if h_data is not None:
        combined = combined + h_data.values()
    nonzero = np.where(combined > 0)[0]
    if len(nonzero) > 0:
        x_min = bins[max(0, nonzero[0] - 1)]
        x_max = bins[min(len(bins) - 1, nonzero[-1] + 2)]
        ax.set_xlim(x_min, x_max)
        rax.set_xlim(x_min, x_max)

    fig.savefig(outpath, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved: {outpath}")


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
) -> None:
    """
    Write mll histograms to a ROOT file in the format expected by
    make_zmmcr_datacard.py:
        zmmcr_inclusive_pt1_{proc}_nominal
    """
    # Accumulate sumw and sumw2 per datacard process
    merged: dict[str, tuple[np.ndarray, np.ndarray]] = {}

    for plotter_proc, dc_proc in DATACARD_PROC_MAP.items():
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
    global DY_GROUPS, STACK_ORDER, PROC_STYLE, DATACARD_PROC_MAP
    year   = args.year
    tag    = args.tag
    outdir = Path(args.outdir)

    if args.data_dir:
        data_dir = Path(args.data_dir)
    elif args.personal_path:
        data_dir = Path(f"/eos/uscms/store/group/lpchbbrun3/gmachado/{tag}/{year}")
    else:
        data_dir = Path(f"/eos/uscms/store/group/lpchbbrun3/skims/{tag}/{year}")

    region = "control-zmumu"
    print(f"\n=== Z(μμ) CR plots: {year}  [{data_dir}] ===\n")

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
        STACK_ORDER = (
            ["Zgamma", "Wgamma", "VV", "singlet", "Wjets", "ttbar"]
            + dyg_keys + ["Zmm_DY"]
        )
        PROC_STYLE = {
            **{k: {"color": v["color"], "label": v["label"]} for k, v in DY_GROUPS.items()},
            **OTHER_PROCESSES,
        }
        DATACARD_PROC_MAP = {
            "Muondata": "data_obs",
            **{k: "Zjets" for k in dyg_keys},
            "Wjets": "Wjets", "ttbar": "ttbar", "VV": "VV", "singlet": "singlet",
        }
        print("  [split-dyg-ptg] DYGto2LG split into 4 PTG-bin components")

    all_events: dict[str, pd.DataFrame] = {}

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
        save_root_histograms(all_events, root_mask, year, root_path)

    # --- No-photon category ---
    print(f"\n--- No-photon category ({year}) ---")
    for var, bins, xlabel in VARS_BOTH:
        outpath = outdir / year / f"zmumu_nophoton_{var}.png"
        outpath.parent.mkdir(parents=True, exist_ok=True)
        make_stack_plot(
            all_events, no_photon_mask, var, bins, xlabel,
            year, "No photon", outpath,
        )

    # --- Gamma category ---
    print(f"\n--- Gamma category ({year}) ---")
    for var, bins, xlabel in VARS_BOTH + VARS_GAMMA:
        outpath = outdir / year / f"zmumu_gamma_{var}.png"
        make_stack_plot(
            all_events, gamma_mask, var, bins, xlabel,
            year, rf"$\geq$1 tight $\gamma$ ($p_T>${PHOTON_PT_CUT:.0f} GeV)", outpath,
        )

    print(f"\nDone. Plots in: {outdir / year}/")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Z(μμ) CR stack plots")
    parser.add_argument("--year",    required=True,
                        help="Year: 2022, 2022EE, 2023, 2023BPix, 2024")
    parser.add_argument("--tag",     required=True, help="Skim tag, e.g. Test_v15")
    parser.add_argument("--outdir",  default="plots/zmumu/", help="Output directory")
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
        help="Also write mll ROOT histograms for make_zmmcr_datacard.py",
    )
    parser.add_argument(
        "--outdir-root", default=None,
        help="Directory for ROOT output (default: <outdir>/root/)",
    )
    parser.add_argument(
        "--dyg-bins", type=str, default=None,
        help="Comma-separated DYGto2LG PTG bins to use in the merged Z(μμ)γ, "
             "e.g. '100' for PTG-100 only, or '100,200,400,600' (default = all four). "
             "Ignored if --split-dyg-ptg is set.",
    )
    parser.add_argument(
        "--split-dyg-ptg", action="store_true",
        help="Split DYGto2LG into its 4 PTG bins (100/200/400/600), each its own "
             "color, to check the photon-pT stitching. Default: merged as one Z(μμ)γ.",
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
