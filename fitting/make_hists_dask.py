#!/usr/bin/env python3
"""
Histogram Maker - Fully Configuration-Driven
Supports: VBF Hbb Analysis, ZGamma Validation Region

Author(s): Gabi Hamilton, Lara Zygala, Cristina Mantilla
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from datetime import datetime
import getpass
import os
import subprocess

# NOTE: dask.distributed / lpcjobqueue are imported lazily inside main() (only for
# the dask path) so that --serial can run in the plain hbb env (no dask installed),
# where the /eos/uscms FUSE mount IS visible (it is NOT inside the coffea-dask container).

from template_utils import (
    REGION_MAP,
    folder_systs,
    year_systs,
    get_pdf_list,
    get_scale_list,
    scalevar_process,
    Zjets_thsysts,
    Wjets_thsysts,
    eos_exists,
    fill_binned_histogram,
    _ptg_bin,
    jmsr_event_mode,
)

def set_xrootd_env():
    #set environment within condor node
    os.environ["XRD_STREAMTIMEOUT"] = "1200"
    os.environ["XRD_REQUESTTIMEOUT"] = "1200"
    os.environ["XRD_TIMEOUTRESOLUTION"] = "15"
    os.environ["XRD_CONNECTIONRETRY"] = "10"
    os.environ["XRD_CONNECTIONWINDOW"] = "1200"

def xrdcp_file(file, eos_path, redirector):
    #send files to eos area
    subprocess.run(["xrdfs", str(redirector), "mkdir", "-p", str(eos_path).replace("/eos/uscms","")])
    subprocess.run(["xrdcp", "-fr", str(file), f"{redirector}{eos_path}",])

def submit_task(process, dataset, data_dir, load_cols, region, region_key, variation, pq_filters, do_loadsys_sumw, scalevar_structure, setup, args, syst, template_outfile, plotting_outfile, eos_path):
    set_xrootd_env()

    import utils
    events = utils.load_samples(
        data_dir=data_dir,
        samples={process: [dataset]},
        columns=load_cols,
        region=region,
        variation=variation,
        filters=pq_filters,
        load_sys_sumweights=do_loadsys_sumw,
        scalevar_structure=scalevar_structure,
        # dask workers have no /eos/uscms FUSE mount -> xrdcp the parquets locally;
        # --serial runs in-process where the FUSE path is readable
        local_search_transfer=not getattr(args, "serial", False),
    )

    if events:
        fill_binned_histogram(
            events,
            region_key,
            setup,
            args,
            systs=syst,
            template_outfile_path=template_outfile,
            plotting_outfile_path=plotting_outfile,
            dataset=dataset,
        )

    redirector = "root://cmseos.fnal.gov/"
    template_eos_path = f"{eos_path}/FITTING_TEMPLATES/"
    plotting_eos_path = f"{eos_path}/PLOTTING_PICKLES/"
    if Path(str(template_outfile)+".dat").exists():
        xrdcp_file(f"{template_outfile}.dat", template_eos_path, redirector)
        xrdcp_file(f"{template_outfile}.bak", template_eos_path, redirector)
        xrdcp_file(f"{template_outfile}.dir", template_eos_path, redirector)
    if Path(str(plotting_outfile)+".dat").exists():
        xrdcp_file(f"{plotting_outfile}.dat", plotting_eos_path, redirector)
        xrdcp_file(f"{plotting_outfile}.bak", plotting_eos_path, redirector)
        xrdcp_file(f"{plotting_outfile}.dir", plotting_eos_path, redirector)
    
    return None

def main(args):
    with Path(args.setup).open() as f:
        setup = json.load(f)
    with Path("pmap_run3.json").open() as f:
        pmap = json.load(f)
        
    do_BDT_regions = setup.get("do_BDT_regions", False)
    obs_name = setup["observable"]["name"]  # e.g., "msd"

    tasks = []

    for region_key, reg_cfg in setup["categories"].items():
        print("\n" + "=" * 50)
        print(f"STARTING REGION: {region_key}")
        print("=" * 50)

        # Define columns to load
        cols = [
            "weight",
            "FatJet0_pt",
            "FatJet0_msd",
            "FatJet0_ParTPXbbVsQCD",
            "FatJet0_ParTPXccVsQCD",
            "FatJet0_ParTPXbbXcc",
            "GenFlavor"
        ]
        if setup.get("use_modified_disc", False):
            # Raw ParT probabilities needed to compute modified discriminant on-the-fly
            cols += [
                "FatJet0_ParTPXbb",
                "FatJet0_ParTPXcc",
                "FatJet0_ParTPQCD",
                "FatJet0_ParTPXcs",
            ]

        # Ensure the dynamic bin branch is loaded
        bin_branch = reg_cfg.get("bin_branch", "FatJet0_pt")
        if bin_branch not in cols:
            cols.append(bin_branch)

        obs_branch = setup["observable"]["branch_name"]
        if obs_branch not in cols:
            cols.append(obs_branch)

        # ------------------------------------------------------------------
        # Build loose PyArrow row filters from the setup config.
        # These are applied at read time (predicate pushdown) — rows that
        # fail are never loaded into RAM, which is critical for large MC
        # samples like GJets that have O(100M) events in the parquet.
        # Use slightly looser cuts than the analysis selection so we don't
        # accidentally lose events at bin edges.
        # ------------------------------------------------------------------
        pq_filters = [
            ("FatJet0_msd", ">=", float(setup["observable"]["min"])),
            ("FatJet0_msd", "<=", float(setup["observable"]["max"])),
            ("FatJet0_pt",  ">=", float(setup.get("pt_min_scale", 450.))),
            ("FatJet0_pt",  "<=", float(1200.)),
        ]

        # Determine Data Stream (e.g., EGammadata for zgamma)
        data_map_key = "Jetdata"
        if "zg" in region_key:
            data_map_key = "EGammadata"
            cols += [
                "Photon0_pt",
                "Photon0_phi",
                "FatJet0_phi",
                "MET",
                "Photon200",
                "Photon110EB_TightID_TightIso",
            ]
            # Photon0_pt > 120 is the analysis cut; pre-filter at 100 to
            # keep a small margin while cutting ~90% of low-pT GJets rows.
            pq_filters.append(("Photon0_pt", ">=", 100.0))
        elif "mu" in region_key:    #refactor for zmumu
            data_map_key = "Muondata"

        do_folder_systs = ["nominal"]
        col_systs = []
        if setup.get("do_systematics"):
            active_syst = setup.get("active_systematics", [])
            # JMS/JMR are not weight columns: morph mode builds them in make_datacards,
            # event mode (jmsr_mode "event") varies the mass in fill_binned_histogram
            col_systs = [f"{s}{var}" for s in active_syst if s not in folder_systs and s not in ["pdf_Higgs", "QCDScale", "VJets"] and s not in year_systs and not s.startswith(("JMS", "JMR")) for var in ("Up", "Down")]
            col_systs.extend([f"{s}_{args.year}{var}" for s in active_syst if s in year_systs for var in ("Up", "Down")])
            do_folder_systs = ["nominal"] + [f"{s}{var}" for s in active_syst if s in folder_systs for var in ("Up", "Down")]

        for variation in do_folder_systs:
            if args.debug:
                if not variation == "nominal":
                    continue
            print(f"\n>>> Running Energy Variation Systematic Pass: {variation}")

            for process, datasets in pmap.items():
                isRealData = "data" in process.lower()
                if isRealData and (process != data_map_key or variation != "nominal"):
                    continue

                col_systs_proc, syst_loop = [], []
                do_loadsys_sumw = False
                if setup.get("do_systematics") and not isRealData:
                    col_systs_proc, syst_loop = col_systs.copy(), col_systs.copy()
                    if jmsr_event_mode(setup):
                        syst_loop.extend([f"{s}{var}" for s in active_syst if s.startswith(("JMS", "JMR")) for var in ("Up", "Down")])
                    if process in scalevar_process:
                        do_loadsys_sumw = True
                        if "pdf_Higgs" in active_syst:
                            col_systs_proc.extend(get_pdf_list(103))
                            syst_loop.extend(["pdf_HiggsUp", "pdf_HiggsDown"])
                        if "QCDScale" in active_syst:
                            col_systs_proc.extend(get_scale_list(scalevar_process[process]))
                            syst_loop.extend([f"scalevar{scalevar_process[process]}Up", f"scalevar{scalevar_process[process]}Down"])

                    #Our submission files technically only run over vjets files (HadLO + LepNLO) that get corrected, so the pmap should be ok
                    if "VJets" in active_syst:
                        if process == "Zjets":
                            for zsyst in Zjets_thsysts:
                                col_systs_proc.extend([f"{zsyst}Up", f"{zsyst}Down"])
                                syst_loop.extend([f"{zsyst}Up", f"{zsyst}Down"])
                        elif process == "Wjets":
                            for wsyst in Wjets_thsysts:
                                col_systs_proc.extend([f"{wsyst}Up", f"{wsyst}Down"])
                                syst_loop.extend([f"{wsyst}Up", f"{wsyst}Down"])

                load_cols = cols
                if variation == "nominal" and not isRealData:
                    load_cols = cols+col_systs_proc

                all_systs = ["nominal"] + syst_loop if variation == "nominal" else [variation]

                for dataset in datasets:

                    # query skim directory so we only create tasks for year + dataset + variation combos that exist
                    data_dir = Path(args.data_dir) if args.data_dir else Path(
                        f"/eos/uscms/store/group/lpchbbrun3/skims/{args.tag}/{args.year}"
                    )
                    region = REGION_MAP[region_key] if not do_BDT_regions or "cr" in region_key else f"{REGION_MAP[region_key]}-BDT"
                    search_path = Path(data_dir / dataset /  "parquet" / variation / region)

                    # a dataset present in an overlay dir (e.g. a partial reskim) is read from there
                    from_overlay = False
                    for overlay in args.overlay_data_dir or []:
                        overlay_path = Path(overlay) / dataset / "parquet" / variation / region
                        if eos_exists(str(overlay_path).replace("/eos/uscms", "")):
                            data_dir, search_path = Path(overlay), overlay_path
                            from_overlay = True
                            break

                    if not eos_exists(str(search_path).replace("/eos/uscms", "")):
                        if args.debug:
                            print("DOESN'T EXIST: ", search_path)
                        continue

                    if args.debug:
                        if len(tasks) > 15:
                            break

                    template_db = f"fitting_{args.year}_{region}_{process}_{dataset}_{variation}_{obs_name}_shelved"
                    plotting_db = f"plotting_{args.year}_{region}_{process}_{dataset}_{variation}_{obs_name}_shelved"
                    tmp_eos_output = f"/store/group/lpchbbrun3/{getpass.getuser()}"
                    if args.debug:
                        print(template_db)

                    # AN-23-206 stitching of the photon-pT-binned V+γ samples needs the photon pT
                    # column. LHEGammaPt only exists in the LHE-photon reskim (read via
                    # --overlay-data-dir); older skims carry only the GenGammaPt proxy, and only
                    # for ZGto2QG. Load per-dataset so we never request a missing column.
                    ds_load_cols = load_cols
                    if setup.get("stitch_ptg", False) and _ptg_bin(dataset) is not None:
                        if from_overlay:
                            ds_load_cols = load_cols + ["LHEGammaPt"]
                        elif "ZGto2QG" in dataset:
                            ds_load_cols = load_cols + ["GenGammaPt"]

                    tasks.append({"process": process,
                                "dataset": dataset,
                                "data_dir": data_dir,
                                "load_cols" : ds_load_cols,
                                "region" : region, 
                                "region_key" : region_key, 
                                "variation" : variation, 
                                "pq_filters" : pq_filters, 
                                "do_loadsys_sumw" : do_loadsys_sumw, 
                                "scalevar_structure" : scalevar_process[process] if do_loadsys_sumw else "", 
                                "setup" : setup, 
                                "args" : args, 
                                "syst" : all_systs, 
                                "template_outfile" : template_db if args.save_templates else "",
                                "plotting_outfile" : plotting_db if args.save_plotting_pkl else "",
                                "eos_path" : tmp_eos_output
                                })

    print(f"|{datetime.now()}| Number of tasks to submit: {len(tasks)}")

    if getattr(args, "serial", False):
        # Run tasks in-process (container main), bypassing dask workers.
        # Use when the condor dask workers can't read EOS (tasks "succeed" but
        # load_samples returns empty -> no templates written). Slower but reliable.
        print(f"|{datetime.now()}| SERIAL mode (no dask) — running {len(tasks)} tasks in-process")
        # submit_task does a bare `import utils`; in the dask path utils.py is shipped
        # to the worker cwd via transfer_input_files. In-process we must put src/hbb on
        # the path so that bare import resolves to src/hbb/utils.py.
        import sys
        _hbb_dir = str(Path(__file__).resolve().parent.parent / "src" / "hbb")
        if _hbb_dir not in sys.path:
            sys.path.insert(0, _hbb_dir)
        n_done = n_failed = 0
        for task in tasks:
            try:
                submit_task(**task)
                n_done += 1
            except Exception as exc:
                n_failed += 1
                print(f"Task FAILED: {task.get('dataset')} -> {exc!r}")
            if (n_done + n_failed) % 10 == 0:
                print(f"|{datetime.now()}| {n_done + n_failed}/{len(tasks)} (ok={n_done} fail={n_failed})")
        print(f"|{datetime.now()}| SERIAL done: {n_done} ok, {n_failed} failed")
        print(f"|{datetime.now()}| Next: python collect_hists.py --year {args.year} --tag {args.tag} --outdir {args.outdir} --save-templates")
        return

    from dask.distributed import Client, as_completed
    from lpcjobqueue import LPCCondorCluster
    cluster = LPCCondorCluster(
         transfer_input_files=[
             "../.env", 
             "../src/hbb/utils.py",
             "template_utils.py"
             ],
        log_directory=f"/uscmst1b_scratch/lpc1/3DayLifetime/{os.environ['USER']}",
        memory="14GB",  # Necessary for some 2024 QCD datasets, can get away with smaller for other years
        # job_script_prologue=[]
    )
    if args.debug:
        print(cluster.job_script())

    cluster.adapt(minimum=50, maximum=100)

    print(f"|{datetime.now()}| Opening Client")

    with Client(cluster, timeout="120s", heartbeat_interval="20s") as client:
        print(f"|{datetime.now()}| Waiting For Workers")
        client.wait_for_workers(1)

        print(f"|{datetime.now()}| Submitting Tasks Now")
        futures = [
            client.submit(submit_task, **task, pure=False)
            for task in tasks
        ] 
        future_to_task = dict(zip(futures, tasks))

        n_done = 0
        n_failed = 0

        for future in as_completed(futures):
            try:
                future.result()
                n_done += 1
            except Exception as exc:
                n_failed += 1
                task = future_to_task[future]
                print(f"\nTask failed:")
                print(f"Task: {task['template_outfile']}")
                print(f"Exception: {exc!r}\n")

            if (n_done + n_failed) % 100 == 0:
                print(f"|{datetime.now()}| Finished {n_done + n_failed}/{len(futures)}")

        print(f"|{datetime.now()}| All Tasks Completed, Closing Client")
        client.close()
    
    cluster.close()
    print(f"|{datetime.now()}| Cluster and Client Closed")

    print(f"|{datetime.now()}| Finished, Exit Singularity and Run the Following to Collect Histograms:")
    out_cmd = [
        "python collect_hists.py",
        f"--year {args.year}",
        {f'--tag {args.tag}' if args.tag else ''},
    ]
    print(f"python collect_hists.py --year {args.year} {f'--tag {args.tag}' if args.tag else ''} {f'--outdir {args.outdir}' if args.outdir else ''} {'--save-templates' if args.save_templates else ''} {'--save-plotting-pkl' if args.save_plotting_pkl else ''}") 
    
    print(f"\n\nClean Your EOS Directories If You Would Like To Run Again")

if __name__ == "__main__":
    tick = datetime.now()
    parser = argparse.ArgumentParser(description="Unified Histogram Maker for Signal and CR")
    parser.add_argument("--year", required=True, choices=["2022", "2022EE", "2023", "2023BPix", "2024"])
    parser.add_argument("--tag", default=None, help="Tag for the skims directory (e.g., 26Feb03). Required if --data-dir is not provided.")
    parser.add_argument("--setup", required=True, help="Path to setup.json file")
    parser.add_argument("--outdir", default="results", help="Directory to save ROOT files")
    parser.add_argument("--save-templates", action="store_true", help="Actually write the ROOT file")
    parser.add_argument("--save-plotting-pkl", action="store_true", help="Actually write the PKL file")
    parser.add_argument("--debug", action="store_true", help="Enter debug mode")
    parser.add_argument("--serial", action="store_true",
                        help="Run tasks in-process (no dask workers). Use when condor "
                             "dask workers can't read EOS. Slower but reliable.")
    parser.add_argument(
        "--data-dir", default=None,
        help="Override the full path to the parquet directory for this year, "
             "e.g. /eos/uscms/store/group/lpchbbrun3/gmachado/Test_v15/2024 "
             "Skips the --tag-based path construction.",
    )
    parser.add_argument(
        "--overlay-data-dir", action="append", default=None,
        help="Parquet directory whose datasets take precedence over --data-dir/--tag "
             "(repeatable, first match wins), e.g. a partial reskim such as "
             "/eos/uscms/store/group/lpchbbrun3/gmachado/26Sep17_lhephoton_v15/2024",
    )

    args = parser.parse_args()

    if args.tag is None and args.data_dir is None:
        parser.error("--tag is required when --data-dir is not provided.")

    main(args)

    print("Total Processing Time: ", datetime.now() - tick )