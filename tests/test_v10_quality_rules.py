from src.rules import load_rules, resolve_query
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RULES = ROOT / "configs" / "base_rules.xlsx"

def infer(q):
    return resolve_query(q, load_rules(RULES))

def test_care_price_need_overrides_coverage():
    r = infer("간병인 보험 가격")
    assert r["insurance_category"] == "간병인보험"
    assert r["customer_need_type"] == "보험료확인"
    assert r["customer_need_detail"] == "보험료/가격확인"

def test_care_compare_need_overrides_coverage():
    r = infer("간병인 보험 비교")
    assert r["insurance_category"] == "간병인보험"
    assert r["customer_need_type"] == "상품비교"

def test_care_public_support_oos():
    r = infer("간병인 지원 제도")
    assert r["gate_type"] == "oos"
    assert r["insurance_category"] == "null"

def test_family_care_exact_not_typo():
    r = infer("가족 간병 보험")
    assert r["insurance_category"] in {"재가간병보험", "간병보험"}
    assert r["evidence_focus"] in {"재가간병비", "가족간병인보장"}

def test_dental_splint_and_zirconia():
    assert infer("스플린트 보험")["insurance_category"] == "치아보험"
    assert infer("지르코니아 보험")["insurance_category"] == "치아보험"

def test_medical_insurance_public_oos():
    r = infer("의료 보험 조회")
    assert r["gate_type"] == "oos"
    assert r["insurance_category"] == "null"

def test_admission_and_savings_categories():
    assert infer("입원 보험")["insurance_category"] == "입원비보험"
    assert infer("저축성 보험")["insurance_category"] == "저축보험"
