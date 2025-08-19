#!/bin/bash

# remove old files
rm *.pkl
rm *.parquet

# clone repository
# try 3 times in case of network errors
(
    r=3
    # shallow clone of single branch (keep repo size as small as possible)
    while ! git clone --single-branch --branch $branch --depth=1 https://github.com/gabihamilton/hbb-run3.git
    do
        ((--r)) || exit
        sleep 60
    done
)
cd hbb-run3 || exit

# Save the githash directly to the final destination
commithash=$$(git rev-parse HEAD)
echo "https://github.com/DAZSLE/hbb-run3/commit/$${commithash}" > commithash.txt
xrdfs $${t2_prefixes[0]} mkdir -p "/${outdir}/githashes"
xrdcp -f commithash.txt $${t2_prefixes[0]}/${outdir}/githashes/commithash_${jobnum}.txt


pip install -e .

# Run the python script, passing the remote outdir
python -u -W ignore $script --year $year --starti $starti --endi $endi --samples $sample --subsamples $subsample --nano-version ${nano_version} --save-skim --outdir ${outdir}


# Move final output to EOS
# 1. Copy the pickle file (histograms)
xrdfs $${t2_prefixes[0]} mkdir -p "/${outdir}/pickles"
xrdcp -f *.pkl "${t2_prefixes[0]}/${outdir}/pickles/out_${jobnum}.pkl"

# 2. Recursively copy the entire parquet directory structure
LOCAL_PARQUET_DIR="outparquet/${year}/${year}_${subsample}/parquet"
if [ -d "$$LOCAL_PARQUET_DIR" ]; then
    xrdcp -r -f $$LOCAL_PARQUET_DIR ${t2_prefixes[0]}/${outdir}/
fi


# Final cleanup
rm *.parquet
rm *.pkl
rm commithash.txt
