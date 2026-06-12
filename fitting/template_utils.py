"""
Template Creation Utilities - common helper functions for creating templates
and dealing with systematics

Lara Zygala March 2026
"""

import numpy as np
import uproot
import pickle


# --- REGION DIRECTORY MAPPING ---
# Maps the keys in setup.json to the actual directory names on EOS
REGION_MAP = {
    "zgcr": "control-zgamma",
    "mucr": "control-tt",
    "zmmcr": "control-zmumu",
    "vh": "signal-vh",
    "vbf": "signal-vbf",
    "ggf": "signal-ggf",
}

#systematics special groupings
folder_systs = ["JES", "JER", "UES", "MuonPTScale", "MuonPTRes"]
analysis_systs = ["pdf_Higgs", "scalevar7pt", "scalevar3pt"]
year_systs = ["btagSFb", "btagSFc", "btagSFlight"]
sig_th_systs = ["pdf_Higgs", "ISRPartonShower", "FSRPartonShower", "QCDScale"]

#Add "VJets" to active_systs in setup.json in order to activate the systs below
Zjets_thsysts = ['d1kappa_EW', 'Z_d2kappa_EW', 'Z_d3kappa_EW', 'd1K_NLO', 'd2K_NLO']
Wjets_thsysts = ['d1kappa_EW', 'W_d2kappa_EW', 'W_d3kappa_EW', 'd1K_NLO', 'd2K_NLO', 'd3K_NLO'] 

scalevar_map = {
    "3pt" : [0, 4, 8],             # case where muF^2 = muR^2
    "7pt" : [0, 1, 3, 4, 5, 7, 8]  # case where muF = muR 
}

scalevar_process = {
    "ggFbb": "7pt",
    "ggFcc": "7pt",
    "VBFbb": "3pt",
    "VBFcc": "3pt",
    "WHbb": "3pt",
    "WHcc": "3pt",
    "ZHbb": "3pt",
    "ZHcc": "3pt",
    "ttH": "7pt"
}

def get_pdf_list(n_var = 103):
    #Collect columns for pdf analysis, sum_weights stored in pickle files
    return [f"weight_pdf_{i}" for i in range(n_var)]
    
def get_scale_list(structure = "7pt"):
    #Collect columns for qcd scale analysis, sum_weights stored in pickle files
    return [f"weight_scalevar_{structure}_{i}" for i in scalevar_map[structure]]
   
def perform_analysis(data, selection, nom_weight, syst_analysis):
    #Select which analysis to perform: QCDScale or PDF
    #Returns the scale factor to be applied to the histogram
    sysdir = "Up" if "Up" in syst_analysis else "Down"
    if "pdf" in syst_analysis:
        rel_unc = pdf_analysis(data, nom_weight, selection)
        factor = (1.0 + rel_unc) if sysdir == "Up" else (1.0 - rel_unc)
    elif "scalevar" in syst_analysis:
        if "7pt" in syst_analysis:
            factor = scalevar_analysis(data, nom_weight, selection, "7pt", sysdir)
        elif "3pt" in syst_analysis:
            factor = scalevar_analysis(data, nom_weight, selection, "3pt", sysdir)

    return factor

def pdf_analysis(data, nom_weight, selection, n_var = 103):
    #Perform the PDF uncertainty analysis
    #Returns the relative uncertainty
    pdfweights = []
    for i in range(n_var):
        ri = data[f"sumweight_pdf_{i}"][selection] / data["sum_genWeight"][selection]
        pdfweights.append( data[f"weight_pdf_{i}"][selection] * nom_weight[selection] / ri )

    pdfweights = np.swapaxes(np.array(pdfweights), 0, 1)
    abs_unc = np.linalg.norm((pdfweights - nom_weight[selection].values.reshape(-1, 1)), axis=1)
    rel_unc = np.clip(abs_unc / nom_weight[selection], 0, 1)

    return rel_unc

def scalevar_analysis(data, nom_weight, selection, structure, direction):
    #Perform the QCD Scale uncertainty analysis
    #Returns the scale factor
    r4 = data[f"sumweight_scalevar_{structure}_4"][selection] / data["sum_genWeight"][selection]
    scale4 = data[f"weight_scalevar_{structure}_4"][selection] * nom_weight[selection] / r4

    scaleweights = []
    for var in scalevar_map[structure]:
        if var == 4:
            continue

        ri = data[f"sumweight_scalevar_{structure}_{var}"][selection] / data["sum_genWeight"][selection]
        scaleweights.append( data[f"weight_scalevar_{structure}_{var}"][selection] * nom_weight[selection] / ri )
        
    scaleweights = np.swapaxes(np.array(scaleweights), 0, 1)
    scaleweights = np.max(scaleweights, axis=1) if direction=="Up" else np.min(scaleweights, axis=1)

    sf = scaleweights / scale4

    return sf

def set_rootfile(output_root):
    # Ensure outdir exists
    output_root.parent.mkdir(parents=True, exist_ok=True)

    # Delete existing file to start fresh for this region
    # (This avoids the errors by ensuring we never 'update' a corrupted or old file)
    if output_root.exists():
        print(f"Cleaning up existing file: {output_root}")
        output_root.unlink()

    # Initialize a fresh ROOT file
    uproot.recreate(output_root).close()

def export_to_root(histograms, output_root_path, data_key):
    # Ensure directory exists
    output_root_path.parent.mkdir(parents=True, exist_ok=True)

    # Use uproot.update for writing
    # If the file doesn't exist, uproot.update will create it.
    with uproot.update(output_root_path) as fout:
        for process, h in histograms.items():
            proc_name = "data_obs" if process == data_key else process
            fout[proc_name] = h

def export_to_pkl(pickle_path):
    with pickle_path.open("wb") as f:
        pickle.dump(histograms_pkl, f)
    print(f"  [SUCCESS] Pickles saved to: {pickle_path}")
    del  histograms_pkl


def accumulate(outdict, name, h):
    if name not in outdict:
        outdict[name] = h.copy()
    else:
        outdict[name] += h.copy()  
    return outdict
