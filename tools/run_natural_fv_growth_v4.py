"""Current v4 FV command; historical checkpoints require explicit migration/replay."""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.natural_fv_growth_scheduler import parser, run, finish, remove_trial
from tools.natural_fv_growth_interval import run as run_interval
from tools.natural_fv_growth_state_io import (CONTRACT, CAPTURE_FIELDS, STATE, identities,
    load_checkpoint, save_checkpoint, read_arrays, migrate_legacy_checkpoint)


def main():
    from tools.verify_fluvial_channel_remobilization import resource_limits
    resource_limits()
    arguments = parser().parse_args()
    if not arguments.resume:
        raise ValueError('explicit complete current checkpoint required')
    print(json.dumps(run(arguments), indent=2))


if __name__ == '__main__':
    main()
