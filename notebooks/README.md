# EC2 results analysis

Open `ec2_large_analysis.ipynb` and run all cells with Python3.11, pandas, numpy,
matplotlib and ipykernel. The frozen project requirements supply these packages.
The notebook expects the downloaded larger-host data under
`analysis/ec2-large-results/paper-v1` and writes PDF/PNG figures and CSV tables to
`analysis/ec2-large-figures`. It works from the repository or notebook directory.
Raw data is deliberately not included in the notebook commit.

For a reproducible noninteractive execution from the repository root:

```sh
uv run --python 3.11 --with-requirements requirements-lock.txt --with nbformat --with nbclient python - <<'PY'
import nbformat
from nbclient import NotebookClient
path = 'notebooks/ec2_large_analysis.ipynb'
notebook = nbformat.read(path, as_version=4)
NotebookClient(notebook, timeout=300, kernel_name='python3',
               resources={'metadata': {'path': '.'}}).execute()
nbformat.write(notebook, path)
PY
```

Recommended paper grouping: backend × scale factor × client count, averaging only
three repetitions. Use the client-count small multiples for the main performance
figure and failure heatmaps as a companion. The paired100% stacked bars show success, non-timeout error and timeout shares
for measurement-admitted attempts, including drained outcomes, averaged across
three repetitions. Each client group has MongoDB (M) left and Couchbase (C) right. Shading is min–max, not a confidence
interval. OOM marks denote full attempt-interval overlap, not precise measurement
phase attribution. See the notebook for denominator definitions and limitations.
