
from pathlib import Path

import hist
import matplotlib.pyplot as plt
import mplhep as hep
import numpy as np
import pandas as pd

from hist.intervals import ratio_uncertainty

from hbb.common_vars import LUMI

def dphi(phi1: pd.Series, phi2: pd.Series) -> pd.Series:
    """Compute |Δφ| wrapped to [0, π]."""
    raw = np.abs(phi1.values - phi2.values)
    return pd.Series(np.where(raw > np.pi, 2 * np.pi - raw, raw), index=phi1.index)


def get_values(df: pd.DataFrame, var: str) -> pd.Series:
    if var == "dphi_photon_muon":
        return dphi(df["Photon0_phi"], df["Zmm_MuonLead_phi"])
    return df[var]


def make_stack_plot(
    all_events: dict[str, pd.DataFrame],
    selection_mask: dict[str, pd.Series],
    var: str,
    bins: np.ndarray,
    region_label: str,
    xlabel: str,
    year: str,
    outpath: Path,
    stack_order: list[str],
    proc_style: dict[str, dict],
    ylog: bool = False
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

    if ylog:
        ax.set_yscale('log') 

    # ------------------------------------------------------------------
    # Build hist.Hist objects for each MC process.
    # hist.Hist automatically accumulates sum(w²) in .variances() when
    # events are filled with weights — this is the correct MC stat unc.
    # ------------------------------------------------------------------
    h_mc: dict[str, hist.Hist] = {}
    for proc in stack_order:
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
        # print(
        #     proc,
        #     "df =", df["finalWeight"].sum(),
        #     "hist =", np.sum(h.values())
        # )

    if not h_mc:
        plt.close(fig)
        return

    mc_ordered = [p for p in stack_order if p in h_mc]
    tot_mc = sum(h_mc[p] for p in mc_ordered)
    bin_edges = tot_mc.axes[0].edges

    # Stack fill
    hep.histplot(
        [h_mc[p] for p in mc_ordered],
        stack=True,
        histtype="fill",
        label=[proc_style[p]["label"] for p in mc_ordered],
        color=[proc_style[p]["color"] for p in mc_ordered],
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
        0.05, 0.95, region_label,
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

def describe_df_weight(proc, df):
    print(proc, len(df))
    print(df.index.nunique())

    print(df["finalWeight"].describe())
    print(df.nlargest(10, "finalWeight")[["finalWeight", "weight"]])

    print("negative fraction:",  np.mean(df["finalWeight"] < 0))

    print(np.sum(df["weight"]), np.sum(df["finalWeight"]))

    print(np.mean(df["weight"] < 0),np.mean(df["finalWeight"] < 0))
    