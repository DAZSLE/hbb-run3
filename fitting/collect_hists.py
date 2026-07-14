
from pathlib import Path
from template_utils import (
    shelve_to_root,
    shelve_to_pkl
)
import argparse
import os

def main(args):

    # Ensure outdir exists before starting
    Path(args.outdir).mkdir(parents=True, exist_ok=True)
    
    if args.save_templates:
        output_root_path = Path(args.outdir) / args.tag / f"fitting_{args.year}_msd.root"
        eos_path = f"/eos/uscms/store/group/lpchbbrun3/{os.getlogin()}/FITTING_TEMPLATES/"
        shelve_to_root(eos_path, output_root_path)

    if args.save_plotting_pkl:
        eos_path = f"/eos/uscms/store/group/lpchbbrun3/{os.getlogin()}/PLOTTING_PICKLES/"
        shelve_to_pkl(eos_path, args)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Unified Histogram Maker for Signal and CR")
    parser.add_argument("--year", required=True, choices=["2022", "2022EE", "2023", "2023BPix", "2024"])
    parser.add_argument("--tag", default=None, help="Tag for the skims directory (e.g., 26Feb03). Required if --data-dir is not provided.")
    parser.add_argument("--outdir", default="results", help="Directory to save ROOT files")
    parser.add_argument("--save-templates", action="store_true", help="Actually write the ROOT file")
    parser.add_argument("--save-plotting-pkl", action="store_true", help="Actually write the PKL file")

    args = parser.parse_args()
    main(args)