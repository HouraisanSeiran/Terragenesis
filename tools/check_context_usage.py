"""Read only token counters from the current session; never export conversation text."""
import argparse
import json
from pathlib import Path
from datetime import datetime, timezone

parser = argparse.ArgumentParser()
parser.add_argument('session', type=Path)
args = parser.parse_args()
latest = None
compactions = 0
with args.session.open(encoding='utf-8') as stream:
    for line in stream:
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if event.get('type') == 'compacted':
            compactions += 1
        payload = event.get('payload', {})
        if payload.get('type') == 'token_count' and payload.get('info'):
            latest = {'timestamp': event.get('timestamp'), **payload['info']}
report = {
    'checked_at': datetime.now(timezone.utc).isoformat(),
    'compaction_records': compactions,
    'latest_reported_usage': latest,
    'interpretation': 'last_token_usage is the last recorded request, not a guaranteed live context meter; '
                      'total_token_usage accumulates repeated inputs across calls, including cache hits.',
}
out = Path(__file__).resolve().parents[1] / 'verification/context-usage.json'
out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(report, ensure_ascii=False, indent=2))
