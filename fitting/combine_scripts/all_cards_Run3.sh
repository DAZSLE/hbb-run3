combineCards.py \
    y22=2022/datacards/srModel_2022/model_combined.txt \
    y22EE=2022EE/datacards/srModel_2022EE/model_combined.txt \
    y23=2023/datacards/srModel_2023/model_combined.txt \
    y23BPix=2023BPix/datacards/srModel_2023BPix/model_combined.txt \
    y24=2024/datacards/srModel_2024/model_combined.txt \
    > full_Run3_srModel.txt

cp 202*/datacards/srModel_*/*_202*.root .


# ONE POI : rH
# text2workspace.py -P HiggsAnalysis.CombinedLimit.PhysicsModel:multiSignalModel --PO verbose \
#     --PO 'map=.*/ggFbb:rH[1,-20,20]' \
#     --PO 'map=.*/ggFcc:rH[1,-20,20]' \
#     --PO 'map=.*/VBFbb:rH[1,-20,20]' \
#     --PO 'map=.*/VBFcc:rH[1,-20,20]' \
#     --PO 'map=.*/WHbb:rH[1,-20,20]' \
#     --PO 'map=.*/WHcc:rH[1,-20,20]' \
#     --PO 'map=.*/ZHbb:rH[1,-20,20]' \
#     --PO 'map=.*/ZHcc:rH[1,-20,20]'  \
#     full_Run3_srModel.txt -o workspace_Run3.root

# TWO POI : rH_bb , rH_cc
# text2workspace.py -P HiggsAnalysis.CombinedLimit.PhysicsModel:multiSignalModel --PO verbose \
#     --PO 'map=.*/ggFbb:rH_bb[1,-20,20]' \
#     --PO 'map=.*/ggFcc:rH_cc[1,-20,20]' \
#     --PO 'map=.*/VBFbb:rH_bb[1,-20,20]' \
#     --PO 'map=.*/VBFcc:rH_cc[1,-20,20]' \
#     --PO 'map=.*/WHbb:rH_bb[1,-20,20]' \
#     --PO 'map=.*/WHcc:rH_cc[1,-20,20]' \
#     --PO 'map=.*/ZHbb:rH_bb[1,-20,20]' \
#     --PO 'map=.*/ZHcc:rH_cc[1,-20,20]'  \
#     full_Run3_srModel.txt -o workspace_Run3.root

# ONE bb POI // ALL cc POI : rH_bb // rVBF_cc , rggF_cc, rVH_cc
# text2workspace.py -P HiggsAnalysis.CombinedLimit.PhysicsModel:multiSignalModel --PO verbose \
#     --PO 'map=.*/ggFbb:rH_bb[1,-20,20]' \
#     --PO 'map=.*/ggFcc:rggF_cc[1,-20,20]' \
#     --PO 'map=.*/VBFbb:rH_bb[1,-20,20]' \
#     --PO 'map=.*/VBFcc:rVBF_cc[1,-20,20]' \
#     --PO 'map=.*/WHbb:rH_bb[1,-20,20]' \
#     --PO 'map=.*/WHcc:rVH_cc[1,-20,20]' \
#     --PO 'map=.*/ZHbb:rH_bb[1,-20,20]' \
#     --PO 'map=.*/ZHcc:rVH_cc[1,-20,20]'  \
#     full_Run3_srModel.txt -o workspace_Run3.root

# ALL POI : rVBF_bb , rggF_bb, rVH_bb // rVBF_cc , rggF_cc, rVH_cc
text2workspace.py -P HiggsAnalysis.CombinedLimit.PhysicsModel:multiSignalModel --PO verbose \
    --PO 'map=.*/ggFbb:rggF_bb[1,-20,20]' \
    --PO 'map=.*/ggFcc:rggF_cc[1,-20,20]' \
    --PO 'map=.*/VBFbb:rVBF_bb[1,-20,20]' \
    --PO 'map=.*/VBFcc:rVBF_cc[1,-20,20]' \
    --PO 'map=.*/WHbb:rVH_bb[1,-20,20]' \
    --PO 'map=.*/WHcc:rVH_cc[1,-20,20]' \
    --PO 'map=.*/ZHbb:rVH_bb[1,-20,20]' \
    --PO 'map=.*/ZHcc:rVH_cc[1,-20,20]'  \
    full_Run3_srModel.txt -o workspace_Run3.root
