"""Default current-v4 FV CLI; historical v1-v3 execution is explicit legacy replay."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0,str(ROOT))

from tools.run_natural_fv_growth_v4 import main, parser, run
from tools.natural_fv_growth_interval import forcing_step


if __name__=='__main__':
    main()
