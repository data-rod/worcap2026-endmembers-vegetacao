from pathlib import Path

from worcap_endmembers.review import validate_all


ROOT = Path(__file__).resolve().parents[1]


if __name__ == "__main__":
    for result in validate_all(ROOT):
        print(result)

