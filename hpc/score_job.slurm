#!/bin/bash
## Job Config
#SBATCH --job-name=cardiokb_score
#SBATCH --mail-user=Asma.Nawaz@cshs.org
#SBATCH --mail-type=ALL

## CPU-only — no GPU needed for XGBoost scoring
#SBATCH -p gpu
#SBATCH -N 1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=16
#SBATCH --mem=128G
#SBATCH --gres=gpu:1
#SBATCH --exclude=esplhpc-cp018,esplhpc-cp076

## Time Config — scoring ~25M pairs per method, ~30 min each
#SBATCH --time=4:00:00
#SBATCH --output=logs/%x_%j.out

ENV_NAME=cardiokb_ml

echo "My job ran on:"
echo $SLURM_NODELIST
echo "Date: $(date)"
ulimit -v || true
echo "SLURM_MEM_PER_NODE=$SLURM_MEM_PER_NODE"

module purge
module load slurm
module load gcc/11.2.0
module load miniconda3-4.10.3-gcc-11.2.0-33aghju

CONDA_BASE=$(conda info --base)
source "$CONDA_BASE/etc/profile.d/conda.sh"

if ! conda info --envs | grep -q "$ENV_NAME"; then
    echo "Environment $ENV_NAME does not exist. Creating..."
    conda create -y -n "$ENV_NAME" python=3.11
fi

conda activate "$ENV_NAME"

echo "Active conda environment:"
which python
python --version

pip install -q xgboost scikit-learn python-dotenv numpy

cd $SLURM_SUBMIT_DIR

echo "=========================================="
echo "Scoring CompGCN..."
echo "=========================================="
python -u score_only.py compgcn || echo "ERROR: CompGCN scoring failed with exit code $?"

echo "=========================================="
echo "Scoring RotatE..."
echo "=========================================="
python -u score_only.py rotate || echo "ERROR: RotatE scoring failed with exit code $?"

echo "=========================================="
echo "All done at $(date)"
echo "=========================================="
