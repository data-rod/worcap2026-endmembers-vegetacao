from pathlib import Path

from worcap_endmembers.panel import build_panels
from worcap_endmembers.workflow import compare_candidates, run_ppi, verify_release


ROOT = Path(__file__).resolve().parents[1]


if __name__ == "__main__":
    print(verify_release(ROOT))
    print(run_ppi(ROOT, output="outputs/reproduced"))
    print(compare_candidates("outputs/reproduced/candidates", "data/candidates", ROOT))
    print(build_panels(ROOT, candidates="outputs/reproduced/candidates", output="outputs/reproduced/panels"))

