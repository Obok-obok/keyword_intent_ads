"""평가 유틸리티."""

from __future__ import annotations

from pathlib import Path
from typing import Dict

import pandas as pd


def evaluate_outputs(pred_path: str | Path, gold_path: str | Path) -> Dict[str, float]:
    """query 기준으로 pred와 gold를 조인해 간단한 정확도를 계산한다."""
    pred = pd.read_excel(pred_path, dtype=str).fillna("") if str(pred_path).endswith("xlsx") else pd.read_csv(pred_path, dtype=str).fillna("")
    gold = pd.read_excel(gold_path, dtype=str).fillna("") if str(gold_path).endswith("xlsx") else pd.read_csv(gold_path, dtype=str).fillna("")

    join_key = "query_norm" if "query_norm" in pred.columns and "query_norm" in gold.columns else "query"
    df = pred.merge(gold, on=join_key, suffixes=("_pred", "_gold"))
    metrics: Dict[str, float] = {"n": float(len(df))}
    for col in ["gate_type", "insurance_category", "customer_need_type", "evidence_focus"]:
        p = f"{col}_pred"
        g = f"{col}_gold"
        if p in df.columns and g in df.columns and len(df) > 0:
            metrics[f"{col}_accuracy"] = float((df[p] == df[g]).mean())

    if "evidence_focus_pred" in df.columns:
        metrics["focus_overfill_rate"] = float(((df["evidence_focus_pred"] != "null") & (df["evidence_focus_gold"] == "null")).mean()) if "evidence_focus_gold" in df.columns else 0.0

    return metrics
