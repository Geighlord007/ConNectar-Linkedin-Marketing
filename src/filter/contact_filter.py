import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from .embedding_filter import EmbeddingFilter


class ContactFilter:
    def __init__(self, config_path: str = "config/settings.json"):
        self.config_path = config_path
        self.embedding_filter = EmbeddingFilter(config_path=config_path)
        self.stats = {
            "total_processed": 0,
            "total_matched": 0,
            "processing_time": 0.0,
            "start_time": None,
            "end_time": None,
        }

    def filter_contacts(
        self,
        contacts: List[Dict[str, Any]],
        requirements_input: str = "",
        min_score: float = 0.3,
        output_file: Optional[str] = None,
        detailed_output: bool = True,
        detailed: Optional[bool] = None,
        require_llm: bool = False,
    ):
        """筛选联系人（使用Embedding语义向量模式）"""
        if detailed is not None:
            detailed_output = bool(detailed)

        start = time.time()
        self.stats["start_time"] = datetime.now()

        # 使用Embedding模式进行筛选
        print(f"[INFO] Using Embedding-based filtering", flush=True)

        output_contacts, stats = self.embedding_filter.filter_contacts(
            contacts=contacts,
            requirements_input=requirements_input,
            min_score=min_score
        )

        elapsed = time.time() - start
        stats["processing_time"] = elapsed
        stats["contacts_per_second"] = len(contacts) / elapsed if elapsed > 0 else 0

        if output_file:
            output_path = Path(output_file)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump({"contacts": output_contacts, "stats": stats}, f, ensure_ascii=False, indent=2)
            stats["output_file"] = str(output_path)

        if detailed is True:
            return output_contacts
        return output_contacts, stats