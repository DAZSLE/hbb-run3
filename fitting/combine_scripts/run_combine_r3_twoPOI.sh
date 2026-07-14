combine -M Significance -m 125 -t -1 --signif workspace_Run3.root --redefineSignalPOI rH_bb  --setParameters rH_bb=1,rH_cc=1  --freezeParameters rH_cc &> expsig_rH_bb.txt
combine -M Significance -m 125 -t -1 --signif workspace_Run3.root --redefineSignalPOI rH_cc  --setParameters rH_bb=1,rH_cc=1  --freezeParameters rH_bb &> expsig_rH_cc.txt

combine -M MultiDimFit -m 125 -t -1 --algo singles -d workspace_Run3.root --setParameters rH_bb=1,rH_cc=1 --robustFit=1 --robustHesse=1 --cminDefaultMinimizerStrategy=0 &> mdfit_rH_bb_cc.txt

combine -M FitDiagnostics -m 125 -t -1 workspace_Run3.root --setParameters rH_bb=1,rH_cc=1 --saveShapes --saveWithUncertainties --robustFit=1 --robustHesse=1 --cminDefaultMinimizerStrategy=0  &> fitdiag.txt

