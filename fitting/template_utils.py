"""
Template Creation Utilities - common helper functions for creating templates
and dealing with systematics

Lara Zygala March 2026
"""

import numpy as np
import uproot
import pickle
import hist
import gc
import re
import shelve
from pathlib import Path
import subprocess
import zlib

# --- AN-23-206 App.H stitching of NLO photon-pT-binned V+γ samples ---------
# The 2024 "Bin-...-PTG-{100,200,400,600}" samples are INCLUSIVE-above (min-pT
# cut, no max) so stacking them multi-counts. Make each exclusive by keeping
# only events whose photon pT falls in that bin's window (AN-23-206 Appendix H).
#
# Stitching variable = the LHE-level photon pT ("LHEGammaPt"), the quantity the
# gridpack pT binning is applied on (AN-23-206 App.H). The post-shower "GenGammaPt"
# is only a proxy (it leaks across the bin boundaries) and is used as a fallback for
# older skims that predate the LHEGammaPt column (see the 26Sep17_lhephoton_v15 reskim).
#
# ALL four V+γ families are gen-stitched now that LHEGammaPt is stored for each:
#   ZGto2QG (bb), WGto2QG (cs), DYGto2LG (μμ), WGtoLNuG (W+γ). Their fully-inclusive
# members are dropped when present. (Earlier only ZGto2QG was stitched; WGto2QG/
# WGtoLNuG kept the inclusive member and DYGto2LG used PTG-100 only — all superseded.)
# Gated by setup flag "stitch_ptg".
_PTG_EDGES = {"100": (100.0, 200.0), "200": (200.0, 400.0),
              "400": (400.0, 600.0), "600": (600.0, np.inf)}
# photon-pT stitching variable, in order of preference (LHE first, gen proxy fallback)
_STITCH_VARS = ("LHEGammaPt", "GenGammaPt")
# datasets to DROP entirely when stitching (fully-inclusive, replaced by stitched bins).
# DYGto2LG has no fully-inclusive member (only Bin-MLL-50-PTG-N), so nothing to drop there.
_STITCH_DROP_INCLUSIVE = {"ZGto2QG-1Jets", "WGto2QG-1Jets", "WGtoLNuG-1Jets"}

# --- Event-by-event JMS/JMR (J. Duarte's HistSmear gist) --------------------
#   m' = m * JMS * (1 + z * sqrt(JMR^2 - 1) * sigma / m),   z ~ N(0,1) per event
# (= MorphHistW2.get(shift=(JMS-1)*mean, smear=JMR) on the histogram). z is drawn
# once per event and shared by nominal and all JMS/JMR variations. JMR < 1 cannot
# be reached by smearing -> no smear (the datacard mirrors JMR down in that case).
# Gated by setup "jmsr_mode": "event"; parameters in setup "jmsr_event".
_JMSR_KEYS = ("JMS", "JMR")


def jmsr_event_mode(setup):
    return setup.get("jmsr_mode", "morph") == "event"


def jmsr_smear_mass(mass, z, jms, jmr, sigma):
    k = np.sqrt(max(jmr * jmr - 1.0, 0.0))
    return jms * (mass + z * k * sigma)


def jmsr_params(cfg, in_syst):
    """(JMS, JMR) for a variation name, e.g. 'JMSunconstrainedUp' -> (jms + jms_unc, jmr)."""
    jms, jmr = cfg.get("jms", 1.0), cfg.get("jmr", 1.0)
    if in_syst.startswith(_JMSR_KEYS) and in_syst.endswith(("Up", "Down")):
        sign = 1.0 if in_syst.endswith("Up") else -1.0
        if in_syst.startswith("JMS"):
            jms += sign * cfg.get("jms_unc", 0.01)
        else:
            jmr += sign * cfg.get("jmr_unc", 0.1)
    return jms, jmr



def _ptg_bin(dataset):
    """Return '100'/'200'/'400'/'600' for a 2024 Bin-...-PTG-N sample, else None."""
    m = re.search(r"Bin-(?:MLL-50-)?PTG-(100|200|400|600)$", dataset)
    return m.group(1) if m else None


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
    if "pdf_Higgs" in syst_analysis:
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

def shelve_to_root(input_shelve_path, output_root_path):
    # Ensure outdir exists
    output_root_path.parent.mkdir(parents=True, exist_ok=True)

    # Delete existing file to start fresh for this region
    # (This avoids the errors by ensuring we never 'update' a corrupted or old file)
    if output_root_path.exists():
        print(f"Cleaning up existing file: {output_root_path}")
        output_root_path.unlink()

    # Initialize a fresh ROOT file
    uproot.recreate(output_root_path, compression=None).close()

    for ps in [".dat", ".bak", ".dir"]:
        f = Path(f"FINAL_TEMPLATES{ps}")
        if f.exists():
            print(f"Cleaning up existing file: {f}")
            f.unlink()

    with shelve.open("FINAL_TEMPLATES") as db_out:
        for db_file in list((Path(input_shelve_path)).glob("*.dat")):
            if Path(db_file).exists():
                print(db_file)
                with shelve.open(str(db_file).replace(".dat", "")) as db:
                    for h_name in db:
                        if h_name in db_out:
                            db_out[h_name] = db_out[h_name] + db[h_name]
                        else:
                            db_out[h_name] = db[h_name]

    with uproot.update(output_root_path) as fout:
        if Path("FINAL_TEMPLATES.dat").exists():
            with shelve.open("FINAL_TEMPLATES") as db:
                for h_name in db:
                    fout[h_name] = db[h_name]

def shelve_to_pkl(input_shelve_path, args):

    for ps in [".dat", ".bak", ".dir"]:
        f = Path(f"FINAL_PLOTTING{ps}")
        if f.exists():
            print(f"Cleaning up existing file: {f}")
            f.unlink()

    all_systs = []
    all_reg = []
    all_procs = []
    with shelve.open("FINAL_PLOTTING") as db_out:
        for db_file in list((Path(input_shelve_path)).glob("*.dat")):
            if Path(db_file).exists():
                print(db_file)
                with shelve.open(str(db_file).replace(".dat", "")) as db:
                    for h_name in db:
                        proc = h_name.split("|")[0]
                        reg = h_name.split("|")[1]
                        syst = h_name.split("|")[2]
                        if not proc in all_procs:
                            all_procs.append(proc)
                        if not reg in all_reg:
                            all_reg.append(reg)
                        if not syst in all_systs:
                            all_systs.append(syst)
                        if h_name in db_out:
                            db_out[h_name] = db_out[h_name] + db[h_name]
                        else:
                            db_out[h_name] = db[h_name]

    with shelve.open("FINAL_PLOTTING") as db:
        for region in all_reg:
            for sys in all_systs:
                dict_sys = {}
                for h_name in db:
                    proc = h_name.split("|")[0]
                    reg = h_name.split("|")[1]
                    syst = h_name.split("|")[2]
                    if sys == syst and reg == region:
                        dict_sys[proc] = db[h_name]

                pickle_path = (
                        Path(args.outdir) / f"hists_{args.year}_{region}_msd_{sys}.pkl"
                    ) 
                if pickle_path.exists():
                    print(f"Cleaning up existing file: {pickle_path}")
                    pickle_path.unlink()           
                with pickle_path.open("wb") as f:
                    pickle.dump(dict_sys, f)

def export_h_to_shelve(in_hist, h_name, output_pkl_path):
    # Ensure directory exists
    Path((output_pkl_path+".dat")).parent.mkdir(parents=True, exist_ok=True)
    print("saving: ", output_pkl_path)

    with shelve.open(str(output_pkl_path), writeback=True) as db:
        if h_name in db:
            db[h_name] = db[h_name] + in_hist
        else:
            db[h_name] = in_hist

def eos_exists(path):
    result = subprocess.run(
        ["xrdfs", "root://cmseos.fnal.gov", "stat", path],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return result.returncode == 0

def fill_binned_histogram(
    events, region_key, setup, args, systs=["nominal"], template_outfile_path="", plotting_outfile_path="",
    dataset="",
):
    samples_qq = setup.get("samples_qq", [])
    
    reg_cfg = setup["categories"][region_key]
    bin_branch = reg_cfg.get("bin_branch", "FatJet0_pt")
    bin_prefix = reg_cfg.get("bin_prefix", "pt")
    bins_list = reg_cfg["bins"]

    obs = setup["observable"]
    axis_var = hist.axis.Regular(obs["nbins"], obs["min"], obs["max"], name=obs["name"], label=obs["name"])
    axis_bin = hist.axis.Variable(np.array(bins_list), name=bin_prefix)  # Replaced axis_pt
    axis_cat = hist.axis.StrCategory(["pass_bb", "pass_cc", "fail", "pass", "inclusive"], name="category")
    axis_flav = hist.axis.IntCategory([0, 1, 2, 3], name="genflavor")

    h_plotting = hist.Hist(axis_var, axis_bin, axis_cat, axis_flav)

    for process_name, data in events.items():
        is_data = "data" in process_name.lower()
        should_split = any(s in process_name for s in samples_qq) and not is_data


        # --- VARIABLE EXTRACTION ---
        var_col = obs["branch_name"]
        pt = data["FatJet0_pt"]

        Txcc = data["FatJet0_ParTPXccVsQCD"]
        Txbb = data["FatJet0_ParTPXbbVsQCD"]
        Txbbxcc = data["FatJet0_ParTPXbbXcc"]

        pt_min = setup.get("pt_min_scale", 450.0)
        working_point = setup.get("working_point", 0.82)

        # Robust MET extraction from the parquet record
        met_pt = np.zeros(len(data))
        if "MET" in data.columns:
            met_pt = data["MET"].pt if hasattr(data["MET"], "pt") else data["MET"]

        dphi = np.nan
        if "Photon0_phi" in data.columns and "FatJet0_phi" in data.columns:
            dphi_raw = np.abs(data["Photon0_phi"] - data["FatJet0_phi"])
            dphi = np.where(dphi_raw > np.pi, 2 * np.pi - dphi_raw, dphi_raw)

        if setup.get("use_regressed_mass", False):
            # regressed-mass flavour comes from the setup (ParTmassX2p or ParTmassGeneric)
            var_series = data[var_col]
        elif var_col == "delta_phi_photon_jet":
            var_series = dphi
        else:
            var_series = data[var_col]

        genflavordata = (
            np.zeros(len(data), dtype=np.int8) if is_data else data["GenFlavor"].astype(np.int8)
        )

        # event-by-event JMS/JMR: the observable window is applied per variation below
        jmsr_cfg = setup.get("jmsr_event", {})
        apply_jmsr = (
            jmsr_event_mode(setup) and not is_data
            and any(p in process_name for p in jmsr_cfg.get("processes", samples_qq))
        )
        if apply_jmsr:
            seed = [jmsr_cfg.get("seed", 42), zlib.crc32(f"{dataset}|{process_name}".encode()), len(data)]
            jmsr_z = np.random.default_rng(seed).standard_normal(len(data))
            raw_mass = var_series.to_numpy(dtype=float)

        # --- SELECTION LOGIC ---
        basic_cuts = (var_series > obs["min"]) & (var_series < obs["max"])
        if apply_jmsr:
            basic_cuts = var_series.notna()

        pre_selection = basic_cuts & (pt > pt_min)  #signal categories
        if "zgcr" in region_key:
            # Specific Z-Gamma logic from Gabi's script
            trigger = data["Photon200"] | data["Photon110EB_TightID_TightIso"]
            topo_cuts = (dphi > 2.2) & (met_pt < 50) & (data["Photon0_pt"] > 120)
            pre_selection = basic_cuts & topo_cuts & trigger & (pt > pt_min)
        elif "zmmcr" in region_key:
            # Z(mumu) CR: observable is mll, bin variable is dimuon pair pt
            pre_selection = basic_cuts & (data[bin_branch] > pt_min)

        # --- AN-23-206 App.H stitching of photon-pT-binned V+γ samples ---
        if setup.get("stitch_ptg", False) and not is_data:
            ptg = _ptg_bin(dataset)
            if ptg is not None:
                # prefer the LHE-level photon pT; fall back to the GenGammaPt proxy
                stitch_col = next((c for c in _STITCH_VARS if c in data.columns), None)
                if stitch_col is not None:
                    # keep only events whose photon pT falls in this bin's window.
                    # (window lo >= 100, so the LHEGammaPt=-1 no-photon sentinel is excluded)
                    lo, hi = _PTG_EDGES[ptg]
                    gpt = data[stitch_col].astype(float)
                    pre_selection = pre_selection & (gpt >= lo) & (gpt < hi)
                else:
                    # binned sample with no stitch variable at all (pre-reskim skim)
                    # -> cannot stitch -> drop it, rely on the inclusive member
                    continue
            elif dataset in _STITCH_DROP_INCLUSIVE:
                # fully-inclusive member replaced by the gen-stitched binned set -> drop
                continue

        if "zmmcr" in region_key:
            # Only inclusive category for zmumu CR — no Txbb pass/fail
            selection_dict = {"inclusive": pre_selection}
        else:
            if setup.get("use_modified_disc", False):
                # All three discriminants use the same 4-body denominator
                # (Xbb + Xcc + QCD + Xcs), following Cristina's definitions
                _num = data["FatJet0_ParTPXbb"] + data["FatJet0_ParTPXcc"]
                _den = (_num + data["FatJet0_ParTPQCD"] + data["FatJet0_ParTPXcs"]).replace(0, np.nan)
                Txbbxcc = (_num / _den).fillna(0.0)
                Txbb = (data["FatJet0_ParTPXbb"] / _den).fillna(0.0)
                Txcc = (data["FatJet0_ParTPXcc"] / _den).fillna(0.0)
            else:
                Txbbxcc = data["FatJet0_ParTPXbbXcc"]
                Txbb = data["FatJet0_ParTPXbbVsQCD"]
                Txcc = data["FatJet0_ParTPXccVsQCD"]

            disc_mode = setup.get("disc_mode", "xbbxcc")
            if disc_mode == "bbvsqcd":
                # Reproduce Raffaele Gerosa's boosted Z->bb calibration selection:
                # single-sided cut on p(X->bb) vs QCD (Txbb), bb-only (no cc split).
                # VHP=0.99, HP=[0.975,0.99], MP=[0.95,0.975]; pass here = > working_point.
                # Pair with use_modified_disc:false (so Txbb = raw FatJet0_ParTPXbbVsQCD)
                # and regions_to_fit:["bb"].
                pass_sel = Txbb > working_point
                selection_dict = {
                    "pass_bb": pre_selection & pass_sel,
                    "fail": pre_selection & ~pass_sel,
                    "pass": pre_selection & pass_sel,
                    "inclusive": pre_selection,
                }
            else:
                selection_dict = {
                    "pass_bb": pre_selection & (Txbbxcc > working_point) & (Txbb > Txcc),
                    "pass_cc": pre_selection & (Txbbxcc > working_point) & (Txcc > Txbb),
                    "fail": pre_selection & (Txbbxcc <= working_point),
                    "pass": pre_selection & (Txbbxcc > working_point),
                    "inclusive": pre_selection,
                }

        flavor_cuts = {
            "": ((genflavordata == 1) | (genflavordata == 2)),
            "bb": (genflavordata == 3),
            "c": (genflavordata == 2),
            "light": (genflavordata == 1)
        }

        for in_syst in systs:

            is_folder = any(fs in in_syst for fs in folder_systs)
            is_analysis_syst = any(ts in in_syst for ts in analysis_systs)
            weight_syst = in_syst if not is_folder and not is_analysis_syst else "nominal"

            # --- WEIGHTING LOGIC - PER SYST ---
            if not is_data and weight_syst != "nominal" and weight_syst in data.columns:
                # Systematic weights (like btagSF) usually need normalization by sum_genWeight
                weight_val = data[weight_syst].astype(float) / data["sum_genWeight"].astype(float)
            else:
                # load_samples already calculated finalWeight (weight / sum_genWeight)
                weight_val = data["finalWeight"].astype(float)

            mass_s, window = var_series, True
            if apply_jmsr:
                jms, jmr = jmsr_params(jmsr_cfg, in_syst)
                mass_s = var_series.copy()
                mass_s[:] = jmsr_smear_mass(raw_mass, jmsr_z, jms, jmr, jmsr_cfg.get("sigma", 10.0))
                window = (mass_s > obs["min"]) & (mass_s < obs["max"])

            # --- FILLING ---
            def fill_h(name, sel, cat, flag_template=False):
                factor = perform_analysis(data, sel, weight_val, in_syst) if is_analysis_syst else np.ones_like(data[bin_branch][sel])
                if args.debug:
                    print(name, in_syst, is_analysis_syst, len(factor), (next(iter(factor), None)))

                if flag_template:
                    h_template = hist.Hist(axis_var, storage=hist.storage.Weight())
                    h_template.fill(
                        mass_s[sel],
                        weight=weight_val[sel] * factor,
                    )
                    export_h_to_shelve(h_template, name, template_outfile_path)
                    del h_template
                    gc.collect()

                else:
                    h_plotting.fill(
                        mass_s[sel],
                        data[bin_branch][sel],  # using dynamic bin data here
                        category=cat,
                        genflavor=genflavordata[sel],
                        weight=weight_val[sel] * factor,
                    )

            for category, selection in selection_dict.items():
                selection = selection & window
                if args.save_plotting_pkl:
                    if category in axis_cat:
                        fill_h(f"{process_name}|{region_key}|{in_syst}", selection, category)

                if args.save_templates:
                    for i in range(len(bins_list) - 1):
                        bin_cut = (data[bin_branch]  > bins_list[i]) & (data[bin_branch] < bins_list[i+1]) & pre_selection
                        base_name = f"{region_key}_{category}_{bin_prefix}{i+1}_{process_name}"
                        splits = flavor_cuts if should_split else {"": None}

                        for suffix, flavor_mask in splits.items():
                            sel = selection & bin_cut & flavor_mask if flavor_mask is not None else selection & bin_cut
                            name = f"{base_name}{suffix}_{in_syst}"
                            fill_h(name, sel, category, flag_template=True)
            
            if args.save_plotting_pkl:
                name = f"{process_name}|{region_key}|{in_syst}"
                export_h_to_shelve(h_plotting, name, plotting_outfile_path)

    return 