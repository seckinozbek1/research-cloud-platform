#!/bin/bash

#SBATCH --job-name=karsiyaka-mpi
#SBATCH --partition=cpu
#SBATCH --nodes=2
#SBATCH --ntasks=4
#SBATCH --ntasks-per-node=2
#SBATCH --cpus-per-task=1
#SBATCH --mem=2G
#SBATCH --time=00:10:00
#SBATCH --output=/data/karsiyaka-mpi-%j.out

export PATH=/usr/lib64/openmpi/bin:$PATH
export LD_LIBRARY_PATH=/usr/lib64/openmpi/lib:${LD_LIBRARY_PATH:-}

cd /workspace/research-cloud-platform

mpirun \
    --allow-run-as-root \
    -np "$SLURM_NTASKS" \
    --host c1:2,c2:2 \
    python3 mlops/waste_gis/build_hub_bin_travel_matrix_mpi.py
