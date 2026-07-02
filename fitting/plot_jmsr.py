"""
plot_jmsr.py
------------
Read a Combine RooWorkspace and plot nominal, JMS (scaleUp/Down) and
JMR (smearUp/Down) shapes for every channel and process that has them.

Usage
-----
    python plot_jmsr.py \\
        --file results/.../zgcrModel_2022EE.root \\
        --wsname zgcrModel_2022EE \\
        --outdir plots/jmsr

    # Restrict to one channel or process
    python plot_jmsr.py --file ... --channel passbb --process zgammabb
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from pathlib import Path

import matplotlib.pyplot as plt
import mplhep as hep
import numpy as np
import ROOT
from card_utils import safe_ratio

ROOT.gROOT.SetBatch(True)
plt.style.use(hep.style.CMS)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Maps a systematic label to the (up, down) suffix as written in the workspace.
# The {year} placeholder is filled at runtime.
VARIATION_PAIRS: dict[str, tuple[str, str]] = {
    "JMS": ("CMS_jms_{year}Up", "CMS_jms_{year}Down"),
    "JMR": ("CMS_jmr_{year}Up", "CMS_jmr_{year}Down"),
}

COL_NOM = "black"
COL_UP = "blue"
COL_DN = "violet"

SKIP_KEYS = {"observation"}


# ---------------------------------------------------------------------------
# Workspace reading
# ---------------------------------------------------------------------------


def _datahist_to_arrays(dh) -> tuple[np.ndarray, np.ndarray]:
    """Convert a RooDataHist to (values, edges) using its first observable."""
    obs_var = next(iter(dh.get()))
    h = dh.createHistogram(dh.GetName() + "__tmp", obs_var)
    n = h.GetNbinsX()
    edges = np.array([h.GetBinLowEdge(i) for i in range(1, n + 2)])
    values = np.array([h.GetBinContent(i) for i in range(1, n + 1)])
    return values, edges


def _parse_name(name: str, all_suffixes: set[str]) -> tuple[str, str, str]:
    """Split a RooDataHist name into (channel, process, variation).

    Names follow the pattern:
        {channel}_{process}[_{variation}]

    Tries longest suffixes first to avoid partial matches.
    """
    for suffix in sorted(all_suffixes, key=len, reverse=True):
        if name.endswith(f"_{suffix}"):
            rest = name[: -len(f"_{suffix}")]
            channel, _, process = rest.rpartition("_")
            return channel, process, suffix

    # No variation suffix — nominal.
    channel, _, process = name.rpartition("_")
    return channel, process, ""


def collect_templates(
    ws_path: str,
    ws_name: str,
    year: str,
    channel_filter: str | None,
    process_filter: str | None,
) -> dict[str, dict[str, dict[str, tuple]]]:
    """Read all RooDataHist objects from the workspace.

    Returns
    -------
    dict  channel -> process -> {nominal | <variation>} -> (values, edges)
    """
    all_suffixes = {
        suf.format(year=year) for _, (up, dn) in VARIATION_PAIRS.items() for suf in (up, dn)
    }

    root_file = ROOT.TFile.Open(ws_path)
    ws = root_file.Get(ws_name)

    templates: dict = defaultdict(lambda: defaultdict(dict))

    for dh in ws.allData():
        name = dh.GetName()

        if any(skip in name for skip in SKIP_KEYS):
            continue

        channel, process, variation = _parse_name(name, all_suffixes)
        label = variation if variation else "nominal"

        if channel_filter and channel_filter not in channel:
            continue
        if process_filter and process_filter not in process:
            continue

        try:
            templates[channel][process][label] = _datahist_to_arrays(dh)
        except Exception as exc:
            print(f"  Warning: could not read {name!r}: {exc}")

    root_file.Close()
    return templates


# ---------------------------------------------------------------------------
# Plotting
# ---------------------------------------------------------------------------
def plot_variation(
    channel: str,
    process: str,
    syst_name: str,
    up_suffix: str,
    dn_suffix: str,
    hists: dict[str, tuple],
    outdir: Path,
) -> None:
    if "nominal" not in hists:
        return
    if up_suffix not in hists or dn_suffix not in hists:
        return

    nom_vals, edges = hists["nominal"]
    up_vals, _ = hists[up_suffix]
    dn_vals, _ = hists[dn_suffix]

    fig, (ax, rax) = plt.subplots(
        2,
        1,
        figsize=(8, 7),
        gridspec_kw={"height_ratios": [3, 1], "hspace": 0},
        sharex=True,
    )

    hep.histplot((nom_vals, edges), ax=ax, color=COL_NOM, ls="-", linewidth=2, label="Nominal")
    hep.histplot(
        (up_vals, edges), ax=ax, color=COL_UP, ls="--", linewidth=1.5, label=f"{syst_name} up"
    )
    hep.histplot(
        (dn_vals, edges), ax=ax, color=COL_DN, ls="--", linewidth=1.5, label=f"{syst_name} down"
    )
    ax.set_ylabel("Events / bin")
    ax.set_ylim(bottom=0)
    ax.legend(fontsize=11)
    ax.set_title(f"{channel}  |  {process}  |  {syst_name}", fontsize=10)

    hep.histplot(
        (safe_ratio(up_vals, nom_vals), edges), ax=rax, color=COL_UP, ls="--", linewidth=1.5
    )
    hep.histplot(
        (safe_ratio(dn_vals, nom_vals), edges), ax=rax, color=COL_DN, ls="--", linewidth=1.5
    )
    rax.axhline(1.0, color=COL_NOM, ls=":", linewidth=1)
    rax.set_ylabel("Var / Nom")
    rax.set_xlabel("Jet mass (GeV)")
    rax.set_ylim(0.5, 1.5)
    rax.grid(axis="y", linestyle=":", alpha=0.5)

    fname = outdir / f"{channel}_{process}_{syst_name}.png"
    fig.savefig(fname, bbox_inches="tight", dpi=150)
    plt.close(fig)
    print(f"  Saved: {fname}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Plot JMS/JMR shape variations from a Combine RooWorkspace."
    )
    parser.add_argument(
        "--file",
        "-f",
        default="results/26Apr27/2022EE/datacards/zgcrModel_2022EE/zgcrModel_2022EE.root",
    )
    parser.add_argument(
        "--wsname",
        "-w",
        default=None,
        help="RooWorkspace name inside the file (default: inferred from filename).",
    )
    parser.add_argument("--year", default="2022EE")
    parser.add_argument("--outdir", "-o", default="plots/jmsr")
    parser.add_argument("--channel", "-c", default=None)
    parser.add_argument("--process", "-p", default=None)
    args = parser.parse_args()

    ws_name = args.wsname or Path(args.file).stem

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    print(f"Opening: {args.file}  (workspace: {ws_name}, year: {args.year})")
    templates = collect_templates(args.file, ws_name, args.year, args.channel, args.process)

    if not templates:
        print("No matching templates found. Check --channel / --process / --year.")
        return

    n_plots = 0
    for channel, processes in sorted(templates.items()):
        for process, hists in sorted(processes.items()):
            for syst_name, (up_tmpl, dn_tmpl) in VARIATION_PAIRS.items():
                up_suf = up_tmpl.format(year=args.year)
                dn_suf = dn_tmpl.format(year=args.year)
                if up_suf in hists or dn_suf in hists:
                    plot_variation(channel, process, syst_name, up_suf, dn_suf, hists, outdir)
                    n_plots += 1

    print(f"\nDone — {n_plots} plot(s) written to {outdir}/")


if __name__ == "__main__":
    main()
