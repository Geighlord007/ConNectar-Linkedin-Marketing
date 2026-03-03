import argparse
import json
import os
import sys
import time
from typing import Dict, List

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.cli import LinkedInMarketingCLI
from src.utils.llm_client import LLMClient


def is_default_like(contact: Dict) -> bool:
    return (
        float(contact.get("match_score", 0.0) or 0.0) == 0.0
        and not contact.get("llm_tags")
        and not contact.get("match_reasons")
        and str(contact.get("industry_category", "unknown")).lower() == "unknown"
        and str(contact.get("seniority_level", "unknown")).lower() == "unknown"
    )


def run_once(contacts: List[Dict], requirements: str, batch_size: int, min_score: float, max_tokens: int) -> Dict:
    cli = LinkedInMarketingCLI()
    cli._load_scoring_rules = lambda: {
        "filtering": {
            "llm_simple_workers": 1,
            "llm_simple_batch_size": batch_size,
            "llm_simple_max_contacts": max(200, len(contacts)),
            "llm_simple_progress_step": 999999,
        }
    }
    original_build_payload = LLMClient._build_payload

    def patched_build_payload(self, messages, **kwargs):
        kwargs["max_tokens"] = max_tokens
        return original_build_payload(self, messages, **kwargs)

    LLMClient._build_payload = patched_build_payload
    try:
        start = time.perf_counter()
        results, stats = cli._filter_contacts_with_llm_simple(
            contacts_data=contacts,
            requirements_input=requirements,
            min_score=min_score,
        )
        elapsed = time.perf_counter() - start
    finally:
        LLMClient._build_payload = original_build_payload

    return {
        "batch_size": batch_size,
        "max_tokens": max_tokens,
        "elapsed_s": round(elapsed, 2),
        "evaluated": int(stats.get("evaluated_contacts", len(contacts))),
        "result_count": len(results),
        "nonzero_scores": sum(1 for r in results if float(r.get("match_score", 0) or 0) > 0.0),
        "default_like_count": sum(1 for r in results if is_default_like(r)),
        "match_rate": float(stats.get("match_rate", 0.0)),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-path", required=True)
    parser.add_argument("--requirements", required=True)
    parser.add_argument("--sample-size", type=int, default=320)
    parser.add_argument("--min-score", type=float, default=0.0)
    parser.add_argument("--batch-sizes", nargs="+", type=int, required=True)
    parser.add_argument("--max-tokens-list", nargs="+", type=int, required=True)
    args = parser.parse_args()

    with open(args.data_path, "r", encoding="utf-8") as f:
        contacts = json.load(f)[: args.sample_size]

    print(f"SAMPLE_SIZE: {len(contacts)}")
    for max_tokens in args.max_tokens_list:
        for batch_size in args.batch_sizes:
            result = run_once(contacts, args.requirements, batch_size, args.min_score, max_tokens)
            print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
