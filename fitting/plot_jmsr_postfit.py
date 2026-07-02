"""
plot_jmsr_postfit.py
--------------------
Read fitDiagnosticsTest.root and the initial templates ROOT file, extract the
fitted JMS/JMR nuisance parameter values, apply the corresponding affine morph
to the prefit templates, and overlay prefit / postfit / morphed shapes.

The morphing reproduces what Combine did internally:
    shift = theta_jms * jmsr_scale      (JMS: shifts mass axis)
    scale = 1 + theta_jmr * jmsr_smear  (JMR: widens/narrows distribution)

Usage, e.g.
-----
    python plot_jmsr_postfit.py \\
        --fitfile  results/26Apr27/2022EE/datacards/zgcrModel_2022EE/fitDiagnosticsTest.root \\
        --wsfile   results/26Apr27/2022EE/datacards/zgcrModel_2022EE/zgcrModel_2022EE.root \\
        --wsname   zgcrModel_2022EE \\
        --year     2022EE \\
        -j setup_zgcr.json \\
        --outdir   plots/jmsr_postfit
"""

from __future__ import annotations

import argparse
import contextlib
import json
from pathlib import Path

import matplotlib.pyplot as plt
import mplhep as hep
import numpy as np
import ROOT
import uproot
from scalesmear import MorphHistW2

ROOT.gROOT.SetBatch(True)
plt.style.use(hep.style.CMS)

COL_PREFIT = "blue"
COL_POSTFIT = "red"
COL_MORPHED = "black"
COL_BAND = "0.75"  # grey

# ---------------------------------------------------------------------------
# Reading helpers
# ---------------------------------------------------------------------------


def read_nuisance(fit_result, name: str) -> tuple[float, float]:
    """Return (value, error) for a named floating parameter in a RooFitResult."""
    par = fit_result.floatParsFinal().find(name)
    if par is None:
        raise KeyError(f"Parameter {name!r} not found in fit result.")
    return par.getVal(), par.getError()


def datahist_to_arrays(dh) -> tuple[np.ndarray, np.ndarray]:
    """Convert a RooDataHist to (values, edges)."""
    obs_var = next(iter(dh.get()))
    h = dh.createHistogram(dh.GetName() + "__tmp", obs_var)
    n = h.GetNbinsX()
    edges = np.array([h.GetBinLowEdge(i) for i in range(1, n + 2)])
    values = np.array([h.GetBinContent(i) for i in range(1, n + 1)])
    return values, edges


def read_workspace_templates(
    ws_path: str,
    ws_name: str,
) -> dict[str, dict[str, tuple[np.ndarray, np.ndarray]]]:
    """Read all nominal RooDataHist templates from the workspace.

    Returns
    -------
    dict  channel -> process -> (values, edges)
    """
    root_file = ROOT.TFile.Open(ws_path)
    ws = root_file.Get(ws_name)

    templates: dict = {}
    for dh in ws.allData():
        name = dh.GetName()
        # Skip variation and observation entries — keep only nominals.
        if any(tag in name for tag in ("Up", "Down", "observation")):
            continue
        # Name pattern: {channel}_{process}
        channel, _, process = name.rpartition("_")
        templates.setdefault(channel, {})[process] = datahist_to_arrays(dh)

    root_file.Close()
    return templates


def convTH1(h) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Convert an uproot TH1 to (values, edges, variances), density-corrected."""
    vals = h.values()
    edges = h.axes[0].edges()
    variances = h.variances()
    widths = np.diff(edges)
    return vals * widths, edges, variances * widths


# ---------------------------------------------------------------------------
# Morphing
# ---------------------------------------------------------------------------


def apply_morph(
    nominal: tuple[np.ndarray, np.ndarray],
    theta_jms: float,
    theta_jmr: float,
    jmsr_scale: float,
    jmsr_smear: float,
) -> tuple[np.ndarray, np.ndarray]:
    """Apply the fitted JMS+JMR morph to a nominal (values, edges) template.

    The combined transformation maps:
        mass_axis -> (mass_axis - shift) / scale
    where
        shift = theta_jms * jmsr_scale
        scale = 1 + theta_jmr * jmsr_smear
    """
    sumw, edges = nominal
    # MorphHistW2 needs a sumw2 — use sumw as a placeholder (shape only matters here)
    morph = MorphHistW2((sumw, edges, sumw.copy()))

    shift = theta_jms * jmsr_scale
    scale = 1.0 + theta_jmr * jmsr_smear

    morphed_sumw, morphed_edges, _ = morph.get(shift=shift, scale=scale)
    return morphed_sumw, morphed_edges


def read_signal_strengths(fit_result) -> dict[str, float]:
    """Return {par_name: value} for all 'r_*' parameters in the fit."""
    pars = fit_result.floatParsFinal()
    return {p.GetName(): p.getVal() for p in pars if p.GetName().startswith("r_")}


# ---------------------------------------------------------------------------
# Plotting
# ---------------------------------------------------------------------------


def plot_channel_process(
    channel: str,
    process: str,
    prefit_templ: tuple,
    postfit_templ: tuple | None,
    morphed_templ: tuple,
    morphed_up: tuple,
    morphed_dn: tuple,
    theta_jms: float,
    theta_jmr: float,
    outdir: Path,
) -> None:
    fig, (ax, rax) = plt.subplots(
        2,
        1,
        figsize=(8, 7),
        gridspec_kw={"height_ratios": [3, 1], "hspace": 0},
        sharex=True,
    )

    prefit_vals, edges = prefit_templ[0], prefit_templ[1]
    morphed_vals, _ = morphed_templ
    up_vals, _ = morphed_up
    dn_vals, _ = morphed_dn

    # --- upper panel ---
    hep.histplot(
        (prefit_vals, edges),
        ax=ax,
        color=COL_PREFIT,
        ls="--",
        linewidth=1.5,
        label="Prefit (nominal)",
    )
    hep.histplot(
        (morphed_vals, edges),
        ax=ax,
        color=COL_MORPHED,
        ls="-",
        linewidth=2,
        label=(f"Morphed (JMS $\\theta$={theta_jms:.2f}, " f"JMR $\\theta$={theta_jmr:.2f})"),
    )
    # 1-sigma band from ±1sigma on each nuisance independently
    band_lo = np.minimum(up_vals, dn_vals)
    band_hi = np.maximum(up_vals, dn_vals)
    ax.fill_between(
        edges[:-1] + np.diff(edges) / 2,
        band_lo,
        band_hi,
        step="mid",
        alpha=0.25,
        color=COL_MORPHED,
        label=r"Morph ±1$\sigma$ band",
    )
    if postfit_templ is not None:
        postfit_vals, _ = postfit_templ[0], postfit_templ[1]
        hep.histplot(
            (postfit_vals, edges),
            ax=ax,
            color=COL_POSTFIT,
            ls=":",
            linewidth=1.5,
            label="Postfit (Combine)",
        )

    ax.set_ylabel("Events / bin")
    ax.set_ylim(bottom=0)
    ax.legend(fontsize=9, loc="upper right")
    ax.set_title(f"{channel}  |  {process}", fontsize=10)

    # --- ratio panel (morphed / prefit) ---
    with np.errstate(divide="ignore", invalid="ignore"):
        ratio = np.where(prefit_vals > 0, morphed_vals / prefit_vals, 1.0)
        ratio_up = np.where(prefit_vals > 0, up_vals / prefit_vals, 1.0)
        ratio_dn = np.where(prefit_vals > 0, dn_vals / prefit_vals, 1.0)

    hep.histplot((ratio, edges), ax=rax, color=COL_MORPHED, ls="-", linewidth=2)
    rax.fill_between(
        edges[:-1] + np.diff(edges) / 2,
        np.minimum(ratio_up, ratio_dn),
        np.maximum(ratio_up, ratio_dn),
        step="mid",
        alpha=0.25,
        color=COL_MORPHED,
    )
    rax.axhline(1.0, color="black", ls=":", linewidth=1)
    rax.set_ylabel("Morphed / Prefit")
    rax.set_xlabel("Jet mass (GeV)")
    rax.set_ylim(0.5, 1.5)
    rax.grid(axis="y", linestyle=":", alpha=0.5)

    fname = outdir / f"{channel}_{process}_postfit_morph.png"
    fig.savefig(fname, bbox_inches="tight", dpi=150)
    plt.close(fig)
    print(f"  Saved: {fname}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Plot postfit JMS/JMR morphed templates from fitDiagnostics."
    )
    parser.add_argument("--fitfile", "-f", required=True, help="Path to fitDiagnosticsTest.root.")
    parser.add_argument(
        "--wsfile",
        "-w",
        required=True,
        help="Path to the Combine RooWorkspace ROOT file e.g. zgcrModel_2022EE.root",
    )
    parser.add_argument(
        "--wsname", default=None, help="RooWorkspace name (default: inferred from filename)."
    )
    parser.add_argument("--year", required=True)
    parser.add_argument(
        "--config",
        "-j",
        required=True,
        help="Path to analysis JSON config (e.g. setup_zgcr.json). ",
    )
    parser.add_argument("--outdir", "-o", default="plots/jmsr_postfit")
    parser.add_argument(
        "--channel", "-c", default=None, help="Filter: only plot channels containing this string."
    )
    parser.add_argument(
        "--process", "-p", default=None, help="Filter: only plot processes containing this string."
    )
    args = parser.parse_args()

    with Path(args.config).open() as f:
        config = json.load(f)

    jmsr_processes = config.get("jmsr_processes", [])
    JMSR_SCALE = config.get("jmsr_scale", 1.0)
    JMSR_SMEAR = config.get("jmsr_smear", 0.1)

    sample_dict = config["process_groups"]
    signal_processes = {name for name, info in sample_dict.items() if info.get("is_signal", False)}

    # Resolve which processes are affected by JMSR.
    # --process overrides the config if both are given.
    if args.process is not None:
        jmsr_processes = [args.process]
        print(f"JMSR processes (from --process): {jmsr_processes}")

    ws_name = args.wsname or Path(args.wsfile).stem
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    # --- 1. Read fitted nuisance values ---
    fit_file = ROOT.TFile.Open(args.fitfile)
    fit_result = fit_file.Get("fit_s")

    jms_name = f"CMS_jms_{args.year}"
    jmr_name = f"CMS_jmr_{args.year}"
    theta_jms, jms_err = read_nuisance(fit_result, jms_name)
    theta_jmr, jmr_err = read_nuisance(fit_result, jmr_name)
    print("\nFitted nuisances:")
    print(f"  {jms_name}: {theta_jms:.4f} +/- {jms_err:.4f}")
    print(f"  {jmr_name}: {theta_jmr:.4f} +/- {jmr_err:.4f}")

    # Physical shifts corresponding to the fit values
    fitted_shift = theta_jms * JMSR_SCALE
    fitted_scale = 1.0 + theta_jmr * JMSR_SMEAR
    print("\nPhysical morph:")
    print(f"  JMS shift = {theta_jms:.4f} x {JMSR_SCALE} GeV = {fitted_shift:.4f} GeV")
    print(f"  JMR scale = 1 + {theta_jmr:.4f} x {JMSR_SMEAR} = {fitted_scale:.4f}")

    # Signal strengths
    signal_strengths = read_signal_strengths(fit_result)

    # Map channel to signal strength
    # r_bb applies to passbb channels, r_cc to passcc
    def get_signal_strength(channel: str) -> float:
        for r_name, r_val in signal_strengths.items():
            region = r_name.replace("r_", "")  # "bb", "cc"
            if region in channel:
                return r_val
        return 1.0

    # --- 2. Read prefit templates from workspace ---
    print(f"\nReading templates from: {args.wsfile}")
    templates = read_workspace_templates(args.wsfile, ws_name)

    # --- 3. Read postfit shapes from fitDiagnostics (for overlay) ---
    fd = uproot.open(args.fitfile)
    postfit_shapes = {}
    for raw_key in fd["shapes_fit_s"]:
        key = raw_key.replace(";1", "")
        if "/" not in key:
            continue
        region, proc = key.split("/", 1)
        with contextlib.suppress(Exception):
            postfit_shapes.setdefault(region, {})[proc] = convTH1(fd[f"shapes_fit_s/{key}"])

    fit_file.Close()

    # --- 4. Apply morph and plot ---
    n_plots = 0
    for channel, processes in sorted(templates.items()):
        if args.channel and args.channel not in channel:
            continue
        for process, (sumw, edges) in sorted(processes.items()):
            # Only plot processes that are listed as JMSR-affected in the config.
            if not any(p in process for p in jmsr_processes):
                continue

            if args.process and args.process not in process:
                continue
            if sumw.sum() == 0:
                continue

            # multiply process by signal strength
            is_signal = process in signal_processes
            r_val = get_signal_strength(channel) if is_signal else 1.0
            print(f"Multiplying {process} by {r_val}")
            nominal = (sumw * r_val, edges)

            morphed = apply_morph(nominal, theta_jms, theta_jmr, JMSR_SCALE, JMSR_SMEAR)
            morph_up = apply_morph(
                nominal, theta_jms + jms_err, theta_jmr + jmr_err, JMSR_SCALE, JMSR_SMEAR
            )
            morph_dn = apply_morph(
                nominal, theta_jms - jms_err, theta_jmr - jmr_err, JMSR_SCALE, JMSR_SMEAR
            )

            postfit = postfit_shapes.get(channel, {}).get(process)

            plot_channel_process(
                channel=channel,
                process=process,
                prefit_templ=nominal,
                postfit_templ=postfit,
                morphed_templ=morphed,
                morphed_up=morph_up,
                morphed_dn=morph_dn,
                theta_jms=theta_jms,
                theta_jmr=theta_jmr,
                outdir=outdir,
            )
            n_plots += 1

    print(f"\nDone — {n_plots} plot(s) written to {outdir}/")


if __name__ == "__main__":
    main()
