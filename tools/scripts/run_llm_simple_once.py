import json
import os
import sys
from datetime import datetime

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.cli import LinkedInMarketingCLI
from src.utils.llm_client import LLMClient


def main() -> None:
    data_path = r"c:\Users\Windows11\Desktop\linkedin爬虫\data\raw\merged_contacts_20250809_154043.json"
    requirements = "北美营养补剂行业，目标职位：研发总监、产品总监、BD负责人，优先Optimum Nutrition"
    min_score = 0.6

    with open(data_path, "r", encoding="utf-8") as f:
        contacts = json.load(f)

    llm_client = LLMClient()
    print("LLM_ENABLED:", llm_client.is_enabled())
    print("LLM_MODEL:", getattr(llm_client, "model_name", ""))
    print("LLM_API_URL:", getattr(llm_client, "api_url", ""))
    print("LLM_TIMEOUT:", getattr(llm_client, "timeout", ""))
    print("LLM_RETRY_ATTEMPTS:", getattr(llm_client, "retry_attempts", ""))

    cli = LinkedInMarketingCLI()
    results, stats = cli._filter_contacts_with_llm_simple(
        contacts_data=contacts,
        requirements_input=requirements,
        min_score=min_score,
    )

    processed_dir = os.path.join(os.path.dirname(os.path.dirname(data_path)), "processed")
    os.makedirs(processed_dir, exist_ok=True)
    out_path = os.path.join(
        processed_dir,
        f"llm_filtered_contacts_manual_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
    )
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "contacts": results,
                "stats": stats,
                "requirements": requirements,
                "source_file": data_path,
            },
            f,
            ensure_ascii=False,
            indent=2,
        )

    print("OUTPUT_FILE:", out_path)
    print("STATS:", stats)
    for i, row in enumerate(results[:10], 1):
        print(
            f"TOP{i}: {row.get('name', '')} | {row.get('title', '')} | {row.get('company', '')} | score={row.get('match_score', 0):.3f}"
        )


if __name__ == "__main__":
    main()
