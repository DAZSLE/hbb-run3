"""
Gen selection functions for skimmer.

Author(s): Raghav Kansal, Cristina Mantilla Suarez
"""

from __future__ import annotations

import awkward as ak
from coffea.nanoevents.methods.base import NanoEventsArray
from coffea.nanoevents.methods.nanoaod import FatJetArray

from ..utils import P4

d_PDGID = 1
u_PDGID = 2
s_PDGID = 3
c_PDGID = 4
b_PDGID = 5
g_PDGID = 21
TOP_PDGID = 6

ELE_PDGID = 11
vELE_PDGID = 12
MU_PDGID = 13
vMU_PDGID = 14
TAU_PDGID = 15
vTAU_PDGID = 16

G_PDGID = 22
Z_PDGID = 23
W_PDGID = 24
HIGGS_PDGID = 25

b_PDGIDS = [511, 521, 523]

GEN_FLAGS = ["fromHardProcess", "isLastCopy"]


def getBosons(genparticles):
    absid = abs(genparticles.pdgId)
    return genparticles[
        # no gluons
        (absid >= 22)
        & (absid <= 25)
        & genparticles.hasFlags(["fromHardProcess", "isLastCopy"])
    ]


def bosonFlavor(bosons):
    childid = abs(bosons.children.pdgId)
    genflavor = (
        ak.any(childid == 5, axis=-1) * 3
        + ak.any(childid == 4, axis=-1) * 2
        + ak.all(childid < 4, axis=-1) * 1
    )
    return ak.fill_none(genflavor, 0)


def gen_selection_Hbb(
    events: NanoEventsArray,
    fatjets: FatJetArray,
):
    """Gets H, bb, 4-vectors + Higgs children information"""

    # finding the two gen higgs
    higgs = events.GenPart[
        (abs(events.GenPart.pdgId) == HIGGS_PDGID) * events.GenPart.hasFlags(GEN_FLAGS)
    ]
    higgs_children = higgs.children

    GenHiggsVars = {f"GenH{key}": higgs[var] for (var, key) in P4.items()}
    GenHiggsVars["GenHChildren"] = abs(higgs_children.pdgId[:, :, 0])

    is_bb = abs(higgs_children.pdgId) == b_PDGID
    bs = ak.flatten(higgs_children[is_bb], axis=2)
    GenbVars = {f"Genb{key}": bs[var] for (var, key) in P4.items()}

    # match fatjets to bb
    b_h1 = ak.firsts(higgs_children[is_bb][:, 0:1])  # first b quark
    b_h2 = ak.firsts(higgs_children[is_bb][:, 1:2])  # second b quark
    matched_to_higgs = (
        fatjets.metric_table(higgs) < 0.8
    )  # metric_table returns the deltaR between the fatjet and the higgs

    # boolean array that checks if the fatjet is matched to the Higgs
    fatjets["HiggsMatch"] = ak.any(matched_to_higgs, axis=2)
    # index of the fatjet that is matched to the Higgs
    fatjets["HiggsMatchIndex"] = ak.mask(
        ak.argmin(fatjets.metric_table(higgs), axis=2), fatjets["HiggsMatch"] == 1
    )
    # number of b quarks matched to the first b
    fatjets["NumBMatchedH1"] = ak.sum(fatjets.metric_table(b_h1) < 0.8, axis=2)
    # number of b quarks matched to the second b
    fatjets["NumBMatchedH2"] = ak.sum(fatjets.metric_table(b_h2) < 0.8, axis=2)

    return {**GenHiggsVars, **GenbVars}


def gen_selection_V(
    events: NanoEventsArray,
    fatjets: FatJetArray,
):
    """Get W/Z and children information"""
    vs = events.GenPart[
        ((abs(events.GenPart.pdgId) == W_PDGID) | (abs(events.GenPart.pdgId) == Z_PDGID))
        * events.GenPart.hasFlags(GEN_FLAGS)
    ]
    vs_flat = ak.firsts(vs)
    vs_children = vs.children
    vs_pdgId = abs(vs_children.pdgId)

    GenVVars = {f"GenV{key}": vs_flat[var] for (var, key) in P4.items()}
    GenVVars["GenVChildren"] = vs_pdgId

    vs_flat["is_bb"] = (vs_pdgId[:, :, 0] == b_PDGID) & (vs_pdgId[:, :, 1] == b_PDGID)
    vs_flat["is_cc"] = (vs_pdgId[:, :, 0] == c_PDGID) & (vs_pdgId[:, :, 1] == c_PDGID)
    vs_flat["is_cs"] = ((vs_pdgId[:, :, 0] == c_PDGID) & (vs_pdgId[:, :, 1] == s_PDGID)) | (
        (vs_pdgId[:, :, 0] == s_PDGID) & (vs_pdgId[:, :, 1] == c_PDGID)
    )

    GenVVars["GenVis_bb"] = vs_flat["is_bb"]
    GenVVars["GenVis_cc"] = vs_flat["is_cc"]
    GenVVars["GenVis_cs"] = vs_flat["is_cs"]

    # quarks of the first W/Z: W/Z -> qq
    q_v1 = vs_children[:, 0]
    delta_r = fatjets.metric_table(q_v1)
    matched_mask = delta_r < 0.8
    # number of quarks matched to the first W/Z
    fatjets["NumQMatchedV1"] = ak.sum(matched_mask, axis=2)

    # matched_to_v = (
    #    fatjets.metric_table(vs) < 0.8
    # )  # metric_table returns the deltaR between the fatjet and the W/Z
    # boolean array that checks if the fatjet is matched to the W/Z
    # is_fatjet_matched = ak.any(
    #    matched_to_v, axis=2
    # )  # checks if any of the fatjets is matched to the W/Z

    return {**GenVVars}


def gen_photon_reco(events: NanoEventsArray):
    """Leading post-shower hard-process photon (GenPart, fromHardProcess+isLastCopy).

    Kept for cross-checks and DY overlap-removal. This is NOT the stitching variable:
    it is smeared by the parton shower relative to the LHE-level photon the gridpack
    binning is actually applied on (see gen_photon_lhe).
    """
    gammas = events.GenPart[
        (abs(events.GenPart.pdgId) == G_PDGID) * events.GenPart.hasFlags(GEN_FLAGS)
    ]
    gammas = ak.firsts(gammas)
    return {f"GenGamma{key}": gammas[var] for (var, key) in P4.items()}


def gen_photon_lhe(events: NanoEventsArray):
    """Leading LHE-level photon pT — the AN-23-206 App. H stitching variable.

    The NLO photon-pT-binned V+gamma samples have their gridpack pT binning applied at
    LHE level, so LHEPart_pt of the photon is exactly the quantity the bin boundaries
    (100/200/400/600) are defined on. Stitching must cut on this, not the post-shower
    GenGammaPt (a proxy). Confirmed present in central 2024 v15 and private PFNano
    2022/2023 inputs (100% of events have a status-1 LHE photon). See AN-23-206 App. H/W.
    """
    photons = events.LHEPart[abs(events.LHEPart.pdgId) == G_PDGID]
    # leading (highest-pT) LHE photon; -1 sentinel for the (empirically absent) no-photon case
    return {"LHEGammaPt": ak.fill_none(ak.max(photons.pt, axis=1), -1.0)}


def gen_selection_Vg(
    events: NanoEventsArray,
    fatjets: FatJetArray,
):
    """Hadronic V+gamma (ZGto2QG, WGto2QG): V->qq reconstruction + gen & LHE photon."""
    GenVVars = gen_selection_V(events, fatjets)
    return {**GenVVars, **gen_photon_reco(events), **gen_photon_lhe(events)}


def gen_selection_Vg_leptonic(
    events: NanoEventsArray,
    fatjets: FatJetArray,
):
    """Leptonic V+gamma (DYGto2LG, WGtoLNuG): photon only.

    Skips the hadronic V->qq reconstruction of gen_selection_V (the V children are
    leptons/neutrinos here, not quarks), storing just the gen and LHE photon. The LHE
    photon pT (LHEGammaPt) is the stitching variable; GenGammaPt is kept for cross-checks
    and gen-level V+gamma overlap removal against plain DY.
    """
    return {**gen_photon_reco(events), **gen_photon_lhe(events)}
