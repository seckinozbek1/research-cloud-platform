#!/bin/bash

#SBATCH --job-name=karsiyaka-matrix
#SBATCH --partition=cpu
#SBATCH --array=0-5%2
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=2
#SBATCH --mem=2G
#SBATCH --time=00:10:00
#SBATCH --output=/data/karsiyaka-%A_%a.out

cd /workspace/research-cloud-platform

python3 mlops/waste_gis/build_hub_bin_travel_matrix_worker.py \
    "$SLURM_ARRAY_TASK_ID"
