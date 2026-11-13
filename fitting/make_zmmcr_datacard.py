#!/usr/bin/env python3
"""
make_zmmcr_datacard.py
----------------------
Build the Z→μμ control region datacard.

The Z→μμ CR is a simple template fit to the dimuon invariant mass (mll)
distribution. No QCD transfer factor is needed — the dominant process is
DY (Z→μμ, grouped as 'zmm'), with small ttbar, W+jets, and other backgrounds.

The resulting datacard is intended for use in the combined fit alongside the
Z+γ CR, where the shared JMS/JMR nuisance parameters are constrained.

Input ROOT files are produced by:
    python make_hists.py --region zmmcr --year <year> --tag <tag> ...

Usage:
    python make_zmmcr_datacard.py --year 2022 --tag 26May18
    python make_zmmcr_datacard.py --year 2022 --tag 26May18 --indir /path/to/hists --outdir results/zmmcr
"""

from __future__ import annotations

import argparse
import json
import warnings
from pathlib import Path

import numpy as np
import rhalphalib as rl
import uproot

warnings.filterwarnings("ignore")
rl.util.install_roofit_helpers()

from hbb.common_vars import LUMI

# ---------------------------------------------------------------------------
# Process groups
# ---------------------------------------------------------------------------
# Each process is a list of (base_name, flavor_suffix) pairs that are summed
# from the ROOT file.  Flavor suffixes come from the make_hists.py splitting
# of samples_qq (["Wjets", "Zjets"]) into bb / c / light.
PROCESS_GROUPS = {
    "zmm": {
        "components": [("Zjets", "")],
        "is_signal": True,
    },
    "wjets": {
        "components": [("Wjets", "")],
        "is_signal": False,
    },
    "ttbar": {
        "components": [("ttbar", "")],
        "is_signal": False,
    },
    "other": {
        # VV and singlet are small but included for completeness
        "components": [("VV", ""), ("singlet", "")],
        "is_signal": False,
    },
}

# Luminosity uncertainty per era (same values as make_datacards.py)
LUMI_ERR = {"2022": 1.01, "2023": 1.02, "2024": 1.02}


# ---------------------------------------------------------------------------
# Histogram helpers
# ---------------------------------------------------------------------------

def read_hist(rootfile, name: str):
    """
    Read a histogram from an uproot file.
    Returns (sumw, sumw2) arrays, or (None, None) if not found.
    Negative bins are clipped to zero.
    """
    if name not in rootfile:
        return None, None
    h = rootfile[name]
    sumw = h.values().copy()
    sumw2 = h.variances().copy() if h.variances() is not None else h.errors() ** 2
    # Clip negatives
    bad = sumw < 0
    sumw[bad] = 0.0
    sumw2[bad] = 0.0
    return sumw, sumw2


def get_merged(rootfile, components, cat: str, region: str, ptbin: int, syst: str = "nominal"):
    """
    Sum histograms for a list of (base_name, flavor_suffix) components.

    Histogram naming convention (from make_hists.py export_to_root):
        {cat}_{region}_pt{ptbin}_{base}{flavor}_{syst}

    e.g. zmmcr_inclusive_pt1_Zjets_bb_nominal
    """
    merged_w = None
    merged_w2 = None
    found_any = False

    for base, flavor in components:
        proc = base + flavor if flavor else base
        name = f"{cat}_{region}_pt{ptbin}_{proc}_{syst}"
        w, w2 = read_hist(rootfile, name)
        if w is None:
            continue
        found_any = True
        if merged_w is None:
            merged_w = np.zeros_like(w)
            merged_w2 = np.zeros_like(w2)
        merged_w += w
        merged_w2 += w2

    if not found_any:
        return None, None
    return merged_w, merged_w2


# ---------------------------------------------------------------------------
# Main datacard builder
# ---------------------------------------------------------------------------

def build_datacard(args):
    year = args.year
    tag = args.tag

    # Load setup
    with open(args.setup) as f:
        config = json.load(f)

    obs_cfg = config["observable"]
    cat_name = list(config["categories"].keys())[0]   # "zmmcr"
    cat_info = config["categories"][cat_name]
    ptbins = np.array(cat_info["bins"])                # [300, 1200]

    # Observable: mll
    mll_bins = np.linspace(obs_cfg["min"], obs_cfg["max"], obs_cfg["nbins"] + 1)
    mll = rl.Observable(obs_cfg["name"], mll_bins)     # "mll", 60–120 GeV, 30 bins

    # Input ROOT file
    root_filename = f"fitting_{year}_{cat_name}_{obs_cfg['name']}.root"
    infile_path = Path(args.indir) / root_filename
    if not infile_path.exists():
        raise FileNotFoundError(
            f"ROOT file not found: {infile_path}\n"
            f"Run: python make_hists.py --region zmmcr --year {year} --tag {tag} ..."
        )

    # Output directory
    outdir = Path(args.outdir) / tag / year / "datacards" / f"zmmcrModel_{year}"
    outdir.mkdir(parents=True, exist_ok=True)

    # Luminosity nuisance (uncorrelated across eras, same as SR/ZGamma CR)
    sys_lumi = rl.NuisanceParameter(f"CMS_lumi_{year}", "lnN")
    lumi_effect = LUMI_ERR[year[:4]] ** (LUMI[year[:4]] / LUMI["2022-2024"])

    model = rl.Model(f"zmmcrModel_{year}")

    with uproot.open(infile_path) as f:
        # List available keys for debugging
        available = [k.split(";")[0] for k in f.keys()]
        print(f"\n[INFO] Opened {infile_path}")
        print(f"[INFO] Found {len(available)} histograms")

        for ptbin in range(len(ptbins) - 1):
            binindex = ptbin + 1       # ROOT file uses 1-indexed pt bins
            region = "inclusive"       # zmumu CR has no pass/fail split

            ch_name = f"ptbin{ptbin}{cat_name}{region}{year}"
            ch = rl.Channel(ch_name)
            model.addChannel(ch)

            print(f"\n  Channel: {ch_name}")

            for proc_name, info in PROCESS_GROUPS.items():
                sumw, sumw2 = get_merged(f, info["components"], cat_name, region, binindex)

                if sumw is None:
                    print(f"    [SKIP] {proc_name} — no histograms found")
                    continue
                if sumw.sum() < 1e-6:
                    print(f"    [SKIP] {proc_name} — zero yield")
                    continue

                stype = rl.Sample.SIGNAL if info["is_signal"] else rl.Sample.BACKGROUND
                templ = (sumw, mll_bins, mll.name, sumw2)
                sample = rl.TemplateSample(f"{ch_name}_{proc_name}", stype, templ)

                # Luminosity uncertainty
                sample.setParamEffect(sys_lumi, lumi_effect)

                # MC statistical uncertainties (Barlow-Beeston lite)
                sample.autoMCStats(lnN=True)

                ch.addSample(sample)
                print(f"    [OK]   {proc_name:8s}  yield = {sumw.sum():.1f}")

            # Data observation
            data_key = config.get("data_obs_name", "Muondata")
            data_name = f"{cat_name}_{region}_pt{binindex}_{data_key}_nominal"
            data_w, _ = read_hist(f, data_name)
            if data_w is None:
                raise RuntimeError(
                    f"data_obs histogram not found: {data_name}\n"
                    f"Available keys (first 10): {available[:10]}"
                )
            ch.setObservation((data_w, mll_bins, mll.name))
            print(f"    [OK]   data_obs   yield = {data_w.sum():.0f}")

    model.renderCombine(str(outdir))

    # Append z_norm rateParam to tie zmm normalization to the Z+γ SR via a
    # shared floating parameter constrained by this CR.
    for card_path in outdir.glob("ptbin*zmmcr*.txt"):
        with open(card_path, "a") as card:
            card.write("\nz_norm  rateParam  *  zmm  1  [0,5]\n")
        print(f"  Added z_norm rateParam to {card_path.name}")

    print(f"\n✓ Datacard written to {outdir}")
    print(f"  To build workspace:")
    print(f"    cd {outdir} && bash build.sh")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Build Z→μμ control region datacard.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--year",   required=True,
                        help="Era, e.g. 2022, 2022EE, 2023, 2023BPix, 2024")
    parser.add_argument("--tag",    required=True,
                        help="Production tag matching the histogram tag, e.g. 26May18")
    parser.add_argument("--setup",  default="setup_zmmcr.json",
                        help="Path to Z→μμ CR setup JSON (default: setup_zmmcr.json)")
    parser.add_argument("--indir",  default=None,
                        help="Directory containing input ROOT files (default: results/<tag>)")
    parser.add_argument("--outdir", default="results/zmmcr",
                        help="Output directory for datacards (default: results/zmmcr)")
    args = parser.parse_args()

    if args.indir is None:
        args.indir = f"results/{args.tag}"

    print(f"\nZ→μμ CR Datacard Builder")
    print(f"  year:   {args.year}")
    print(f"  tag:    {args.tag}")
    print(f"  indir:  {args.indir}")
    print(f"  outdir: {args.outdir}")

    build_datacard(args)


if __name__ == "__main__":
    main()
