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
figure and failure heatmaps as a companion. The six-panel100% stacked bars show success, non-timeout error and timeout shares
for measurement-admitted attempts, including drained outcomes, averaged across
three repetitions. MongoDB occupies the top row and Couchbase the bottom row; columns fix scale factor. Shading is min–max, not a confidence
interval. OOM marks denote full attempt-interval overlap, not precise measurement
phase attribution. See the notebook for denominator definitions and limitations.

The Couchbase SF=200 timeline shows 10-second completion-count histograms, with
client counts as rows and repetitions as columns. It includes measurement-admitted
queries and their drain outcomes; a query filter allows inspecting individual queries.
Event and binned-count CSV exports accompany the 200 dpi PNG and vector PDF.

## Memory comparison

`ec2_memory_comparison.ipynb` compares Couchbase SF=200 in the original 12 GiB
and doubled 24 GiB service-budget matrices. It also records the doubled data/index
quotas, validates matched workloads against raw events, and displays outcome
percentages alongside kernel-recorded query-engine OOM counts. Each repetition
receives equal weight in the bars; supporting tables also expose pooled counts.
Read-only loading and comparison checks live in `utilities.py`.

The notebook reads `analysis/ec2-large-results/paper-v1` and
`analysis/ec2-large-memory24-results/paper-memory24-v1`, including their archived
kernel journals. Outputs go to `analysis/ec2-memory-comparison-figures` as 200 dpi
PNG, vector PDF and CSV. Use the execution command above with
`path = 'notebooks/ec2_memory_comparison.ipynb'`.
