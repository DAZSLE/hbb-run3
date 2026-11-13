#!/bin/bash
# run_combined_ccs_fit.sh
# Combined Z+gamma + Z->mumu fit, ccs-JOINT model (the default):
#   zgammabb -> r_bb ;  zgammacc AND wgammacs -> r_ccs ;  z_norm shared with the mumu CR.
# Requires cmsenv. Uses existing datacards (no histogramming).
#
# STANDARD reference = the mumu+GAMMA card (Zgamma->mumu, same production as Zgamma->bb).
# Its z_norm carries the real Zgamma normalization; plain-DY mumu cannot (see METHOD_NOTE §4a0).
#
# Usage:
#   bash run_combined_ccs_fit.sh --year 2024 --tag 24Aug07_v15 [--model zgcr] [--zmmdir <path>] [--suffix _x]
#   --model : zgcr datacard model name (make_datacards --analysis); default "zgcr" -> zgcrModel_YEAR
#   --zmmdir: override the zmmcrModel dir; DEFAULT = mumu+gamma card (results_zmmcr_gamma_cards/...).
#             For the old plain-DY reference pass:
#             --zmmdir results/<TAG>/<YEAR>/datacards/zmmcrModel_<YEAR>
set -e
YEAR=2024
TAG=24Aug07_v15
MODEL=zgcr
ZMMDIR=""
SUFFIX="_mumugamma"
EXTRA=""
while [[ $# -gt 0 ]]; do
  case $1 in
    --year)   YEAR=$2;   shift 2 ;;
    --tag)    TAG=$2;    shift 2 ;;
    --model)  MODEL=$2;  shift 2 ;;
    --zmmdir) ZMMDIR=$2; shift 2 ;;
    --suffix) SUFFIX=$2; shift 2 ;;
    --extra)  EXTRA=$2;  shift 2 ;;
    *) echo "Unknown argument: $1"; exit 1 ;;
  esac
done

FITTING_DIR="$(cd "$(dirname "$0")" && pwd)"
ZGCR_DIR="${FITTING_DIR}/results/${TAG}/${YEAR}/datacards/${MODEL}Model_${YEAR}"
# DEFAULT reference = mumu+gamma card; override with --zmmdir
ZMMCR_DIR="${ZMMDIR:-${FITTING_DIR}/results_zmmcr_gamma_cards/${TAG}/${YEAR}/datacards/zmmcrModel_${YEAR}}"
OUTDIR="${FITTING_DIR}/results/${TAG}/${YEAR}/datacards/${MODEL}_combined_ccs${SUFFIX}_${YEAR}"

mkdir -p "$OUTDIR"; cd "$OUTDIR"

echo "=== Zgamma passbb/passcc/fail (+ z_norm on zgammabb, zgammacc) ==="
for cat in passbb passcc fail; do
    cp "${ZGCR_DIR}/ptbin0zgcr${cat}${YEAR}.txt" .
    echo "z_norm rateParam * zgammabb 1 [0,5]" >> ptbin0zgcr${cat}${YEAR}.txt
    echo "z_norm rateParam * zgammacc 1 [0,5]" >> ptbin0zgcr${cat}${YEAR}.txt
done
cp "${ZGCR_DIR}/${MODEL}Model_${YEAR}.root" .

echo "=== Z->mumu card (already carries z_norm on zmm) ==="
cp "${ZMMCR_DIR}/ptbin0zmmcrinclusive${YEAR}.txt" .
cp "${ZMMCR_DIR}/zmmcrModel_${YEAR}.root" .

echo "=== combineCards (passbb + passcc + fail + zmm) ==="
combineCards.py \
    ptbin0zgcrpassbb${YEAR}=ptbin0zgcrpassbb${YEAR}.txt \
    ptbin0zgcrpasscc${YEAR}=ptbin0zgcrpasscc${YEAR}.txt \
    ptbin0zgcrfail${YEAR}=ptbin0zgcrfail${YEAR}.txt \
    ptbin0zmmcrinclusive${YEAR}=ptbin0zmmcrinclusive${YEAR}.txt \
    > combined_ccs_${YEAR}.txt

echo "=== ccs-joint workspace (zgammacc + wgammacs -> r_ccs) ==="
text2workspace.py combined_ccs_${YEAR}.txt \
    -P HiggsAnalysis.CombinedLimit.PhysicsModel:multiSignalModel \
    --PO "map=.*/zgammabb:r_bb[1,-100,100]" \
    --PO "map=.*/zgammacc:r_ccs[1,-100,100]" \
    --PO "map=.*/wgammacs:r_ccs[1,-100,100]" \
    -o workspace_ccs_${YEAR}.root

echo "=== FitDiagnostics (r_bb, r_ccs) ==="
combine -M FitDiagnostics -d workspace_ccs_${YEAR}.root \
    --redefineSignalPOIs r_bb,r_ccs \
    --saveShapes --saveWithUncertainties \
    --cminDefaultMinimizerStrategy 1 ${EXTRA} \
    -n _ccs${SUFFIX}_${YEAR}

echo "=== MultiDimFit --algo singles (clean profiled errors on r_bb, r_ccs, z_norm) ==="
combine -M MultiDimFit -d workspace_ccs_${YEAR}.root --algo singles \
    --redefineSignalPOIs r_bb,r_ccs,z_norm \
    --cminDefaultMinimizerStrategy 1 ${EXTRA} \
    -n _ccs${SUFFIX}_singles_${YEAR}

echo ""
echo "Done (ccs-joint). Results in: $OUTDIR"
