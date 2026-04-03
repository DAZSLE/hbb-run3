#!/usr/bin/env python3
"""
Plotting script adapted for new make_hists.py output.

Gabi Hamilton - Feb 2026
"""
from __future__ import annotations

import argparse
import json
import pickle
import sys
from pathlib import Path

import hist
import matplotlib.pyplot as plt
import mplhep as hep
import yaml

# Add the ../python directory to the path
sys.path.append(str(Path(__file__).resolve().parent.parent / "python"))

from plotting import ratio_plot

from hbb.common_vars import LUMI

hep.style.use("CMS")

# --- Globals for Plotting Logic ---
# 3: bb, 2: cc, 1: light (based on GenFlavor)
flavor_map = {3: "b-jet", 2: "c-jet", 1: "light-jet"}

mass_lo = 115
mass_hi = 135

categories = [
    "inclusive",
    "pass_bb",
    "pass_cc",
    "fail",
    "pass",
]

category_labels = {
    "inclusive": "Pre-selection",
    "pass_bb": "Xbb+Xcc > 0.95 (bb-like)",
    "pass_cc": "Xbb+Xcc > 0.95 (cc-like)",
    "fail": "Xbb+Xcc < 0.95 (Fail)",
    "pass": "Xbb+Xcc > 0.95 (All Pass)",
}


# --- Function 1: Plotting Stacked by Process ---
def plot_by_process(
    hists, category, year_str, year_list, outdir, region, style, variable, ptinclusive=False
):
    first_hist = next((h for h in hists.values() if h.sum() > 0), None)
    if not first_hist:
        print(f"All histograms are empty for {category} category. Skipping plot.")
        return
    pt_axis = first_hist.axes[1]

    if ptinclusive:
        loop_indices = ["inclusive"]
        print("--- Preparing pT-inclusive plot ---")
    else:
        loop_indices = range(len(pt_axis.edges) - 1)
        print("--- Preparing plots for each pT bin ---")

    for i in loop_indices:
        if i == "inclusive":
            pt_low, pt_high = pt_axis.edges[0], pt_axis.edges[-1]
            idx_selector = slice(None)
        else:
            pt_low, pt_high = pt_axis.edges[i], pt_axis.edges[i + 1]
            idx_selector = i

        print(f"  Processing pt bin: {pt_low} - {pt_high} (Index {i})")

        histograms_to_plot = {}
        total_yield = 0

        for process, h in hists.items():
            if h.sum() == 0 or category not in h.axes["category"]:
                continue

            # Project to 1D
            h_proj = h[:, idx_selector, category, :].project(variable)

            # --- Blinding Data (MSD only) ---
            is_data_process = "data" in process.lower()
            if (
                is_data_process
                and "zgamma" not in region
                and "zgcr" not in region
                and variable == "msd"
            ):
                edges = h_proj.axes[0].edges
                mask = (edges[:-1] >= mass_lo) & (edges[:-1] < mass_hi)
                data_val = h_proj.values()
                data_val[mask] = 0
                h_proj.values()[:] = data_val

            histograms_to_plot[process] = h_proj
            total_yield += h_proj.sum()

        print(f"    Total Yield in this bin: {total_yield:.2f}")

        if ptinclusive:
            legend_title = f"{category.capitalize()} Region, $p_T$-inclusive"
            output_name = (
                f"{outdir}/{year_str}_{region}_{category}_{variable}_process_ptinclusive.png"
            )
        else:
            cat_label = category_labels.get(category, category)
            legend_title = f"{cat_label}\n{pt_low:g} < $p_T$ < {pt_high:g} GeV"
            output_name = f"{outdir}/{year_str}_{region}_{category}_{variable}_process_ptbin{pt_low}_{pt_high}.png"

        # --- UPDATED: Region-specific plotting logic with CamelCase keys ---
        if "zgcr" in region or "zgamma" in region:
            signals = ["Zgamma"]
            bkg_order = ["ttbar", "Wjets", "Zjets", "QCD", "Wgamma"]
            onto = "GJets"
        elif "zmumu" in region or "zmmcr" in region:
            signals = []
            bkg_order = ["QCD", "singlet", "VV", "Wjets", "ttbar", "Zjets"]
            onto = "Zjets"
        elif "control-tt" in region:
            signals = []
            bkg_order = ["Wjets", "Zjets", "QCD", "singlet", "ttbar"]
            onto = "ttbar"
        else:
            signals = ["ggF", "VBF", "WH", "ZH", "ttH"]  # Changed 'VH' to 'WH', 'ZH'
            bkg_order = ["Zjets", "Wjets", "ttbar", "QCD"]
            onto = "QCD"

        # Safe fallback if a process is missing from the order list
        existing_bkgs = [b for b in bkg_order if b in histograms_to_plot]

        # If 'onto' is missing, pick the largest background
        if onto not in histograms_to_plot:
            if existing_bkgs:
                onto = existing_bkgs[-1]
            else:
                print("    No backgrounds found to plot ratio against.")
                continue

        data_key = next((k for k in histograms_to_plot if "data" in k.lower()), None)
        if data_key and data_key != "data":
            histograms_to_plot["data"] = histograms_to_plot.pop(data_key)

        print(f"DEBUG: Yields in {category}:")
        for k, v in histograms_to_plot.items():
            print(f"  - {k}: {v.sum():.2f}")

        fig, (ax, rax) = ratio_plot(
            histograms_to_plot,
            sigs=signals,
            bkgs=existing_bkgs,
            onto=onto,
            style=style,
            sort_by_yield=False,  # Respect our custom order
            legend_title=legend_title,
        )

        luminosity = sum(LUMI[y] / 1000.0 for y in year_list)
        hep.cms.label(
            "Private Work",
            data=True,
            ax=ax,
            lumi=luminosity,
            lumi_format="{:0.1f}",
            com=13.6,
            year=year_str,
            loc=0,
        )
        print(f"  [SAVING] {output_name}")  # Add this line
        fig.savefig(output_name, dpi=300, bbox_inches="tight")
        plt.close(fig)


# --- Function 2: Plotting Stacked by Flavor ---
def plot_by_flavor(hists, category, year_str, year_list, outdir, region, style, variable):
    first_hist = next((h for h in hists.values() if h.sum() > 0), None)
    if not first_hist:
        print(f"All histograms are empty for {category} category. Skipping plot.")
        return
    pt_axis = first_hist.axes[1]

    for i in range(len(pt_axis.edges) - 1):
        pt_low, pt_high = pt_axis.edges[i], pt_axis.edges[i + 1]
        i_start = pt_axis.index(pt_low)
        print(f"  Processing pt bin: {pt_low} - {pt_high}")

        histograms_to_plot = {}
        for process, h in hists.items():
            if h.sum() == 0 or category not in h.axes["category"]:
                continue

            # --- UPDATED: Wjets/Zjets check ---
            if process in ["Wjets", "Zjets"]:
                h_2d = h[:, i_start, category, :]
                for flavor_code, flavor_name in flavor_map.items():
                    new_key = f"{process}_{flavor_name}"
                    histograms_to_plot[new_key] = h_2d[:, hist.loc(flavor_code)].project(variable)
            else:
                h_proj = h[:, i_start, category, :].project(variable)

                if process == "data" and variable == "msd" and region != "control-zgamma":
                    edges = h_proj.axes[0].edges
                    mask = (edges[:-1] >= mass_lo) & (edges[:-1] < mass_hi)
                    data_val = h_proj.values()
                    data_val[mask] = 0
                    h_proj.values()[:] = data_val
                histograms_to_plot[process] = h_proj

        # --- UPDATED: Background Order for Flavors ---
        bkg_order = [
            "ggF",
            "VBF",
            "VH",
            "ttH",
            "QCD",
            "singlet",
            "ttbar",
            "Wjets_light-jet",
            "Wjets_c-jet",
            "Zjets_light-jet",
            "Zjets_c-jet",
            "Zjets_b-jet",
            "Wgamma",
            "Zgamma",
            "GJets",
        ]

        legend_title = f"{category.capitalize()} Region, {pt_low:g} < $p_T$ < {pt_high:g} GeV"

        # Filter order to only include what exists
        existing_bkgs = [b for b in bkg_order if b in histograms_to_plot]

        # Determine ratio denominator
        onto = "QCD"
        if "control-zgamma" in region:
            onto = "GJets"
        elif "zmumu" in region or "zmmcr" in region:
            onto = "Zjets"
        elif "control-tt" in region:
            onto = "ttbar"

        if onto not in histograms_to_plot and existing_bkgs:
            onto = existing_bkgs[-1]

        print(f"DEBUG: Yields in {category}:")
        for k, v in histograms_to_plot.items():
            print(f"  - {k}: {v.sum():.2f}")

        fig, (ax, rax) = ratio_plot(
            histograms_to_plot,
            sigs=[],
            bkgs=existing_bkgs,
            onto=onto,
            style=style,
            sort_by_yield=False,
            legend_title=legend_title,
        )

        luminosity = sum(LUMI[y] / 1000.0 for y in year_list)
        hep.cms.label(
            "Private Work",
            data=True,
            ax=ax,
            lumi=luminosity,
            lumi_format="{:0.1f}",
            com=13.6,
            year=year_str,
            loc=0,
        )

        output_name = (
            f"{outdir}/{year_str}_{region}_{category}_{variable}_flavor_ptbin{pt_low}_{pt_high}.png"
        )
        fig.savefig(output_name, dpi=300, bbox_inches="tight")
        plt.close(fig)


# --- Function 3: QCD Pass/Fail Shape Comparison ---
def plot_qcd_shapes(hists, year_str, outdir, region, norm_type, variable, qcd_proc):
    if qcd_proc not in hists or hists[qcd_proc].sum() == 0:
        print(f"No '{qcd_proc}' histogram with entries found. Exiting.")
        return
    h_qcd = hists[qcd_proc]
    pt_axis = h_qcd.axes[1]

    for i in range(len(pt_axis.edges) - 1):
        pt_low, pt_high = pt_axis.edges[i], pt_axis.edges[i + 1]
        i_start = pt_axis.index(pt_low)
        print(f"Processing pt bin: {pt_low} - {pt_high}")

        h_pass = h_qcd[:, i_start, "pass", :].project(variable)
        h_fail = h_qcd[:, i_start, "fail", :].project(variable)

        if h_pass.sum() == 0 or h_fail.sum() == 0:
            print("  Skipping pt bin due to zero events.")
            continue

        fig, ax = plt.subplots(figsize=(10, 8))

        if norm_type == "shape":
            hep.histplot(h_fail, ax=ax, label="QCD MC fail", color="blue", density=True, yerr=True)
            hep.histplot(h_pass, ax=ax, label="QCD MC pass", color="black", density=True, yerr=True)
            ylabel = "Probability Density"

        elif norm_type == "density":
            bin_width = h_pass.axes[0].widths[0]
            pass_yield = h_pass.sum()
            fail_yield = h_fail.sum()
            h_fail_scaled = h_fail * (pass_yield / fail_yield)

            xlabel_text = h_pass.axes[0].label
            units = (
                xlabel_text[xlabel_text.find("[") + 1 : xlabel_text.find("]")]
                if "[" in xlabel_text
                else ""
            )
            ylabel = f"Events / {bin_width:g} {units}"

            hep.histplot(
                h_fail_scaled / bin_width, ax=ax, label="QCD MC fail", color="blue", yerr=True
            )
            hep.histplot(h_pass / bin_width, ax=ax, label="QCD MC pass", color="black", yerr=True)

        ax.set_xlabel(h_pass.axes[0].label)
        ax.set_ylabel(ylabel)
        ax.grid(True)
        hep.cms.label("Private Work", data=False, ax=ax, com=13.6, year=year_str)
        ax.legend(title=f"{pt_low:g} < $p_T$ < {pt_high:g} GeV", loc="upper right")

        output_name = (
            f"{outdir}/{year_str}_{region}_{variable}_qcd_{norm_type}_ptbin{pt_low}_{pt_high}.png"
        )
        fig.savefig(output_name, dpi=300, bbox_inches="tight")
        plt.close(fig)


# --- Function 4: Inclusive Plots ---
def plot_inclusive(
    hists, year_str, year_list, outdir, region, style, inclusive_scope, stack_by, variable
):
    inclusive_cat = "inclusive"
    print(f"  Creating inclusive plot from '{inclusive_cat}' category.")

    hists_incl = {}
    for process, h in hists.items():
        if h.sum() > 0 and inclusive_cat in h.axes["category"]:
            hists_incl[process] = h[..., hist.loc(inclusive_cat), :]

    if not hists_incl:
        print(f"No histograms with '{inclusive_cat}' category found.")
        return

    first_hist = next(iter(hists_incl.values()))
    pt_axis = first_hist.axes[1]
    plot_configs = []

    if inclusive_scope in ["pt-binned", "all"]:
        for i in range(len(pt_axis.edges) - 1):
            pt_low, pt_high = pt_axis.edges[i], pt_axis.edges[i + 1]
            title_label = category_labels.get("inclusive", "Inclusive")
            h_slice = {
                p: h[:, pt_axis.index(pt_low), :].project(variable) for p, h in hists_incl.items()
            }
            plot_configs.append(
                {
                    "hists": h_slice,
                    "title": f"{title_label}, {pt_low:g} < $p_T$ < {pt_high:g} GeV",
                    "filename": f"{outdir}/{year_str}_{region}_inclusive_{variable}_{stack_by}_ptbin{pt_low}_{pt_high}.png",
                    "pt_slice": i,
                }
            )

    if inclusive_scope in ["pt-inclusive", "all"]:
        title_label = category_labels.get("inclusive", "Inclusive")
        h_slice = {p: h[:, hist.sum, :].project(variable) for p, h in hists_incl.items()}
        plot_configs.append(
            {
                "hists": h_slice,
                "title": f"{title_label} (all $p_T$)",
                "filename": f"{outdir}/{year_str}_{region}_inclusive_{variable}_{stack_by}_allpt.png",
                "pt_slice": hist.sum,
            }
        )

    for config in plot_configs:
        print(f"  Processing: {config['title']}")
        histograms_to_plot = config["hists"]

        if "data" in histograms_to_plot and variable == "msd" and region != "control-zgamma":
            h_proj = histograms_to_plot["data"]
            edges, data_val = h_proj.axes[0].edges, h_proj.values()
            mask = (edges[:-1] >= mass_lo) & (edges[:-1] < mass_hi)
            data_val[mask] = 0
            h_proj.values()[:] = data_val

        if stack_by == "flavor":
            flavored_hists = {}
            for process, h in histograms_to_plot.items():
                if process in ["Wjets", "Zjets"]:
                    h_2d = hists_incl[process][:, config["pt_slice"], :]
                    for code, name in flavor_map.items():
                        flavored_hists[f"{process}_{name}"] = h_2d[:, hist.loc(code)].project(
                            variable
                        )
                else:
                    flavored_hists[process] = h
            histograms_to_plot = flavored_hists

        # --- UPDATED: Region Logic ---
        if "control-zgamma" in region:
            signals = ["Zgamma"]
            bkg_order = ["ttbar", "Wjets", "Zjets", "QCD", "Wgamma", "GJets"]
            onto = "GJets"
        elif "zmumu" in region or "zmmcr" in region:
            signals = []
            bkg_order = ["QCD", "singlet", "VV", "Wjets", "ttbar", "Zjets"]
            onto = "Zjets"
        elif "control-tt" in region:
            signals = []
            bkg_order = ["Wjets", "Zjets", "QCD", "singlet", "ttbar"]
            onto = "ttbar"
        else:
            signals = ["ggF", "VBF", "VH", "ttH"]
            bkg_order = ["Zjets", "Wjets", "ttbar", "QCD"]
            onto = "QCD"

        if stack_by == "flavor":
            # Expand bkg_order for flavors... (Same as plot_by_flavor)
            bkg_order = [
                "ggF",
                "VBF",
                "VH",
                "ttH",
                "QCD",
                "singlet",
                "ttbar",
                "Wjets_light-jet",
                "Wjets_c-jet",
                "Zjets_light-jet",
                "Zjets_c-jet",
                "Zjets_b-jet",
                "Wgamma",
                "Zgamma",
                "GJets",
            ]

        # Safe fallback if a process is missing from the order list
        existing_bkgs = [b for b in bkg_order if b in histograms_to_plot]

        # --- FIX: Rename data stream to "data" for ratio_plot handshake ---
        data_key = next((k for k in histograms_to_plot if "data" in k.lower()), None)
        if data_key and data_key != "data":
            histograms_to_plot["data"] = histograms_to_plot.pop(data_key)

        if onto not in histograms_to_plot:
            if existing_bkgs:
                onto = existing_bkgs[-1]
            else:
                continue

        data_key = next((k for k in histograms_to_plot if "data" in k.lower()), None)
        if data_key and data_key != "data":
            histograms_to_plot["data"] = histograms_to_plot.pop(data_key)
        fig, (ax, rax) = ratio_plot(
            histograms_to_plot,
            sigs=signals,
            bkgs=existing_bkgs,
            onto=onto,
            style=style,
            sort_by_yield=False,
            legend_title=config["title"],
        )

        luminosity = sum(LUMI[y] / 1000.0 for y in year_list)
        hep.cms.label(
            "Private Work",
            data=True,
            ax=ax,
            lumi=luminosity,
            lumi_format="{:0.1f}",
            com=13.6,
            year=year_str,
            loc=0,
        )

        fig.savefig(config["filename"], dpi=300, bbox_inches="tight")
        plt.close(fig)


# --- Main Function ---
def main(args):
    # Initialize dictionaries and strings
    histograms = {}
    year_str = "all-years" if len(args.year) > 1 else args.year[0]

    # Load the same setup file used for make_hists.py
    with Path(args.setup).open() as f:
        setup = json.load(f)

    variable = setup["observable"]["name"]
    print(f"DEBUG: Projecting along axis name: {variable}")
    categories_to_plot = list(setup["categories"].keys())

    for year in args.year:
        for region_key in categories_to_plot:
            pkl_path = Path(args.indir) / f"hists_{year}_{region_key}_{variable}_nominal.pkl"

            if not pkl_path.exists():
                print(f"Error: File not found at {pkl_path}. Skipping.")
                continue

            with pkl_path.open("rb") as f:
                histograms_tmp = pickle.load(f)

                # Just for the terminal printout: identify which data stream is present
                current_data_key = next((k for k in histograms_tmp if "data" in k.lower()), "Data")
                data_yield = histograms_tmp.get(current_data_key, hist.Hist()).sum()
                qcd_yield = histograms_tmp.get("QCD", hist.Hist()).sum()

                print(f"\nLoading {variable} histograms for year {year}...")
                print(f"  Year {year}: Data={data_yield:.2f}, QCD={qcd_yield:.2f}")

                for process, h in histograms_tmp.items():
                    if process in histograms:
                        histograms[process] += h
                    else:
                        histograms[process] = h

    if not histograms:
        print("No histograms were loaded. Exiting.")
        return

    output_dir = Path(args.outdir)
    output_dir.mkdir(parents=True, exist_ok=True)

    style_path = Path("style_hbb.yaml")
    if style_path.exists():
        with style_path.open() as f:
            style = yaml.safe_load(f)
    else:
        print("Warning: style_hbb.yaml not found. Using empty style.")
        style = {}

    if args.plot_type == "process":
        for category in categories:
            print(f"Plotting {args.variable} by process for {category}...")
            plot_by_process(
                histograms,
                category,
                year_str,
                args.year,
                args.outdir,
                args.region,
                style,
                variable,
                ptinclusive=(args.inclusive_scope == "pt-inclusive"),
            )
    elif args.plot_type == "flavor":
        for category in categories:
            print(f"Plotting {args.variable} by flavor for {category}...")
            plot_by_flavor(
                histograms,
                category,
                year_str,
                args.year,
                args.outdir,
                args.region,
                style,
                variable,
            )
    elif args.plot_type == "qcd_shape":
        qcd_proc = setup.get("qcd_proc", "QCD")
        plot_qcd_shapes(
            histograms, year_str, args.outdir, args.region, args.norm_type, args.variable, qcd_proc
        )
    elif args.plot_type == "inclusive":
        plot_inclusive(
            histograms,
            year_str,
            args.year,
            args.outdir,
            args.region,
            style,
            args.inclusive_scope,
            args.stack_by,
            args.variable,
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Unified plotting script for Hbb analysis.")
    parser.add_argument(
        "--year",
        help="List of years",
        type=str,
        required=True,
        nargs="+",
        choices=["2022", "2022EE", "2023", "2023BPix", "2024"],
    )
    parser.add_argument("--indir", help="Input directory for .pkl files", type=str, required=True)
    parser.add_argument("--outdir", help="Output directory for plots", type=str, required=True)
    parser.add_argument("--region", help="Analysis region", type=str, required=True)
    parser.add_argument("--variable", help="Variable to plot", type=str, default="msd")
    parser.add_argument("--setup", help="Path to the setup.json file", type=str, required=True)
    parser.add_argument(
        "--stack-by",
        help="For inclusive plots",
        type=str,
        default="process",
        choices=["process", "flavor"],
    )
    parser.add_argument(
        "--plot_type",
        help="Type of plot",
        type=str,
        default="process",
        choices=["process", "flavor", "qcd_shape", "inclusive", "reference"],
    )
    parser.add_argument(
        "--norm_type",
        help="QCD shape norm",
        type=str,
        default="shape",
        choices=["shape", "density"],
    )
    parser.add_argument(
        "--inclusive_scope",
        help="Scope",
        type=str,
        default="pt-binned",
        choices=["pt-binned", "pt-inclusive"],
    )
    args = parser.parse_args()
    main(args)
