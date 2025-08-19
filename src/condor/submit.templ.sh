
#!/bin/bash

# remove old files
rm *.pkl
rm *.parquet

for t2_prefix in ${t2_prefixes}
do
    for folder in pickles parquet githashes
    do
        xrdfs $${t2_prefix} mkdir -p "/${outdir}/$${folder}"
    done
done

# clone repository
# try 3 times in case of network errors
(
    r=3
    # shallow clone of single branch (keep repo size as small as possible)
    while ! git clone --single-branch --branch $branch --depth=1 https://github.com/DAZSLE/hbb-run3.git
    do
        ((--r)) || exit
        sleep 60
    done
)
cd hbb-run3 || exit

commithash=$$(git rev-parse HEAD)
echo "https://github.com/DAZSLE/hbb-run3/commit/$${commithash}" > commithash.txt

#move output to t2s
for t2_prefix in ${t2_prefixes}
do
    xrdcp -f commithash.txt $${t2_prefix}/${outdir}/githashes/commithash_${jobnum}.txt
done

pip install -e .

# run code (saving skim always)
python -u -W ignore $script --year $year --starti $starti --endi $endi --samples $sample --subsamples $subsample --nano-version ${nano_version} --save-skim

# Move final output to EOS
# This new logic recursively copies the region directories created by the processor

# First, copy the pickle file
xrdfs ${t2_prefixes} mkdir -p "/${outdir}/pickles"
xrdcp -f *.pkl "${t2_prefixes}/${outdir}/pickles/out_${jobnum}.pkl"

# Next, copy the entire directory structure for the skimmed files
LOCAL_SKIM_DIR="outparquet/${year}/${year}_${subsample}"
if [ -d "$$LOCAL_SKIM_DIR" ]; then
    # Copy each region directory (e.g., control-tt, signal-all) and its contents
    for region_dir in $$LOCAL_SKIM_DIR/*; do
        if [ -d "$$region_dir" ]; then
            xrdcp -r -f $$region_dir ${t2_prefixes}/${outdir}/
        fi
    done
fi

rm *.parquet
rm *.pkl
rm commithash.txt
