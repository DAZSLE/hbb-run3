combine -M Significance -m 125 -t -1 --signif workspace_Run3.root --redefineSignalPOI rH  --setParameters rH=1  &> expsig_rH.txt

combine -M MultiDimFit -m 125 -t -1 --algo singles -d workspace_Run3.root --setParameters rH=1 --robustFit=1 --robustHesse=1 --cminDefaultMinimizerStrategy=0 &> mdfit_rH.txt

combine -M FitDiagnostics -m 125 -t -1 workspace_Run3.root --setParameters rH=1 --saveShapes --saveWithUncertainties --robustFit=1 --robustHesse=1 --cminDefaultMinimizerStrategy=0  &> fitdiag.txt
