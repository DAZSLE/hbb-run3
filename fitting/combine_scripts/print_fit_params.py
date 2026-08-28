"""
Print fit parameters / Format fit parameters for AN
Author(s): Lara Zygala

example run:
python print_fit_params.py ../results/26Jun12_ParTGeneric/2024/datacards/srModel_2024/fitDiagnosticsTest.root --fit fit_b --year 2024
python print_fit_params.py ../results/26May18_nosyst/Run3/fitDiagnosticsTest.root --fit fit_b --tt_latex
"""

import argparse
import ROOT

# Parameters you want to print
parameters = [
    # "rVBF",
    # "rggF",
    # "rVH",
    "tqqeffSF",
    "tqqeffBCSF",
    "tqqnormSF",
]

ttSF_latex_titles = {
    "tqqnormSF": "$SF^{\\ttbar}_{norm}$",
    "tqqeffSF": "$SF^{\\ttbar}_{mistag}$",
    "tqqeffBCSF": "$SF^{\\ttbar}_{bb/cc}$",
}
ttSF_latex_lines = {}

years = ["2022", "2022EE", "2023", "2023BPix", "2024"]
    
def get_param_valerr(name, final_params):
    param = final_params.find(name)
    if param:
        return f'$ {param.getVal():.5f} \\pm {param.getError():.5f} $'
    else:
        return f'PARAM {name} NOT FOUND'

def main(args):

    # Open ROOT file
    f = ROOT.TFile.Open(args.filename)

    if not f or f.IsZombie():
        raise RuntimeError(f"Could not open {args.filename}")

    # Get RooFitResult
    fit = f.Get(args.fit)

    if not fit:
        raise RuntimeError(f"Could not find {args.fit} in {args.filename}")

    # Final fitted floating parameters
    final_params = fit.floatParsFinal()
    
    if args.tt_latex:
        for ttSF in ttSF_latex_titles:
            ttSF_latex_lines[ttSF] = f"{ttSF_latex_titles[ttSF]} & {' & '.join([get_param_valerr(f'{ttSF}_{yr}', final_params) for yr in years])} \\\\"
            
        print("--------------------TABLE TO COPY INTO AN---------------------\n\n\n")
        for ttSF in ttSF_latex_lines:
            print("\\hline")
            print(ttSF_latex_lines[ttSF])
        print("\\hline")
        print("\n\n\n------------------------------------------------------------------")
        
    else:
        year = args.year
        for name in parameters:
            param_name = f"{name}_{year}"
            print(f"{name}: {get_param_valerr(param_name, final_params)}")

    print(f"\nParameters from {args.fit}:\n")
    f.Close()


if __name__ == "__main__":
    
    parser = argparse.ArgumentParser(
        description="Print selected parameters from a Combine FitDiagnostics result."
    )
    parser.add_argument(
        "filename",
        nargs="?",
        default="fitDiagnosticsTest.root",
        help="FitDiagnostics ROOT file (default: fitDiagnosticsTest.root)",
    )
    parser.add_argument(
        "--fit",
        choices=["fit_b", "fit_s"],
        default="fit_b",
        help="Fit result to use (default: fit_s)",
    )
    parser.add_argument(
        "--year",
        choices=["2022", "2022EE", "2023", "2023BPix", "2024"],
        default="2022",
        help="Year choice for individual parameter printing",
    )
    parser.add_argument(
        "--tt_latex",
        action="store_true",
        help="Format the tt SFs into the latex table format for the AN",
    )
    args = parser.parse_args()
    main(args)
    