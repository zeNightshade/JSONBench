"""Read-only helpers for analysis of downloaded native JSONBench matrices."""
from datetime import datetime, timezone
import json
from pathlib import Path

import pandas as pd


def repository_root():
    """Find the checkout when running from its root or a notebook subdirectory."""
    return next(p for p in (Path.cwd(), *Path.cwd().parents) if (p / 'jsonbench/matrix.py').exists())


def load_outcomes(root, *, backend, scale_factor, kernel_log):
    """Validate raw measurement-admitted outcomes and attribute query-engine kills.

    OOM attribution uses full attempt intervals, not exact measurement intervals.
    Events finishing during drain are included if admitted during measurement.
    """
    root = Path(root)
    plan = json.loads((root / 'plan.json').read_text())
    state = json.loads((root / 'state.json').read_text())
    status = json.loads((root / 'native-status.json').read_text())
    assert status['state'] == 'complete'
    start, end = status['started_at'], status['finished_at']
    years = range(datetime.fromtimestamp(start, timezone.utc).year,
                  datetime.fromtimestamp(end, timezone.utc).year + 1)
    kills = []
    for line in (root / kernel_log).read_text().splitlines():
        if 'Killed process' not in line or '(cbq-engine)' not in line:
            continue
        for year in years:
            stamp = datetime.strptime(f'{year} {line[:15]}', '%Y %b %d %H:%M:%S').replace(tzinfo=timezone.utc).timestamp()
            if start <= stamp <= end:
                kills.append(stamp)
    rows = []
    for cell in plan['cells']:
        if cell['backend'] != backend or cell['scale_factor'] != scale_factor:
            continue
        attempts = state['attempts'][cell['id']]
        attempt = attempts[-1]
        assert attempt['state'] == 'complete', cell['id']
        run = root / 'attempts' / attempt['run_path'].split('/attempts/', 1)[1]
        info = json.loads((run / 'info.json').read_text())
        summary = json.loads((run / 'summary.json').read_text())
        events = [json.loads(line) for line in (run / 'events.jsonl').open()]
        completed = [e for e in events if e['event'] == 'completed']
        ids = [e['attempt_id'] for e in completed]
        assert len(set(ids)) == len(ids)
        assert set(ids) == {e['attempt_id'] for e in events if e['event'] == 'started'}
        begin = info['warmup_seconds']
        admitted = [e for e in completed if begin <= e['start_seconds'] < begin + info['measurement_seconds']]
        counts = {label: sum(e['status'] == label for e in admitted) for label in ('success', 'error', 'timeout')}
        assert sum(counts.values()) == len(admitted) > 0
        for label, field in [('success', 'measurement_successes'), ('error', 'measurement_errors'), ('timeout', 'measurement_timeouts')]:
            assert counts[label] == summary[field], (cell['id'], field)
        rows.append(dict(cell=cell['id'], clients=cell['workers'], repetition=cell['repetition'],
                         seed=cell['seed'], attempts=len(attempts), admitted=len(admitted), **counts,
                         oom_kills=sum(attempt['started_at'] <= t <= attempt['finished_at'] for t in kills),
                         revision=info['revision'], dataset_hash=info['dataset_manifest_sha256'],
                         queries=json.dumps(info['queries'], sort_keys=True),
                         warmup_seconds=begin, measurement_seconds=info['measurement_seconds'],
                         query_timeout_seconds=info['query_timeout_seconds']))
    result = pd.DataFrame(rows).sort_values(['clients', 'repetition']).reset_index(drop=True)
    assert len(result) == 18 and result.groupby('clients').size().eq(3).all()
    assert sorted(result.clients.unique()) == [2, 4, 8, 16, 32, 64]
    return result


def validate_paired_runs(before, after):
    """Require matching workloads and datasets before comparing memory settings."""
    fields = ['cell', 'clients', 'repetition', 'seed', 'revision', 'dataset_hash', 'queries',
              'warmup_seconds', 'measurement_seconds', 'query_timeout_seconds']
    pd.testing.assert_frame_equal(before[fields], after[fields])
