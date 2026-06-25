#!/bin/bash
## Job Config
#SBATCH --job-name=cardiokb_compgcn
#SBATCH --mail-user=Asma.Nawaz@cshs.org
#SBATCH --mail-type=ALL

## Task and hardware config — GPU required for CompGCN
#SBATCH -p gpu
#SBATCH -N 1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=64G
#SBATCH --gres=gpu:1
#SBATCH --exclude=esplhpc-cp018

## Time Config — CompGCN on 459K nodes, 200 epochs with early stopping
#SBATCH --time=24:00:00
#SBATCH --output=logs/%x_%j.out

# Name of conda env
ENV_NAME=cardiokb_ml

echo "My job ran on:"
echo $SLURM_NODELIST

# Loading modules
module purge
module load slurm
module load gcc/11.2.0
module load miniconda3-4.10.3-gcc-11.2.0-33aghju
module load cuda12.4/toolkit/12.4.1

echo "Loaded Modules"
module list

# Getting path to miniconda3
CONDA_BASE=$(conda info --base)
source "$CONDA_BASE/etc/profile.d/conda.sh"

# Setting up python env
if ! conda info --envs | grep -q "$ENV_NAME"; then
    echo "Environment $ENV_NAME does not exist. Creating..."
    conda create -y -n "$ENV_NAME" python=3.11
fi

conda activate "$ENV_NAME"

echo "Active conda environment:"
which python
python --version

# Install PyTorch with CUDA 12.4 support — uninstall first to avoid CPU fallback
pip uninstall -y torch 2>/dev/null
pip install torch --index-url https://download.pytorch.org/whl/cu124

# CompGCN implementation is pure PyTorch — no torch-geometric needed
pip install -q numpy

# Verify GPU access — abort early if CUDA not available
python -c "
import torch
print(f'PyTorch version: {torch.__version__}')
print(f'CUDA built with: {torch.version.cuda}')
print(f'CUDA available: {torch.cuda.is_available()}')
if torch.cuda.is_available():
    print(f'GPU: {torch.cuda.get_device_name(0)}')
else:
    print('ERROR: CUDA not available, aborting')
    exit(1)
"

if [ $? -ne 0 ]; then
    echo "GPU verification failed, exiting"
    exit 1
fi

# Running CompGCN training
echo "Starting CompGCN training..."
cd $SLURM_SUBMIT_DIR

srun python -u train_compgcn.py
