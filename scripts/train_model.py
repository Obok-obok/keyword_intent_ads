from pathlib import Path
import argparse
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.model import train_model


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--gold-path", required=True)
    parser.add_argument("--output", "--model-path", dest="output", default="outputs/model_bundle.joblib")
    args = parser.parse_args()
    train_model(args.gold_path, args.output)
    print(f"model saved: {args.output}")


if __name__ == "__main__":
    main()
