#!/bin/bash
#SBATCH --partition=batch
#SBATCH --nodes=1
#SBATCH --ntasks=8
#SBATCH --ntasks-per-node=8
#SBATCH --cpus-per-task=1
#SBATCH --mem-per-cpu=6G
#SBATCH --time=12:00:00
#SBATCH --gres=lscratch:100
#SBATCH --signal=B:USR1@60

set -uo pipefail

SUBMIT_DIR=$(pwd)
SCRATCH_DIR="/lscratch/${USER}/orca_${SLURM_JOB_ID}"

mkdir -p "$SCRATCH_DIR"
rsync -a "$SUBMIT_DIR/" "$SCRATCH_DIR/"
cd "$SCRATCH_DIR"

cleanup() {
    echo "Signal/Error caught. Syncing progress to $SUBMIT_DIR..."
    rsync -a --exclude='*tmp*' "$SCRATCH_DIR/" "$SUBMIT_DIR/"
    rm -rf "$SCRATCH_DIR"
}
trap cleanup EXIT USR1

module load ORCA/6.1
ORCA_EXE=$(which orca)

echo "Starting FREQ at $(date)"
$ORCA_EXE freq_f.inp > freq_f.log
cp "freq_f.log" "$SUBMIT_DIR/freq_f.log"

echo "Starting ENERGY at $(date)"
$ORCA_EXE energy_f.inp > energy_f.log

rsync -a "$SCRATCH_DIR/" "$SUBMIT_DIR/"

# Disable the trap so the cleanup function doesn't rsync a second time on exit
trap - EXIT USR1
rm -rf "$SCRATCH_DIR"
