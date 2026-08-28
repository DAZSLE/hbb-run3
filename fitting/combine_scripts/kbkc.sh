 #!/bin/bash

# If build isn't working, see if the "latest" CMSSW path has updated
# /cvmfs/unpacked.cern.ch/gitlab-registry.cern.ch/cms-analysis/general/combine-container:latest/home/cmsusr/CMSSW_16_0_0/
# export CMSSW_BASE='/cvmfs/unpacked.cern.ch/gitlab-registry.cern.ch/cms-analysis/general/combine-container:latest/home/cmsusr/CMSSW_16_0_0'
# export COMBINE_SRC="/cvmfs/unpacked.cern.ch/gitlab-registry.cern.ch/cms-analysis/general/combine-container:latest/home/cmsusr/CMSSW_16_0_0/src/HiggsAnalysis/CombinedLimit"


# combineCards.py ptbin0ggfpassbb2024=ptbin0ggfpassbb2024.txt ptbin0ggfpasscc2024=ptbin0ggfpasscc2024.txt ptbin0ggffail2024=ptbin0ggffail2024.txt ptbin0vbfpassbb2024=ptbin0vbfpassbb2024.txt ptbin0vbfpasscc2024=ptbin0vbfpasscc2024.txt ptbin0vbffail2024=ptbin0vbffail2024.txt ptbin0vhpassbb2024=ptbin0vhpassbb2024.txt ptbin0vhpasscc2024=ptbin0vhpasscc2024.txt ptbin0vhfail2024=ptbin0vhfail2024.txt muonCRpassbb2024=muonCRpassbb2024.txt muonCRpasscc2024=muonCRpasscc2024.txt muonCRfail2024=muonCRfail2024.txt  > model_combined.txt
# text2workspace.py -P hbb.KappaBC:KBC --PO verbose --PO modes=ggH,qqH,VH --PO allowNegativeCouplings -m 125 model_combined.txt -o workspace.root
# echo 'Workspace created: workspace.root'


combine -M MultiDimFit workspace.root --algo grid --points=200 --setParameters kappa_b=1,kappa_W=1,kappa_Z=1,kappa_tau=1,kappa_t=1,kappa_g=1,kappa_gam=1 --freezeParameters kappa_b,kappa_W,kappa_Z,kappa_tau,kappa_t,kappa_g,kappa_gam --redefineSignalPOIs kappa_c --setParameterRanges kappa_c=-40,40 -n .KHc -t -1

plot1DScan.py higgsCombine.KHc.MultiDimFit.mH120.root --POI kappa_c --y-max 5 --y-cut 5


combine -M MultiDimFit workspace.root --algo grid --points=200 --setParameters kappa_c=1,kappa_W=1,kappa_Z=1,kappa_tau=1,kappa_t=1,kappa_g=1,kappa_gam=1 --freezeParameters kappa_c,kappa_W,kappa_Z,kappa_tau,kappa_t,kappa_g,kappa_gam --redefineSignalPOIs kappa_b --setParameterRanges kappa_b=-10,10 -n .KHb -t -1

plot1DScan.py higgsCombine.KHb.MultiDimFit.mH120.root --POI kappa_b --y-max 5 --y-cut 5


# combineTool.py -M MultiDimFit --mass 125 -n .ZH.kb_kc --algo grid --points 100 --split-points 1000 -d workspace.root --setParameters kappa_b=1,kappa_c=1,kappa_W=1,kappa_Z=1,kappa_tau=1,kappa_t=1,kappa_g=1,kappa_gam=1 --freezeParameters kappa_W,kappa_Z,kappa_tau,kappa_t,kappa_g,kappa_gam --setParameterRanges kappa_b=-8,8:kappa_c=-10,10 -P kappa_b -P kappa_c -t -1 --job-mode condor --sub-opts='+JobFlavour="workday"' &


combine -M MultiDimFit --mass 125 -n .ZH.kb_kc --algo grid --points 1000  -d workspace.root --setParameters kappa_b=1,kappa_c=1,kappa_W=1,kappa_Z=1,kappa_tau=1,kappa_t=1,kappa_g=1,kappa_gam=1 --freezeParameters kappa_W,kappa_Z,kappa_tau,kappa_t,kappa_g,kappa_gam --setParameterRanges kappa_b=-8,8:kappa_c=-10,10 -P kappa_b -P kappa_c -t -1 
