combine -M AsymptoticLimits -m 125 -t -1 workspace_Run3.root --redefineSignalPOI rH_cc --setParameters rH_bb=1,rH_cc=1   --freezeParameters rH_bb --expectSignal 1 -n .rHcc_exp &> limit_rHcc.txt
combine -M MultiDimFit -m 125 -t -1 workspace_Run3.root --redefineSignalPOI rH_cc -P rH_cc --setParameters rH_bb=1,rH_cc=1 --freezeParameters rH_bb --algo grid --points 200 --expectSignal 1 -n .rHcc_scan &> mdfit_rHcc_scan.txt

combine -M AsymptoticLimits -m 125 -t -1 workspace_Run3.root --redefineSignalPOI rVBF_cc --setParameters rH_bb=1,rVBF_cc=1,rggF_cc=1,rVH_cc=1  --freezeParameters rH_bb,rggF_cc,rVH_cc --expectSignal 1 -n .rVBFcc_exp &> limit_rVBFcc.txt
combine -M AsymptoticLimits -m 125 -t -1 workspace_Run3.root --redefineSignalPOI rggF_cc --setParameters rH_bb=1,rVBF_cc=1,rggF_cc=1,rVH_cc=1  --freezeParameters rH_bb,rVBF_cc,rVH_cc --expectSignal 1 -n .rggFcc_exp &> limit_rggFcc.txt
combine -M AsymptoticLimits -m 125 -t -1 workspace_Run3.root --redefineSignalPOI rVH_cc --setParameters rH_bb=1,rVBF_cc=1,rggF_cc=1,rVH_cc=1  --freezeParameters rH_bb,rggF_cc,rVBF_cc --expectSignal 1 -n .rVHcc_exp &> limit_rVHcc.txt
