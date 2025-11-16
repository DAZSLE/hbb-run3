"""
Collection of utilities for corrections and systematics in processors.

Most corrections retrieved from the cms-nanoAOD repo:
See https://cms-nanoaod-integration.web.cern.ch/commonJSONSFs/
"""

from __future__ import annotations

import pathlib
from pathlib import Path

import contextlib

import awkward as ak
import dask_awkward as dak
import numpy as np
import correctionlib
from coffea.analysis_tools import Weights
from coffea.nanoevents.methods import vector
from coffea.nanoevents.methods.nanoaod import JetArray
from coffea.jetmet_tools import CorrectedJetsFactory, CorrectedMETFactory, JECStack
from coffea.lookup_tools import extractor
import pickle

from hbb.jerc_eras import jec_eras,jer_eras, jec_mc, jer_mc, jec_data, fatjet_jerc_keys, jet_jerc_keys
from hbb.taggers import b_taggers

ak.behavior.update(vector.behavior)
package_path = str(pathlib.Path(__file__).parent.parent.resolve())

# Important Run3 start of Run
FirstRun_2022C = 355794
FirstRun_2022D = 357487
LastRun_2022D = 359021
FirstRun_2022E = 359022
LastRun_2022F = 362180

"""
CorrectionLib files are available from: /cvmfs/cms.cern.ch/rsync/cms-nanoAOD/jsonpog-integration - synced daily
"""
pog_correction_path = "/cvmfs/cms.cern.ch/rsync/cms-nanoAOD/jsonpog-integration/"
pog_jsons = {
    "muon": ["MUO", "muon_Z.json.gz"],
    "electron": ["EGM", "electron.json.gz"],
    "pileup": ["LUM", "puWeights.json.gz"],
    "fatjet_jec": ["JME", "fatJet_jerc.json.gz"],
    "jet_jec": ["JME", "jet_jerc.json.gz"],
    "jetveto": ["JME", "jetvetomaps.json.gz"],
    "btagging": ["BTV", "btagging.json.gz"],
    "jetid" : ["JME", "jetid.json.gz"],
}

years = {
    "2022": "2022_Summer22",
    "2022EE": "2022_Summer22EE",
    "2023": "2023_Summer23",
    "2023BPix": "2023_Summer23BPix",
    "2024": "2024_Summer24",
}


def ak_clip(arr: ak.Array, min_value: float, max_value: float):
    """
    Clip the values of an awkward array using where
    """
    return ak.where(arr < min_value, min_value, ak.where(arr > max_value, max_value, arr))


def get_pog_json(obj: str, year: str) -> str:
    try:
        pog_json = pog_jsons[obj]
    except:
        print(f"No json for {obj}")

    year = years[year]

    return f"{pog_correction_path}/POG/{pog_json[0]}/{year}/{pog_json[1]}"


def build_lumimask(filename):
    from coffea.lumi_tools import LumiMask

    path = Path(f"{package_path}/hbb/data/{filename}")
    return LumiMask(path)


lumiMasks = {
    "2022": build_lumimask("Cert_Collisions2022_355100_362760_Golden.json"),
    "2022EE": build_lumimask("Cert_Collisions2022_355100_362760_Golden.json"),
    "2023": build_lumimask("Cert_Collisions2023_366442_370790_Golden.json"),
    "2023BPix": build_lumimask("Cert_Collisions2023_366442_370790_Golden.json"),
    "2024": build_lumimask("Cert_Collisions2024_378981_386951_Golden.json"),
}


def add_pileup_weight(weights: Weights, year: str, nPU):
    # clip nPU from 0 to 150
    nPU = ak_clip(nPU, 0, 150)

    # https://twiki.cern.ch/twiki/bin/view/CMS/LumiRecommendationsRun3
    values = {}

    cset = correctionlib.CorrectionSet.from_file(get_pog_json("pileup", year))
    corr = {
        "2018": "Collisions18_UltraLegacy_goldenJSON",
        "2022": "Collisions2022_355100_357900_eraBCD_GoldenJson",
        "2022EE": "Collisions2022_359022_362760_eraEFG_GoldenJson",
        "2023": "Collisions2023_366403_369802_eraBC_GoldenJson",
        "2023BPix": "Collisions2023_369803_370790_eraD_GoldenJson",
        #"2024": "", Not yet derived by pog
    }[year]
    # evaluate and clip up to 4 to avoid large weights
    values["nominal"] = ak_clip(cset[corr].evaluate(nPU, "nominal"), 0, 4)
    values["up"] = ak_clip(cset[corr].evaluate(nPU, "up"), 0, 4)
    values["down"] = ak_clip(cset[corr].evaluate(nPU, "down"), 0, 4)

    weights.add("pileup", values["nominal"], values["up"], values["down"])

def add_pdf_weight(weights, pdf_weights):

    nom = ak.ones_like(weights.weight())
    if pdf_weights is None:
        weights.add('PDF_weight', nom)
        weights.add('aS_weight', nom)
        weights.add('PDFaS_weight', nom)
        return
                               
    arg = pdf_weights[:,1:-2]-(ak.ones_like(weights.weight())[:, None] * ak.Array(np.ones(100)))
    summed = ak.sum(np.square(arg),axis=1)
    pdf_unc = np.sqrt( (1./99.) * summed )
    weights.add('PDF_weight', nom, pdf_unc + nom)

    # alpha_S weights
    as_unc = 0.5*(pdf_weights[:,102] - pdf_weights[:,101])
    weights.add('aS_weight', nom, as_unc + nom)

    # PDF + alpha_S weights
    pdfas_unc = np.sqrt( np.square(pdf_unc) + np.square(as_unc) )
    weights.add('PDFaS_weight', nom, pdfas_unc + nom) 

def add_ps_weight(weights, ps_weights):
    """
    Parton Shower Weights (FSR and ISR)
    """
    nom = ak.ones_like(weights.weight())

    up_isr = ak.ones_like(nom)
    down_isr = ak.ones_like(nom)
    up_fsr = ak.ones_like(nom)
    down_fsr = ak.ones_like(nom)

    if ak.num(ps_weights[0], axis=0) == 4:
        up_isr = ps_weights[:, 0]  # ISR=2, FSR=1
        down_isr = ps_weights[:, 2]  # ISR=0.5, FSR=1

        up_fsr = ps_weights[:, 1]  # ISR=1, FSR=2
        down_fsr = ps_weights[:, 3]  # ISR=1, FSR=0.5

    elif ak.num(ps_weights[0], axis=0) > 1:
        print("PS weight vector has length ", ak.num(ps_weights[0]))

    weights.add("ISRPartonShower", nom, up_isr, down_isr)
    weights.add("FSRPartonShower", nom, up_fsr, down_fsr)

def add_scalevar_7pt(weights, var_weights):

    nom   = ak.ones_like(weights.weight())
    up    = ak.ones_like(nom)
    down  = ak.ones_like(nom)

    if var_weights is None:
        weights.add('scalevar_7pt', nom)
        return
 
    try:
        selected = var_weights[:, [0, 1, 3, 5, 7, 8]]
        up = ak.max(selected, axis=1)
        down = ak.min(selected, axis=1)
    except Exception as e:
        print("Scale variation structure unexpected:", e)

    weights.add('scalevar_7pt', nom, up, down)

def add_scalevar_3pt(weights,var_weights):

    nom   = ak.ones_like(weights.weight())
    up    = ak.ones_like(nom)
    down  = ak.ones_like(nom)

    if var_weights is None:
        weights.add('scalevar_3pt', nom)
        return

    try:
        selected = var_weights[:, [0, 8]]
        up = ak.max(selected, axis=1)
        down = ak.min(selected, axis=1)
    except Exception as e:
        print("Scale variation structure unexpected:", e)

    weights.add('scalevar_3pt', nom, up, down)

# Jet Veto Maps
# the JERC group recommends ALL analyses use these maps, as the JECs are derived excluding these zones.
# apply to both Data and MC
# https://cms-talk.web.cern.ch/t/jet-veto-maps-for-run3-data/18444?u=anmalara
# https://cms-talk.web.cern.ch/t/jes-for-2022-re-reco-cde-and-prompt-fg/32873
def get_jetveto_event(jets: JetArray, year: str):
    """
    Get event selection that rejects events with jets in the veto map
    """

    # correction: Non-zero value for (eta, phi) indicates that the region is vetoed
    cset = correctionlib.CorrectionSet.from_file(get_pog_json("jetveto", year))
    j, nj = ak.flatten(jets), ak.num(jets)

    def get_veto(j, nj, csetstr):
        j_phi = ak_clip(j.phi, -3.1415, 3.1415)
        j_eta = ak_clip(j.eta, -4.7, 4.7)
        veto = cset[csetstr].evaluate("jetvetomap", j_eta, j_phi)
        return ak.unflatten(veto, nj)

    corr_str = {
        "2022": "Summer22_23Sep2023_RunCD_V1",
        "2022EE": "Summer22EE_23Sep2023_RunEFG_V1",
        "2023": "Summer23Prompt23_RunC_V1",
        "2023BPix": "Summer23BPixPrompt23_RunD_V1",
        "2024": "Summer24Prompt24",
    }[year]

    jet_veto = get_veto(j, nj, corr_str) > 0

    event_sel = ~(ak.any((jets.pt > 15) & (jets.jetidtightlepveto) & jet_veto, axis=1))
    return event_sel

def correct_jetid(jets, jet_type: str, year: str):
    evaluator = correctionlib.CorrectionSet.from_file(get_pog_json("jetid", year))

    if jet_type == "AK8":
        name_tight = "AK8PUPPI_Tight"
        name_tightlv = "AK8PUPPI_TightLeptonVeto"
    elif jet_type == "AK4":
        name_tight = "AK4PUPPI_Tight"
        name_tightlv = "AK4PUPPI_TightLeptonVeto"

    flat_j = ak.flatten(jets)

    def get_jetid(j, nj, ev_str):
 
        eta    = ak_clip(j.eta, -4.7, 4.7)
        chHEF  = ak_clip(j.chHEF, 0., 1.)
        neHEF  = ak_clip(j.neHEF, 0., 1.)
        chEmEF = ak_clip(j.chEmEF, 0., 1.)
        neEmEF = ak_clip(j.neEmEF, 0., 1.)
        muEF   = ak_clip(j.muEF, 0., 1.)
        chMult = ak_clip(j.chMultiplicity, 0., 100.)
        neMult = ak_clip(j.neMultiplicity, 0., 100.)
        nConst = chMult + neMult

        jetid = evaluator[ev_str].evaluate(eta, chHEF, neHEF, chEmEF, neEmEF, muEF, chMult, neMult, nConst)
        return ak.unflatten(jetid, nj)

    jets["jetidtight"] = ak.values_astype(get_jetid(flat_j, ak.num(jets), name_tight), bool)
    jets["jetidtightlepveto"] = ak.values_astype(get_jetid(flat_j, ak.num(jets), name_tightlv), bool)

    return jets

jec_name_map = {
    "JetPt": "pt",
    "JetMass": "mass",
    "JetEta": "eta",
    "JetA": "area",
    "ptGenJet": "pt_gen",
    "ptRaw": "pt_raw",
    "massRaw": "mass_raw",
    "Rho": "event_rho",
    "METpt": "pt",
    "METphi": "phi",
    "JetPhi": "phi",
    "UnClusteredEnergyDeltaX": "MetUnclustEnUpDeltaX",
    "UnClusteredEnergyDeltaY": "MetUnclustEnUpDeltaY",
}

def apply_jerc(jets, jet_type: str, year: str, runkey: str):

    jerc_path =f"{package_path}/hbb/data/jerc"
    jec_path = f"{jerc_path}/{jec_eras[runkey]}"

    if jet_type == "AK8":
        jet_key = fatjet_jerc_keys[year]
    elif jet_type == "AK4":
        jet_key = jet_jerc_keys[year]

    #build filelist
    files = []
    if "mc" in runkey:
        jer_path = f"{jerc_path}/{jer_eras[runkey]}"
        for jec, ps in jec_mc.items():
            files.append(f"{jec_path}/{jec_eras[runkey]}_{jec}_{jet_key}{ps}")
        for jer, ps in jer_mc.items():
            files.append(f"{jer_path}/{jer_eras[runkey]}_{jer}_{jet_key}{ps}")
    else:
        for jec, ps in jec_data.items():
            files.append(f"{jec_path}/{jec_eras[runkey]}_{jec}_{jet_key}{ps}")

    ext = extractor()
    with contextlib.ExitStack() as stack:
        real_files = [stack.enter_context(Path(f)) for f in files]
        ext.add_weight_sets([f"* * {file}" for file in real_files])
        ext.finalize()

    jec_stack = JECStack(ext.make_evaluator())
    jet_factory = CorrectedJetsFactory(jec_name_map, jec_stack)

    corrected_jets = jet_factory.build(jets)
    return corrected_jets

def correct_met(met, jets):

    dX_up = met.ptUnclusteredUp * np.cos(met.phiUnclusteredUp)
    dY_up = met.ptUnclusteredUp * np.sin(met.phiUnclusteredUp)
    dX_nom = met.pt * np.cos(met.phi)
    dY_nom = met.pt * np.sin(met.phi)
    met["MetUnclustEnUpDeltaX"] = dX_up - dX_nom
    met["MetUnclustEnUpDeltaY"] = dY_up - dY_nom

    met_factory = CorrectedMETFactory(jec_name_map)
    corrected_met = met_factory.build(met, jets)

    return corrected_met

def add_btag_weights(weights, jets, btagger, wp, year, dataset):
    if "PNet" in btagger:
        sys_name = "particleNet"
    elif "RobustParT" in btagger:
        sys_name = "robustParticleTransformer"
    elif "DeepFlav" in btagger:
        sys_name = "deepJet"

    cset = correctionlib.CorrectionSet.from_file(get_pog_json("btagging", year))
    btag_cut = b_taggers[year]["AK4"][btagger][wp]

    eff_file = f"{package_path}/hbb/data/btag/mc_eff_{btagger}_{year}.pkl"
    with open(eff_file, 'rb') as f:
        lookup_dict = pickle.load(f)

    def eff_lookup(x, y, z): return lookup_dict[dataset](x, y, z)

    jets_l = jets[(jets.hadronFlavour == 0) & (abs(jets.eta)<2.5)]
    jets_b = jets[(jets.hadronFlavour == 4) & (abs(jets.eta)<2.5)]
    jets_c = jets[(jets.hadronFlavour == 5) & (abs(jets.eta)<2.5)]

    pass_l = getattr(jets_l, btagger) > btag_cut
    pass_b = getattr(jets_b, btagger) > btag_cut
    pass_c = getattr(jets_c, btagger) > btag_cut

    eff_l = eff_lookup(jets_l.hadronFlavour, jets_l.pt, abs(jets_l.eta))
    eff_b = eff_lookup(jets_b.hadronFlavour, jets_b.pt, abs(jets_b.eta))
    eff_c = eff_lookup(jets_c.hadronFlavour, jets_c.pt, abs(jets_c.eta))

    def calc_weight(eff, sf, pass_tag):
        tagged = ak.prod(sf, axis=-1)
        untagged = ak.prod(((1 - sf*eff) / (1 - eff))[~pass_tag], axis=-1)
        return ak.fill_none(tagged * untagged, 1.)
    
    def get_sf(jets, j_flav, syst):
        j, nj = ak.flatten(jets), ak.num(jets)
        sf = cset[f"{sys_name}_{j_flav}"].evaluate(syst, wp, j.hadronFlavour, abs(j.eta), j.pt)
        return ak.unflatten(sf, nj)

    weight_l = calc_weight( eff_l, get_sf(jets_l, "light", "central"), pass_l )
    weight_b = calc_weight( eff_b, get_sf(jets_b, "comb", "central"), pass_b )
    weight_c = calc_weight( eff_c, get_sf(jets_c, "comb", "central"), pass_c )

    weights.add('btagLightSF', weight_l)
    weights.add('btagBSF', weight_b)
    weights.add('btagCSF', weight_c)
    
    nominal = weight_l * weight_b * weight_c

    weights.add(
        f"btagSFlight_{year}",
        ak.ones_like(nominal),
        weightUp=calc_weight(eff_l, get_sf(jets_l, "light", "up"), pass_l),
        weightDown=calc_weight(eff_l, get_sf(jets_l, "light", "down"), pass_l),
    )
    weights.add(
        f"btagSFb_{year}",
        ak.ones_like(nominal),
        weightUp=calc_weight(eff_b, get_sf(jets_b, "comb", "up"), pass_b),
        weightDown=calc_weight(eff_b, get_sf(jets_b, "comb", "down"), pass_b),
    )
    weights.add(
        f"btagSFc_{year}",
        ak.ones_like(nominal),
        weightUp=calc_weight(eff_c, get_sf(jets_c, "comb", "up"), pass_c),
        weightDown=calc_weight(eff_c, get_sf(jets_c, "comb", "down"), pass_c),
    )
    weights.add(
        'btagSFlight_correlated', 
        ak.ones_like(nominal),
        weightUp=calc_weight(eff_l, get_sf(jets_l, "light", "up_correlated"), pass_l),
        weightDown=calc_weight(eff_l, get_sf(jets_l, "light", "down_correlated"), pass_l),
    )
    weights.add(
        'btagSFb_correlated', 
        ak.ones_like(nominal),
        weightUp=calc_weight(eff_b, get_sf(jets_b, "comb", "up_correlated"), pass_b),
        weightDown=calc_weight(eff_b, get_sf(jets_b, "comb", "down_correlated"), pass_b),
    )
    weights.add(
        'btagSFc_correlated', 
        ak.ones_like(nominal),
        weightUp=calc_weight(eff_c, get_sf(jets_c, "comb", "up_correlated"), pass_c),
        weightDown=calc_weight(eff_c, get_sf(jets_c, "comb", "down_correlated"), pass_c),
    )
    return nominal