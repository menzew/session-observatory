"""Fictional, deterministic usage amounts with dates relative to the demo launch."""
from datetime import datetime, timedelta, timezone
import json


def sample_log(anchor=None):
    anchor = anchor or datetime.now(timezone.utc)
    rows = []
    projects = [('cedar-web', 'gpt-5.6-sol', 90000),
                ('harbor-api', 'gpt-6-astra', 65000),
                ('maple-docs', 'gpt-5.6-terra', 18000)]
    for day in range(6):
        timestamp = (anchor - timedelta(days=day, hours=1)).isoformat()
        for project, model, amount in projects:
            task = f'demo-{project}-{day}'
            events = [('session_meta', dict(id=task, cwd='/demo/'+project,
                       model_provider='openai', originator='Demo CLI', git={'branch':'demo/example'})),
                      ('turn_context', dict(model=model))]
            for step in range(4):
                n = amount * (step+1)
                events.append(('token_usage_record', dict(response_id=f'{task}-{step}',
                    usage=dict(input_tokens=n, cached_input_tokens=n*3//4,
                               cache_write_input_tokens=0, output_tokens=1200*(step+1),
                               reasoning_output_tokens=400*(step+1)))))
            rows.extend(dict(type=kind, timestamp=timestamp, payload=payload) for kind,payload in events)
    return ''.join(json.dumps(row)+'\n' for row in rows)


def seed_demo(ledger):
    ledger.import_data('synthetic-demo.jsonl', sample_log(), 'Fictional demo')
