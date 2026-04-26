"""검색어 정규화 유틸리티.

이 모듈은 v5 Phase 1 Light의 가장 앞단에서 동작한다.
정규화는 과하게 하지 않는다. 광고 검색어는 짧고 의도가 압축되어 있으므로,
형태소 분석이나 의미 변환보다 "같은 검색어를 같은 키로 맞추는 것"이 중요하다.

주요 역할:
- 앞뒤 공백 제거
- 중복 공백 제거
- 전각/반각, 일부 특수문자 정리
- null-like 값 표준화
- 영어는 소문자화
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any

NULL_LIKE = {"", "nan", "none", "null", "na", "n/a", "-", "없음"}


def is_null_like(value: Any) -> bool:
    """값이 비어 있거나 null처럼 쓰이는 문자열인지 확인한다."""
    if value is None:
        return True
    text = str(value).strip()
    return text.lower() in NULL_LIKE


def normalize_query(value: Any) -> str:
    """검색어를 비교 가능한 형태로 정규화한다.

    이 함수는 검색어의 의미를 바꾸지 않는다.
    예를 들어 '비갱신형'을 '갱신형'으로 바꾸거나,
    '실비'를 '실손보험'으로 바꾸지 않는다. 그런 작업은 phrase 사전에서 담당한다.
    """
    if is_null_like(value):
        return ""

    text = str(value)
    text = unicodedata.normalize("NFKC", text)
    text = text.strip().lower()
    text = re.sub(r"[\u200b\u200c\u200d\ufeff]", "", text)
    text = re.sub(r"[\"'`“”‘’]", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def normalize_label(value: Any, *, null_value: str = "null") -> str:
    """라벨 값을 표준화한다.

    엑셀에서는 빈칸, NaN, None, '-' 등이 섞여 들어오기 쉽다.
    출력 계약에서는 비어 있는 카테고리를 문자열 'null'로 통일한다.
    """
    if is_null_like(value):
        return null_value
    return str(value).strip()
