# hbb-run3

## Setup environment

**Singularity**: (for submitting jobs)
Set up environment by following instructions at https://github.com/CoffeaTeam/lpcjobqueue/

Ensure you have a valid grid certificate.

Enable singularity
```bash
./shell coffeateam/coffea-dask-almalinux9:latest
```

**Virtual environment**: (for testing locally)

The instructions below will do the following:

- Download the micromamba setup script (change if needed for your machine https://mamba.readthedocs.io/en/latest/installation/micromamba-installation.html)
- Install: (the micromamba directory can end up taking O(1-10GB) so make sure the directory you're using allows that quota)
    - Note: If on lpc cluster: install micromamba in `nobackup` area.

```
# Download and execute install script
"${SHELL}" <(curl -L micro.mamba.pm/install.sh)
# You may need to restart your shell
```

Here is an example output:
```
  % Total    % Received % Xferd  Average Speed   Time    Time     Time  Current
                                 Dload  Upload   Total   Spent    Left  Speed
  0     0    0     0    0     0      0      0 --:--:-- --:--:-- --:--:--     0
100  3059  100  3059    0     0   3196      0 --:--:-- --:--:-- --:--:--  3196
Micromamba binary folder? [~/.local/bin] ~/nobackup/micromamba
Init shell (bash)? [Y/n] Y
Configure conda-forge? [Y/n] y
Running `shell init`, which:
 - modifies RC file: "/uscms/home/cmantill/.bashrc"
 - generates config for root prefix: "/uscms_data/d3/cmantill/micromamba"
 - sets mamba executable to: "/uscms_data/d3/cmantill/y/micromamba"
The following has been added in your "/uscms/home/cmantill/.bashrc" file

# >>> mamba initialize >>>
# !! Contents within this block are managed by 'micromamba shell init' !!
export MAMBA_EXE='/uscms_data/d3/cmantill/y/micromamba';
export MAMBA_ROOT_PREFIX='/uscms_data/d3/cmantill/micromamba';
__mamba_setup="$("$MAMBA_EXE" shell hook --shell bash --root-prefix "$MAMBA_ROOT_PREFIX" 2> /dev/null)"
if [ $? -eq 0 ]; then
    eval "$__mamba_setup"
else
    alias micromamba="$MAMBA_EXE"  # Fallback on help from micromamba activate
fi
unset __mamba_setup
# <<< mamba initialize <<<
```

Then create an environment:
```
micromamba create -n hbb python=3.10 -c conda-forge
micromamba activate hbb
# install ipykernel for running jupyter notebooks
micromamba install  -n hbb ipykernel
```

Install requirements (see note on lpc below):
```
# Perform an editable installation
pip install -e .
# for committing to the repository
pip install pre-commit
pre-commit install
# install requirements
pip install -r requirements.txt
```

Note:
In LPC, install pre-commit in your nobackup area:
```
pip install --target=~/nobackup/pre-commit pre-commit
# export location of your precommits
echo 'export PRE_COMMIT_HOME=~./nobackup/pre-commit/.pre-commit-cache' >> ~/.bashrc
source ~/.bashrc
```

## Run processor locally

**In your micromamba environment:**
```
micromamba activate hbb
```

```bash
# to run on a single file (starting index at 0, ending index at 1) for one subsample
python src/run.py --sample Hbb --subsample GluGluHto2B_PT-200_M-125 --starti 0 --endi 1
# to save skim, add:
--save-skim

# to run on multiple subsamples
python src/run.py --sample Hbb --subsample GluGluHto2B_PT-200_M-125  VBFHto2B_M-125 --starti 0 --endi 1
```

## Submit jobs with DASK

**In the bash shell:**

Run the processor for a certain year:
```bash
python3 submit.py --year $YEAR --tag $TAG --yaml src/submit_configs/hbb_example.yaml
```
e.g.:
```
python3 submit.py --year 2022 --tag test --yaml src/submit_configs/hbb_example.yaml
```


Format your tags as `TAG=YRMonthDay` e.g. `TAG=25May22`.

To enable the skimming option, add:
```bash
--save-skim
```

The processor will output parquet files for each of the regions defined in categorizer.py, for example:

```python
regions = {
    "signal-ggf",
    "signal-vh",
    "signal-vbf",
    "control-tt",
}
```
It is then straightforward to define regions and cuts in order to customize skims for individual studies.

### Debugging

- Look for error:
```
proxy has expired
```
if your proxy is not valid in the dask submission.
Note: Start your proxy outside your `./shell` singularity environment.

## Submit jobs with CONDOR

To submit a specific subsample:
```bash
python src/condor/submit.py --tag $TAG  --samples Hbb --subsamples GluGluHto2B_PT-200_M-125 --git-branch main  --allow-diff-local-repo
```
- Format your tags as `TAG=YRMonthDay` e.g. `TAG=25May22`.
- You must specify the git branch name
- If you have local changest that have not been committed to github, it will complain. Add `--allow-diff-local-repo` to avoid that`.

This will create a set of condor submission files. To submit add: `--submit`.

To submit a set of samples (this will submit all years in that yaml file:
```bash
nohup python src/condor/submit_from_yaml.py --tag $TAG --yaml src/submit_configs/${YAML}.yaml --year $YEAR &> tmp/submitout.txt &
```

By default the yaml is: `src/submit_configs/hbb.yaml`.

For example:
```
# The git branch should be specified
# For best practices, the script will automatically check if your code version is up to date in github. If you have changes that are not committed/pushed use --allow-diff-local-repo

python src/condor/submit_from_yaml.py --yaml src/submit_configs/hbb.yaml --tag 25May23 --git-branch main --allow-diff-local-repo --year 2022EE
```

To check whether jobs have finished use `src/condor/check_jobs.py`.

Example:
```
python src/condor/check_jobs.py  --location /eos/uscms/store/user/lpchbbrun3/cmantill/ --tag 25Jun25_v12 --year 2023
```

## Plotting features from parquet files

Example:
```
python make_histos.py  --region signal-all --year 2022
```
