combine -M Significance -m 125 -t -1 --signif workspace.root --redefineSignalPOI rVBF_bb  --setParameters rVBF_bb=1,rggF_bb=1,rVH_bb=1,rVBF_cc=1,rggF_cc=1,rVH_cc=1 --freezeParameters rggF_bb,rVH_bb,rVBF_cc,rggF_cc,rVH_cc &> expsig_vbf_bb.txt
combine -M Significance -m 125 -t -1 --signif workspace.root --redefineSignalPOI rVH_bb  --setParameters rVBF_bb=1,rggF_bb=1,rVH_bb=1,rVBF_cc=1,rggF_cc=1,rVH_cc=1 --freezeParameters rggF_bb,rVBF_bb,rVBF_cc,rggF_cc,rVH_cc &> expsig_vh_bb.txt
combine -M Significance -m 125 -t -1 --signif workspace.root --redefineSignalPOI rggF_bb  --setParameters rVBF_bb=1,rggF_bb=1,rVH_bb=1,rVBF_cc=1,rggF_cc=1,rVH_cc=1 --freezeParameters rVBF_bb,rVH_bb,rVBF_cc,rggF_cc,rVH_cc &> expsig_ggf_bb.txt

combine -M Significance -m 125 -t -1 --signif workspace.root --redefineSignalPOI rVBF_cc  --setParameters rVBF_bb=1,rggF_bb=1,rVH_bb=1,rVBF_cc=1,rggF_cc=1,rVH_cc=1 --freezeParameters rggF_cc,rVH_cc,rVBF_bb,rggF_bb,rVH_bb &> expsig_vbf_cc.txt
combine -M Significance -m 125 -t -1 --signif workspace.root --redefineSignalPOI rVH_cc  --setParameters rVBF_bb=1,rggF_bb=1,rVH_bb=1,rVBF_cc=1,rggF_cc=1,rVH_cc=1 --freezeParameters rggF_cc,rVBF_cc,rVBF_bb,rggF_bb,rVH_bb &> expsig_vh_cc.txt
combine -M Significance -m 125 -t -1 --signif workspace.root --redefineSignalPOI rggF_cc  --setParameters rVBF_bb=1,rggF_bb=1,rVH_bb=1,rVBF_cc=1,rggF_cc=1,rVH_cc=1 --freezeParameters rVBF_cc,rVH_cc,rVBF_bb,rggF_bb,rVH_bb &> expsig_ggf_cc.txt

combine -M MultiDimFit -m 125 -t -1 --algo singles -d workspace.root --setParameters rVBF_bb=1,rggF_bb=1,rVH_bb=1,rVBF_cc=1,rggF_cc=1,rVH_cc=1 --robustFit=1 --robustHesse=1 --cminDefaultMinimizerStrategy=0 &> mdfit.txt

combine -M FitDiagnostics -m 125 -t -1 workspace.root --setParameters rVBF_bb=1,rggF_bb=1,rVH_bb=1,rVBF_cc=1,rggF_cc=1,rVH_cc=1 --saveShapes --saveWithUncertainties --robustFit=1 --robustHesse=1 --cminDefaultMinimizerStrategy=0  &> fitdiag.txt
