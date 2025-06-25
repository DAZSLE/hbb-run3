from __future__ import annotations

import json
import logging
import time
from pathlib import Path

import awkward as ak
import dask
import dask_awkward as dak
import numpy as np
from coffea.analysis_tools import PackedSelection, Weights
from hist.dask import Hist

from hbb.corrections import (
    add_pileup_weight,
    get_jetveto_event,
    lumiMasks,
)
from hbb.processors.SkimmerABC import SkimmerABC

from .GenSelection import (
    bosonFlavor,
    gen_selection_Hbb,
    gen_selection_V,
    gen_selection_Vg,
    getBosons,
)
from .objects import (
    good_ak4jets,
    good_ak8jets,
    good_electrons,
    good_muons,
    good_photons,
    set_ak4jets,
    set_ak8jets,
)

logger = logging.getLogger(__name__)


def update(events, collections):
    """Return a shallow copy of events array with some collections swapped out"""
    out = events
    for name, value in collections.items():
        out = ak.with_field(out, value, name)
    return out


# mapping samples to the appropriate function for doing gen-level selections
gen_selection_dict = {
    "Hto2B": gen_selection_Hbb,
    "Wto2Q-": gen_selection_V,
    "Zto2Q-": gen_selection_V,
    "ZGto2QG-": gen_selection_Vg,
}


class categorizer(SkimmerABC):
    def __init__(
        self,
        year="2022",
        xsecs: dict = None,
        systematics=False,
        save_skim=False,
        skim_outpath="",
    ):
        super().__init__()

        self.XSECS = xsecs if xsecs is not None else {}  # in pb

        self._year = year
        self._systematics = systematics
        self._ak4tagBranch = "btagDeepFlavB"
        self._save_skim = save_skim
        self._skim_outpath = skim_outpath

        with Path("src/hbb/muon_triggers.json").open() as f:
            self._muontriggers = json.load(f)

        with Path("src/hbb/egamma_triggers.json").open() as f:
            self._egammatriggers = json.load(f)

        with Path("src/hbb/triggers.json").open() as f:
            self._triggers = json.load(f)

        # https://twiki.cern.ch/twiki/bin/view/CMS/MissingETOptionalFiltersRun2
        with Path("src/hbb/metfilters.json").open() as f:
            self._met_filters = json.load(f)

        with Path("src/hbb/taggers.json").open() as f:
            self._b_taggers = json.load(f)

        self.make_output = lambda: {
            "sumw": {},
            "cutflow": Hist.new.StrCat([], growth=True, name="region", label="Region")
            .StrCat([], growth=True, name="dataset", label="Dataset")
            .Reg(15, 0, 15, name="cut", label="Cut index")
            .Variable([0, 1, 2, 3, 4], name="genflavor", label="Gen. jet flavor"),
            "btagWeight": Hist.new.Reg(50, 0, 3, name="val", label="BTag correction").Weight(),
            "templates": Hist.new.StrCat([], growth=True, name="dataset", label="Dataset")
            .StrCat([], growth=True, name="region", label="Region")
            .StrCat([], growth=True, name="systematic", label="Systematic")
            .Variable([0, 1, 3, 4], name="genflavor", label="Gen. jet flavor")
            .Variable(
                [300, 400, 450, 500, 550, 600, 675, 800, 1200],
                name="pt1",
                label="Jet $p_{T}$ [GeV]",
            )
            .Reg(23, 40, 201, name="msd1", label="Jet $m_{sd}$")
            .Variable([0, 0.4, 0.5, 0.64, 1], name="bvl1", label="Jet bvl score")
            .Variable([1000, 2000, 13000], name="mjj", label="$m_{jj}$ [GeV]")
            .Weight(),
            "skim": {},
        }

    def process(self, events):
        # fatjets = events.FatJet
        # jets = events.Jet
        # met = events.MET
        # shifts = [({"Jet": jets, "FatJet": fatjets, "MET": met}, None)]
        # TODO return processor.accumulate(self.process_shift(update(events, collections), name) for collections, name in shifts)
        return self.process_shift(events, None)

    def add_weights(
        self,
        weights,
        events,
        dataset,
    ) -> tuple[dict, dict]:
        """Adds weights and variations, saves totals for all norm preserving weights and variations"""
        weights.add("genweight", events.genWeight)

        add_pileup_weight(weights, self._year, events.Pileup.nPU)

        logger.debug("weights", extra=weights._weights.keys())
        # logger.debug(f"Weight statistics: {weights.weightStatistics!r}")

        # dictionary of all weights and variations
        weights_dict = {}
        # dictionary of total # events for norm preserving variations for normalization in postprocessing
        totals_dict = {}

        # nominal
        weights_dict["weight"] = weights.weight()

        # systematics
        for systematic in weights.variations:
            weights_dict[systematic] = weights.weight(modifier=systematic)

        ###################### Normalization (Step 1) ######################
        # strip the year from the dataset name
        dataset_no_year = dataset.replace(f"{self._year}_", "")
        weight_norm = self.get_dataset_norm(self._year, dataset_no_year)
        # normalize all the weights to xsec, needs to be divided by totals in Step 2 in post-processing
        for key, val in weights_dict.items():
            weights_dict[key] = val * weight_norm

        # save the unnormalized weight, to confirm that it's been normalized in post-processing
        weights_dict["weight_noxsec"] = weights.weight()

        return weights_dict, totals_dict

    def process_shift(self, events, shift_name):

        dataset = events.metadata["dataset"]
        isRealData = not hasattr(events, "genWeight")
        selection = PackedSelection()
        output = self.make_output()
        weights = Weights(None, storeIndividual=True)
        if shift_name is None and not isRealData:
            output["sumw"][dataset] = ak.sum(events.genWeight)

        trigger = ak.values_astype(ak.zeros_like(events.run), bool)
        for t in self._triggers[self._year]:
            if t in events.HLT.fields:
                trigger = trigger | events.HLT[t]
        selection.add("trigger", trigger)
        del trigger

        if isRealData:
            selection.add("lumimask", lumiMasks[self._year[:4]](events.run, events.luminosityBlock))
        else:
            selection.add("lumimask", ak.values_astype(ak.ones_like(events.run), bool))

        trigger = ak.values_astype(ak.zeros_like(events.run), bool)
        for t in self._muontriggers[self._year]:
            if t in events.HLT.fields:
                trigger = trigger | events.HLT[t]
        selection.add("muontrigger", trigger)
        del trigger

        trigger = ak.values_astype(ak.zeros_like(events.run), bool)
        for t in self._egammatriggers[self._year]:
            if t in events.HLT.fields:
                trigger = trigger | events.HLT[t]
        selection.add("egammatrigger", trigger)
        del trigger

        metfilter = ak.values_astype(ak.ones_like(events.run), bool)
        for flag in self._met_filters[self._year]["data" if isRealData else "mc"]:
            if flag in events.Flag.fields:
                metfilter = dask.array.bitwise_and(metfilter, events.Flag[flag])
        selection.add("metfilter", metfilter)
        del metfilter

        fatjets = set_ak8jets(events.FatJet)
        goodfatjets = good_ak8jets(fatjets)
        goodjets = good_ak4jets(set_ak4jets(events.Jet))

        cut_jetveto = get_jetveto_event(goodjets, self._year)
        selection.add("ak4jetveto", cut_jetveto)

        selection.add("2FJ", ak.num(goodfatjets, axis=1) == 2)
        selection.add("not2FJ", ak.num(goodfatjets, axis=1) != 2)

        candidatejet = ak.firsts(
            goodfatjets[ak.argmax(goodfatjets.particleNet_XbbVsQCD, axis=1, keepdims=True)]
        )

        selection.add(
            "minjetkin",
            (candidatejet.pt >= 300)
            & (candidatejet.pt < 1200)
            & (candidatejet.msd >= 40.0)
            & (candidatejet.msd < 201.0)
            & (abs(candidatejet.eta) < 2.5),
        )

        bvl = candidatejet.particleNet_XbbVsQCD
        selection.add("bvlpass", (bvl >= 0.5))

        # only consider first 4 jets to be consistent with old framework
        jets = goodjets[:, :4]
        dphi = abs(jets.delta_phi(candidatejet))
        btag_cut = self._b_taggers[self._year]["AK4"]["Jet_btagPNetB"]["M"]
        selection.add(
            "antiak4btagMediumOppHem",
            ak.max(jets[dphi > np.pi / 2].btagPNetB, axis=1, mask_identity=False) < btag_cut,
        )
        ak4_away = jets[dphi > 0.8]
        selection.add(
            "ak4btagMedium08", ak.max(ak4_away.btagPNetB, axis=1, mask_identity=False) > btag_cut
        )

        met = events.MET
        selection.add("met", met.pt < 140.0)

        # VBF specific variables
        dR = jets.delta_r(candidatejet)
        ak4_outside_ak8 = jets[dR > 0.8]

        jet1 = ak4_outside_ak8[:, 0:1]
        jet2 = ak4_outside_ak8[:, 1:2]

        vbf_deta = abs(ak.firsts(jet1).eta - ak.firsts(jet2).eta)
        vbf_mjj = (ak.firsts(jet1) + ak.firsts(jet2)).mass

        isvbf = (vbf_deta > 3.5) & (vbf_mjj > 1000)
        isvbf = ak.fill_none(isvbf, False)
        selection.add("isvbf", isvbf)

        isnotvbf = ak.fill_none(~isvbf, True)
        selection.add("notvbf", isnotvbf)

        goodmuon = good_muons(events.Muon)
        nmuons = ak.num(goodmuon, axis=1)
        leadingmuon = ak.firsts(goodmuon)

        goodelectron = good_electrons(events.Electron)
        nelectrons = ak.num(goodelectron, axis=1)

        selection.add("noleptons", (nmuons == 0) & (nelectrons == 0))
        selection.add("onemuon", (nmuons == 1) & (nelectrons == 0))
        selection.add("muonkin", (leadingmuon.pt > 55.0) & (abs(leadingmuon.eta) < 2.1))
        selection.add("muonDphiAK8", abs(leadingmuon.delta_phi(candidatejet)) > 2 * np.pi / 3)

        goodphotons = good_photons(events.Photon)
        nphotons = ak.num(goodphotons, axis=1)
        leadingphoton = ak.firsts(goodphotons)

        selection.add("onephoton", (nphotons == 1))
        selection.add("passphotonveto", (nphotons == 0))

        gen_variables = {}
        if isRealData:
            genflavor = ak.zeros_like(candidatejet.pt)
            genBosonPt = ak.zeros_like(candidatejet.pt)
        else:
            weights_dict, totals_temp = self.add_weights(
                weights,
                events,
                dataset,
            )
            for d, gen_func in gen_selection_dict.items():
                if d in dataset:
                    # match fatjets_xbb
                    gen_variables = gen_func(events, goodfatjets)

            bosons = getBosons(events.GenPart)
            matchedBoson = candidatejet.nearest(bosons, axis=None, threshold=0.8)
            match_mask = ((candidatejet.pt - matchedBoson.pt) / matchedBoson.pt < 0.5) & (
                (candidatejet.msd - matchedBoson.mass) / matchedBoson.mass < 0.3
            )
            selmatchedBoson = ak.mask(matchedBoson, match_mask)
            genflavor = bosonFlavor(selmatchedBoson)
            genBosonPt = ak.fill_none(ak.firsts(bosons.pt), 0)

        # softdrop mass, 0 for genflavor == 0
        msd_matched = candidatejet.msd * (genflavor > 0) + candidatejet.msd * (genflavor == 0)

        regions = {
            "signal-all": [
                "trigger",
                "lumimask",
                "metfilter",
                "minjetkin",
                "antiak4btagMediumOppHem",
                "met",
                "noleptons",
            ],
            # "signal-ggf": [
            #     "trigger",
            #     "lumimask",
            #     "metfilter",
            #     "minjetkin",
            #     "antiak4btagMediumOppHem",
            #     "met",
            #     "noleptons",
            #     "notvbf",
            #     "not2FJ",
            #     "bvlpass",
            # ],
            # "signal-vh": [
            #     "trigger",
            #     "lumimask",
            #     "metfilter",
            #     "minjetkin",
            #     "antiak4btagMediumOppHem",
            #     "met",
            #     "noleptons",
            #     "notvbf",
            #     "2FJ",
            #     "bvlpass",
            # ],
            # "signal-vbf": [
            #     "trigger",
            #     "lumimask",
            #     "metfilter",
            #     "minjetkin",
            #     "antiak4btagMediumOppHem",
            #     "met",
            #     "noleptons",
            #     "isvbf",
            #     "bvlpass",
            # ],
            # "control-tt": [
            #     "muontrigger",
            #     "lumimask",
            #     "metfilter",
            #     "minjetkin",
            #     "ak4btagMedium08",
            #     "onemuon",
            #     "muonkin",
            #     "muonDphiAK8",
            # ],
            # "control-zgamma": [
            #     "egammatrigger",
            #     "lumimask",
            #     "metfilter",
            #     "minjetkin",
            #     "ak4btagMedium08",
            #     "onephoton",
            #     "bvlpass",
            # ],
        }

        def normalize(val, cut):
            if cut is None:
                ar = ak.fill_none(val, np.nan)
                return ar
            else:
                ar = ak.fill_none(val[cut], np.nan)
                return ar

        tic = time.time()

        if shift_name is None:
            systematics = [None] + list(weights.variations)
        else:
            systematics = [shift_name]

        nominal_weight = ak.ones_like(candidatejet.pt) if isRealData else weights_dict["weight"]

        output_array = None
        if self._save_skim:
            # define "flat" output array
            output_array = ak.zip(
                {
                    "GenBoson_pt": genBosonPt,
                    "FatJet_pt": candidatejet.pt,
                    "FatJet_msd": msd_matched,
                    "FatJet_TXbb": candidatejet.particleNet_XbbVsQCD,
                    "FatJet_TXcc": candidatejet.particleNet_XccVsQCD,
                    "VBFJets_Mjj": vbf_mjj,
                    "VBFJets_DEta": vbf_deta,
                    "Photon_pt": leadingphoton.pt,
                    "weight": nominal_weight,
                    **gen_variables,
                },
                depth_limit=1,
            )

        def fill(region, systematic, wmod=None):
            selections = regions[region]
            cut = selection.all(*selections)
            sname = "nominal" if systematic is None else systematic

            if wmod is None:
                if systematic in weights.variations and not isRealData:
                    weight = weights_dict[systematic][cut]
                else:
                    weight = nominal_weight[cut]
            else:
                weight = nominal_weight[cut] * wmod[cut]

            output["templates"].fill(
                dataset=dataset,
                region=region,
                systematic=sname,
                genflavor=normalize(genflavor, cut),
                pt1=normalize(candidatejet.pt, cut),
                msd1=normalize(msd_matched, cut),
                bvl1=normalize(bvl, cut),
                mjj=normalize(vbf_mjj, cut),
                weight=weight,
            )

        def skim(region, output_array):
            selections = regions[region]
            cut = selection.all(*selections)

            # to debug...
            # print(output_array.compute())
            # print(output_array[cut].compute())

            if "root:" in self._skim_outpath:
                skim_path = f"{self._skim_outpath}/{self._year}/{dataset}/{region}"
            else:
                skim_path = Path(self._skim_outpath) / self._year / dataset / region
                skim_path.mkdir(parents=True, exist_ok=True)
            print("Saving skim to: ", skim_path)

            # possible TODO: add systematic weights?
            output["skim"][region] = dak.to_parquet(
                output_array[cut],
                str(skim_path),
                compute=False,
            )

        for region in regions:
            if self._save_skim:
                skim(region, output_array)
            for systematic in systematics:
                if isRealData and systematic is not None:
                    continue
                fill(region, systematic)

        toc = time.time()
        output["filltime"] = toc - tic
        if shift_name is None:
            output["weightStats"] = weights.weightStatistics
        return output

    def postprocess(self, accumulator):
        pass
