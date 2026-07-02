#!/usr/bin/env python3
"""
summarize_jmsr.py — Tabulate JMS/JMR nuisance fit results.

Reads a CombineTool impacts JSON (preferred — has values + errors + POIs)
or a fitDiagnostics ROOT file (central values only, no errors).

Writes:
  - Pretty table to stdout
  - Markdown table  →  <output>.md
  - CSV             →  <output>.csv

Usage:
    # From impacts JSON (recommended — run after combineTool -M Impacts):
    python summarize_jmsr.py \\
        --impacts impacts_newdisc_jmsr.json \\
        --setup   setup_zgcr.json \\
        --tag     newdisc_jmsr \\
        --output  jmsr_results_newdisc_jmsr.md

    # From fitDiagnostics only (central values, no uncertainties):
    python summarize_jmsr.py \\
        --fitfile fitDiagnostics_Run3_newdisc_jmsr.root \\
        --setup   setup_zgcr.json \\
        --tag     newdisc_jmsr
"""

from __future__ import annotations

import argparse
import csv
import json
from datetime import date
from pathlib import Path

YEARS = ["2022", "2022EE", "2023", "2023BPix", "2024"]

# A nuisance is considered "at boundary" when its central value is within
# BOUNDARY_TOL of ±1 AND one of its errors is < BOUNDARY_TOL (i.e., it
# can't move further in that direction).
BOUNDARY_TOL = 0.05


# ---------------------------------------------------------------------------
# Classification helpers
# ---------------------------------------------------------------------------

def classify(central: float, err_lo: float, err_hi: float, boundary: float = 1.0) -> str:
    """Return a human-readable status for a nuisance parameter."""
    at_bnd = (
        abs(abs(central) - boundary) < BOUNDARY_TOL
        and (err_lo < BOUNDARY_TOL or err_hi < BOUNDARY_TOL)
    )
    if at_bnd:
        return "at boundary"
    avg = 0.5 * (err_lo + err_hi)
    if avg < 0.3:
        return "well constrained"
    if avg < 0.7:
        return "constrained"
    return "loosely constrained"


def classify_emoji(status: str) -> str:
    if "boundary" in status:
        return f"⚠  {status}"
    if "well" in status:
        return f"✓  {status}"
    if "constrained" in status:
        return f"✓  {status}"
    return f"~  {status}"


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_impacts(path: str) -> tuple[dict, dict]:
    """Load param_map and poi_map from a combineTool impacts JSON.

    impacts JSON format (from: combineTool.py -M Impacts ... -o out.json):
        {
          "POIs":   [{"name": "r_bb", "fit": [central, lo_val, hi_val]}, ...],
          "params": [{"name": "CMS_jms_2024", "fit": [central, lo_val, hi_val]}, ...]
        }
    where lo_val / hi_val are the PARAMETER VALUES at the −1σ / +1σ points,
    so: err_lo = central − lo_val,  err_hi = hi_val − central.
    """
    with open(path) as f:
        data = json.load(f)
    param_map = {p["name"]: p for p in data.get("params", [])}
    poi_map   = {p["name"]: p for p in data.get("POIs",   [])}
    return param_map, poi_map


def load_fitdiag(path: str) -> tuple[dict, dict]:
    """Load central values only from a fitDiagnostics ROOT TTree (no errors)."""
    try:
        import uproot
    except ImportError:
        raise SystemExit("uproot is required to read ROOT files.  "
                         "Install it or use --impacts instead.")
    with uproot.open(path) as f:
        tree = f["tree_fit_sb"]
        arr  = tree.arrays(library="np")
    param_map = {
        name: {"fit": [float(arr[name][0])] * 3}   # no errors → fill lo=central=hi
        for name in tree.keys()
    }
    return param_map, {}


# ---------------------------------------------------------------------------
# Row extraction
# ---------------------------------------------------------------------------

def extract(param_map: dict, poi_map: dict,
            jmsr_scale: float, jmsr_smear: float) -> tuple[list, dict]:
    """Build per-year rows and a POI summary dict."""

    rows = []
    for year in YEARS:
        row: dict = {"year": year}

        for kind, key in [("JMS", f"CMS_jms_{year}"), ("JMR", f"CMS_jmr_{year}")]:
            p = param_map.get(key)
            if p is None:
                row[kind] = None
                continue

            fit     = p["fit"]
            central = fit[0]
            err_lo  = central - fit[1]   # positive: how far down from central
            err_hi  = fit[2]  - central  # positive: how far up   from central

            if kind == "JMS":
                physical_str = f"{central * jmsr_scale:+.1f} GeV"
            else:
                physical_str = f"{1.0 + central * jmsr_smear:.2f}×"

            row[kind] = {
                "central":  central,
                "err_lo":   err_lo,
                "err_hi":   err_hi,
                "physical": physical_str,
                "status":   classify(central, err_lo, err_hi),
            }

        rows.append(row)

    pois: dict = {}
    for poi in ("r_bb", "r_cc"):
        p = poi_map.get(poi)
        if p:
            fit = p["fit"]
            pois[poi] = {
                "central": fit[0],
                "err_lo":  fit[0] - fit[1],
                "err_hi":  fit[2] - fit[0],
            }

    return rows, pois


# ---------------------------------------------------------------------------
# Output: terminal
# ---------------------------------------------------------------------------

def _pull_str(r: dict | None) -> str:
    if r is None:
        return "N/A"
    return f"{r['central']:+.2f} +{r['err_hi']:.2f}/−{r['err_lo']:.2f}"


def print_table(rows: list, pois: dict, jmsr_scale: float, jmsr_smear: float, tag: str) -> None:
    width = 100
    print()
    print("=" * width)
    print(f"  JMSR Fit Results  |  tag: {tag or '(none)'}  |  "
          f"scale = {jmsr_scale} GeV/σ   smear = {jmsr_smear}/σ")
    print("=" * width)

    if pois:
        for poi, v in pois.items():
            print(f"  {poi} = {v['central']:.3f}  +{v['err_hi']:.3f} / −{v['err_lo']:.3f}")
        print()

    # Column widths
    cw = [8, 26, 12, 26, 10, 28]
    header = ["Year", "JMS (σ)", "JMS shift", "JMR (σ)", "JMR width", "Status (JMS / JMR)"]
    fmt = "  ".join(f"{{:<{w}}}" for w in cw)
    sep = "  " + "-" * (sum(cw) + 2 * (len(cw) - 1))

    print(fmt.format(*header))
    print(sep)
    for row in rows:
        jms, jmr = row["JMS"], row["JMR"]
        jms_status = classify_emoji(jms["status"]) if jms else "—"
        jmr_status = classify_emoji(jmr["status"]) if jmr else "—"
        status_combined = f"{jms_status}  /  {jmr_status}"
        print(fmt.format(
            row["year"],
            _pull_str(jms),
            jms["physical"] if jms else "—",
            _pull_str(jmr),
            jmr["physical"] if jmr else "—",
            status_combined,
        ))
    print(sep)
    print()


# ---------------------------------------------------------------------------
# Output: Markdown
# ---------------------------------------------------------------------------

def write_markdown(rows: list, pois: dict, jmsr_scale: float, jmsr_smear: float,
                   tag: str, path: Path) -> None:
    lines = [
        f"# JMSR Fit Results — `{tag}`",
        "",
        f"**Date:** {date.today()}  ",
        f"**jmsr\\_scale:** {jmsr_scale} GeV/σ &nbsp;&nbsp; "
        f"**jmsr\\_smear:** {jmsr_smear}/σ",
        "",
    ]

    # POI table
    if pois:
        lines += [
            "## Signal strengths",
            "",
            "| POI | Best fit | +1σ | −1σ |",
            "|-----|----------|-----|-----|",
        ]
        for poi, v in pois.items():
            lines.append(
                f"| `{poi}` | **{v['central']:.3f}** "
                f"| +{v['err_hi']:.3f} | −{v['err_lo']:.3f} |"
            )
        lines.append("")

    # JMS table
    lines += [
        "## JMS (Jet Mass Scale)",
        "",
        "| Year | θ_JMS | +1σ | −1σ | Shift | Status |",
        "|------|-------|-----|-----|-------|--------|",
    ]
    for row in rows:
        r = row["JMS"]
        if r:
            lines.append(
                f"| {row['year']} | {r['central']:+.2f} "
                f"| +{r['err_hi']:.2f} | −{r['err_lo']:.2f} "
                f"| {r['physical']} | {classify_emoji(r['status'])} |"
            )
        else:
            lines.append(f"| {row['year']} | N/A | — | — | — | — |")
    lines.append("")

    # JMR table
    lines += [
        "## JMR (Jet Mass Resolution)",
        "",
        "| Year | θ_JMR | +1σ | −1σ | Width scale | Status |",
        "|------|-------|-----|-----|-------------|--------|",
    ]
    for row in rows:
        r = row["JMR"]
        if r:
            lines.append(
                f"| {row['year']} | {r['central']:+.2f} "
                f"| +{r['err_hi']:.2f} | −{r['err_lo']:.2f} "
                f"| {r['physical']} | {classify_emoji(r['status'])} |"
            )
        else:
            lines.append(f"| {row['year']} | N/A | — | — | — | — |")
    lines.append("")

    # Legend
    lines += [
        "## Legend",
        "",
        "- **θ** — dimensionless nuisance parameter (θ = 0: nominal; θ = ±1: ±1σ variation)",
        f"- **JMS shift** = θ × {jmsr_scale} GeV  (positive = mass peak shifted up)",
        f"- **JMR width** = 1 + θ × {jmsr_smear}  (> 1: peak broadened; < 1: narrowed)",
        "- **⚠ at boundary** — statistics-limited; the Z→bb peak has too few events to",
        "  constrain JMS/JMR. Extending the range will not help.",
        "- **✓ well constrained** — avg uncertainty < 0.3σ",
        "- **✓ constrained** — avg uncertainty < 0.7σ",
        "- **~ loosely constrained** — errors are large; treat with caution",
    ]

    path.write_text("\n".join(lines) + "\n")
    print(f"[Saved Markdown → {path}]")


# ---------------------------------------------------------------------------
# Output: CSV
# ---------------------------------------------------------------------------

def write_csv(rows: list, pois: dict, path: Path) -> None:
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow([
            "year",
            "jms_central", "jms_err_hi", "jms_err_lo", "jms_shift_GeV", "jms_status",
            "jmr_central", "jmr_err_hi", "jmr_err_lo", "jmr_width_scale", "jmr_status",
        ])
        for row in rows:
            jms, jmr = row["JMS"], row["JMR"]
            w.writerow([
                row["year"],
                f"{jms['central']:.4f}" if jms else "",
                f"{jms['err_hi']:.4f}"  if jms else "",
                f"{jms['err_lo']:.4f}"  if jms else "",
                jms["physical"]          if jms else "",
                jms["status"]            if jms else "",
                f"{jmr['central']:.4f}" if jmr else "",
                f"{jmr['err_hi']:.4f}"  if jmr else "",
                f"{jmr['err_lo']:.4f}"  if jmr else "",
                jmr["physical"]          if jmr else "",
                jmr["status"]            if jmr else "",
            ])

        # Append POI rows
        if pois:
            w.writerow([])
            w.writerow(["poi", "central", "err_hi", "err_lo"])
            for poi, v in pois.items():
                w.writerow([poi, f"{v['central']:.4f}",
                             f"{v['err_hi']:.4f}", f"{v['err_lo']:.4f}"])

    print(f"[Saved CSV     → {path}]")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(args: argparse.Namespace) -> None:
    with open(args.setup) as f:
        setup = json.load(f)
    jmsr_scale = float(setup.get("jmsr_scale", 3))
    jmsr_smear = float(setup.get("jmsr_smear", 0.2))

    if args.impacts:
        param_map, poi_map = load_impacts(args.impacts)
    else:
        param_map, poi_map = load_fitdiag(args.fitfile)

    rows, pois = extract(param_map, poi_map, jmsr_scale, jmsr_smear)

    print_table(rows, pois, jmsr_scale, jmsr_smear, args.tag)

    out_md  = Path(args.output)
    out_csv = out_md.with_suffix(".csv")
    write_markdown(rows, pois, jmsr_scale, jmsr_smear, args.tag, out_md)
    write_csv(rows, pois, out_csv)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Tabulate JMS/JMR nuisance results from a Combine fit.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    src = parser.add_mutually_exclusive_group(required=True)
    src.add_argument(
        "--impacts",
        metavar="JSON",
        help="Path to combineTool impacts JSON  (preferred — includes errors)",
    )
    src.add_argument(
        "--fitfile",
        metavar="ROOT",
        help="Path to fitDiagnostics ROOT file  (central values only, no errors)",
    )
    parser.add_argument(
        "-j", "--setup",
        default="setup_zgcr.json",
        help="Path to setup JSON (reads jmsr_scale, jmsr_smear)",
    )
    parser.add_argument(
        "-o", "--output",
        default="jmsr_results.md",
        help="Output Markdown file (a .csv is written alongside it)",
    )
    parser.add_argument(
        "--tag",
        default="",
        help="Label for this fit run, e.g. 'newdisc_jmsr'",
    )
    main(parser.parse_args())
