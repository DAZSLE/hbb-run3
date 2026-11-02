"""
Combine F-Test Runner

Automates the Combine commands required to perform an F-test between two
competing workspace models (a 'Null' simpler model and an 'Alt' complex model).
Generates snapshots, computes the observed Goodness-of-Fit (saturated algorithm),
and generates/fits pseudo-experiments (toys) to evaluate the models.

Gabi Hamilton - Feb 2026
"""

from __future__ import annotations

import argparse
import os

EXTRA = ""  # extra combine args (e.g. parameter ranges), set from --extra


def run_command(cmd):
    if cmd.startswith("combine") and EXTRA:
        cmd = f"{cmd} {EXTRA}"
    print(f"\n[F-TEST] Running: {cmd}")
    os.system(cmd)


def main(w_null, w_alt, ntoys, seed, tag):
    # We append the tag to the names so files don't get overwritten
    suffix = f"_{tag}" if tag else ""

    # 1. Create Snapshots
    print(f"--- Creating Snapshots ({tag}) ---")
    run_command(
        f"combine -M MultiDimFit -d {w_null} -n _Null_Snapshot{suffix} --saveWorkspace --cminDefaultMinimizerStrategy 0"
    )
    run_command(
        f"combine -M MultiDimFit -d {w_alt}  -n _Alt_Snapshot{suffix}  --saveWorkspace --cminDefaultMinimizerStrategy 0"
    )

    # 2. Observed GoF
    print(f"--- Calculating Observed GoF ({tag}) ---")
    # Note: We use the snapshots created above
    run_command(
        f"combine -M GoodnessOfFit -d higgsCombine_Null_Snapshot{suffix}.MultiDimFit.mH120.root --snapshotName MultiDimFit --bypassFrequentistFit -n _Observed_Null{suffix} --algo saturated"
    )
    run_command(
        f"combine -M GoodnessOfFit -d higgsCombine_Alt_Snapshot{suffix}.MultiDimFit.mH120.root  --snapshotName MultiDimFit --bypassFrequentistFit -n _Observed_Alt{suffix}  --algo saturated"
    )

    # 3. Generate Toys
    print(f"--- Generating {ntoys} Toys ({tag}) ---")
    run_command(
        f"combine -M GenerateOnly -d higgsCombine_Null_Snapshot{suffix}.MultiDimFit.mH120.root --snapshotName MultiDimFit --bypassFrequentistFit -n _Toys{suffix} --saveToys -t {ntoys} --seed {seed}"
    )

    # 4. Fit Toys
    toy_file = f"higgsCombine_Toys{suffix}.GenerateOnly.mH120.{seed}.root"

    print(f"--- Fitting Toys with Null Model ({tag}) ---")
    run_command(
        f"combine -M GoodnessOfFit -d higgsCombine_Null_Snapshot{suffix}.MultiDimFit.mH120.root --snapshotName MultiDimFit --bypassFrequentistFit -n _Toys_Null{suffix} -t {ntoys} --algo saturated --toysFile {toy_file} --seed {seed}"
    )

    print(f"--- Fitting Toys with Alt Model ({tag}) ---")
    run_command(
        f"combine -M GoodnessOfFit -d higgsCombine_Alt_Snapshot{suffix}.MultiDimFit.mH120.root  --snapshotName MultiDimFit --bypassFrequentistFit -n _Toys_Alt{suffix}  -t {ntoys} --algo saturated --toysFile {toy_file} --seed {seed}"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--null", required=True, help="Workspace for simpler model")
    parser.add_argument("--alt", required=True, help="Workspace for complex model")
    parser.add_argument("--ntoys", default=100, type=int, help="Number of toys")
    parser.add_argument("--seed", default=123456, type=int, help="Random seed")
    parser.add_argument("--tag", default="", help="Tag to append to filenames (e.g. 2022)")
    parser.add_argument("--extra", default="", help="Extra args for every combine call, e.g. --setParameterRanges CMS_jms_2024=-10,10")
    args = parser.parse_args()

    EXTRA = args.extra
    main(args.null, args.alt, args.ntoys, args.seed, args.tag)
