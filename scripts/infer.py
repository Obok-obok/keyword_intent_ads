from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import argparse
from src.infer import run_inference, export_review_template


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--query-path", required=True)
    parser.add_argument("--base-rules", default="configs/base_rules.xlsx")
    parser.add_argument("--feedback-store", default=None)
    parser.add_argument("--model-path", default=None)
    parser.add_argument("--output", default="outputs/inference_result.xlsx")
    parser.add_argument("--review-template", default="outputs/review_template.xlsx")
    parser.add_argument("--enable-semantic-hints", action="store_true", help="의미 유사 힌트까지 계산한다. 속도상 기본 OFF 권장")
    parser.add_argument("--no-dedupe", action="store_true", help="동일 query_norm 캐시를 끈다")
    args = parser.parse_args()

    result = run_inference(
        query_path=args.query_path,
        base_rules_path=args.base_rules,
        feedback_store_path=args.feedback_store,
        model_path=args.model_path,
        output_path=args.output,
        enable_semantic_hints=args.enable_semantic_hints,
        dedupe=not args.no_dedupe,
    )
    export_review_template(result, args.review_template)
    print(f"saved: {args.output}")
    print(f"saved: {args.review_template}")
    print(result.head(20).to_string())


if __name__ == "__main__":
    main()
