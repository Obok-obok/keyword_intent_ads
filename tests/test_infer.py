from src.rules import RuleBook, load_rules, resolve_query
from src.feedback import quick_fix_exact, quick_add_phrase, quick_add_exclusion
from src.infer import run_inference


def make_rulebook():
    phrases = [
            {"surface": "치아보험", "slot": "insurance_category", "canonical_value": "치아보험", "level": 6, "priority": 7000, "category_hint": "치아보험", "need_hint": "상품추천탐색", "gate_hint": "general", "is_protected": False, "allow_nested": False, "match_type": "contains", "source": "test"},
            {"surface": "청구", "slot": "action_service", "canonical_value": "청구", "level": 3, "priority": 8500, "category_hint": "", "need_hint": "청구/보험금문의", "gate_hint": "general", "is_protected": False, "allow_nested": False, "match_type": "contains", "source": "test"},
            {"surface": "임플란트", "slot": "coverage_focus", "canonical_value": "임플란트보장", "level": 5, "priority": 7500, "category_hint": "치아보험", "need_hint": "보장범위확인", "gate_hint": "detailed", "is_protected": False, "allow_nested": False, "match_type": "contains", "source": "test"},
            {"surface": "비갱신형", "slot": "policy_product_feature", "canonical_value": "비갱신형", "level": 4, "priority": 8000, "category_hint": "", "need_hint": "상품조건확인", "gate_hint": "detailed", "is_protected": True, "allow_nested": False, "match_type": "contains", "source": "test"},
            {"surface": "갱신형", "slot": "policy_product_feature", "canonical_value": "갱신형", "level": 4, "priority": 7900, "category_hint": "", "need_hint": "상품조건확인", "gate_hint": "detailed", "is_protected": False, "allow_nested": False, "match_type": "contains", "source": "test"},
            {"surface": "암보험", "slot": "insurance_category", "canonical_value": "암보험", "level": 6, "priority": 7000, "category_hint": "암보험", "need_hint": "상품추천탐색", "gate_hint": "general", "is_protected": False, "allow_nested": False, "match_type": "contains", "source": "test"},
            {"surface": "국민건강보험", "slot": "public_non_private", "canonical_value": "국민건강보험", "level": 2, "priority": 9000, "category_hint": "", "need_hint": "OOS", "gate_hint": "oos", "is_protected": True, "allow_nested": False, "match_type": "contains", "source": "test"},
            {"surface": "암 초기증상", "slot": "hard_oos", "canonical_value": "암 초기증상", "level": 1, "priority": 9500, "category_hint": "", "need_hint": "질병정보탐색", "gate_hint": "oos", "is_protected": True, "allow_nested": False, "match_type": "contains", "source": "test"},
            {"surface": "보험", "slot": "insurance_intent", "canonical_value": "보험", "level": 8, "priority": 3000, "category_hint": "기타보험", "need_hint": "상품추천탐색", "gate_hint": "general", "is_protected": False, "allow_nested": False, "match_type": "contains", "source": "test"},
        ]
    return RuleBook(
        phrases=phrases,
        exact_overrides=[],
        exclusions=[],
    )


def test_action_beats_coverage():
    rb = make_rulebook()
    out = resolve_query("임플란트 치아보험 청구", rb)
    assert out["customer_need_type"] == "청구/보험금문의"
    assert out["evidence_focus"] == "청구"
    assert out["insurance_category"] == "치아보험"


def test_protected_span_blocks_subspan():
    rb = make_rulebook()
    out = resolve_query("비갱신형 암보험", rb)
    assert out["evidence_focus"] == "비갱신형"
    assert "갱신형→갱신형" not in out["evidence_trace"] or "blocked_by" in out["evidence_trace"]


def test_public_oos():
    rb = make_rulebook()
    out = resolve_query("국민건강보험 환급금", rb)
    assert out["gate_type"] == "oos"
    assert out["insurance_category"] == "null"


def test_hard_oos():
    rb = make_rulebook()
    out = resolve_query("암 초기증상", rb)
    assert out["gate_type"] == "oos"
    assert out["customer_need_type"] == "질병정보탐색"


def test_renewal_product_feature_not_action():
    rb = load_rules("configs/base_rules.xlsx")
    out = resolve_query("갱신형 암보험", rb)
    assert out["customer_need_type"] == "상품조건확인"
    assert out["evidence_focus"] == "갱신형"
    assert "action_service:갱신 blocked_by protected:갱신형" in out["evidence_trace"]


def test_base_rules_expanded_coverage_and_underwriting():
    rb = load_rules("configs/base_rules.xlsx")
    cases = {
        "암 진단비 보험": ("detailed", "암진단비보험", "보장범위확인", "암진단비"),
        "인수기준 완화 보험": ("detailed", "인수완화보험", "가입가능성확인", "인수기준완화"),
        "중입자 암보험": ("detailed", "암보험", "보장범위확인", "중입자치료비"),
        "여성 유방암 보험": ("detailed", "여성암보험", "보장범위확인", "유방암진단비"),
        "실비 청구 서류 면책기간": ("general", "실손보험", "서류/증빙확인", "서류"),
    }
    for query, expected in cases.items():
        out = resolve_query(query, rb)
        assert (out["gate_type"], out["insurance_category"], out["customer_need_type"], out["evidence_focus"]) == expected


def test_definition_policy_term_is_general():
    rb = load_rules("configs/base_rules.xlsx")
    out = resolve_query("면책기간 뜻", rb)
    assert out["gate_type"] == "general"
    assert out["customer_need_type"] == "보험용어/제도탐색"
    assert out["evidence_focus"] == "면책기간"


def test_brand_beats_category_for_need_when_no_stronger_intent():
    rb = load_rules("configs/base_rules.xlsx")
    out = resolve_query("라이나 치아보험", rb)
    assert out["insurance_category"] == "치아보험"
    assert out["customer_need_type"] == "브랜드상품확인"
    assert out["evidence_focus"] == "라이나"


def test_conflict_goes_to_review():
    rb = load_rules("configs/base_rules.xlsx")
    out = resolve_query("국민건강보험 암보험", rb)
    assert out["gate_type"] == "oos"
    assert out["review_flag"] == "Y"
    assert out["confidence_flag"] == "needs_review"


def test_colab_quick_fix_loop(tmp_path):
    rb = load_rules("configs/base_rules.xlsx")
    result_df = [{"row_id": 0, **resolve_query("스케일링 치아보험", rb)}]
    feedback_path = tmp_path / "feedback_store.xlsx"
    quick_fix_exact(
        feedback_path,
        result_df,
        row_id=0,
        gate_type="detailed",
        insurance_category="치아보험",
        customer_need_type="보장범위확인",
        evidence_focus="스케일링보장",
    )
    rb2 = load_rules("configs/base_rules.xlsx", feedback_path)
    out = resolve_query("스케일링 치아보험", rb2)
    assert out["evidence_trace"] == "exact_override:selected=true"
    assert out["evidence_focus"] == "스케일링보장"


def test_phrase_addition_and_exclusion_loop(tmp_path):
    feedback_path = tmp_path / "feedback_store.xlsx"
    quick_add_phrase(
        feedback_path,
        surface="보톡스",
        slot="coverage_focus",
        canonical_value="보톡스치료보장",
        level=5,
        priority=7500,
        category_hint="기타보험",
        need_hint="보장범위확인",
        gate_hint="detailed",
    )
    rb = load_rules("configs/base_rules.xlsx", feedback_path)
    out = resolve_query("보톡스 보험", rb)
    assert out["evidence_focus"] == "보톡스치료보장"

    quick_add_exclusion(feedback_path, surface="보톡스", block_slot="coverage_focus", reason="테스트 차단")
    rb2 = load_rules("configs/base_rules.xlsx", feedback_path)
    out2 = resolve_query("보톡스 보험", rb2)
    assert out2["evidence_focus"] != "보톡스치료보장"


def test_run_inference_outputs_required_columns(tmp_path):
    q = tmp_path / "queries.csv"
    q.write_text("query\n치아보험 추천\n국민건강보험 환급금\n", encoding="utf-8")
    out = run_inference(q, base_rules_path="configs/base_rules.xlsx", output_path=None)
    required = {
        "query", "query_norm", "gate_type", "insurance_category", "customer_need_type",
        "evidence_focus", "evidence_trace", "confidence_flag", "model_hint", "review_flag"
    }
    assert required.issubset(set(out.columns))


def test_final_rule_enrichment_latest_products_and_coverage():
    rb = load_rules("configs/base_rules.xlsx")
    cases = {
        "암주요치료비 보험": ("detailed", "암주요치료비보험", "보장범위확인", "암주요치료비"),
        "순환계치료비 보험": ("detailed", "순환계치료비보험", "보장범위확인", "순환계치료비"),
        "산후우울 보험": ("detailed", "정신건강보험", "보장범위확인", "산후우울보장"),
        "난자동결 보험": ("detailed", "난임보험", "보장범위확인", "난자동결보장"),
        "신생아중환자실 태아보험": ("detailed", "태아보험", "보장범위확인", "NICU입원비"),
        "장기요양등급 보험": ("detailed", "장기요양보험", "보장범위확인", "장기요양등급진단비"),
        "슬개골 강아지보험": ("detailed", "펫보험", "보장범위확인", "슬개골탈구보장"),
        "일상생활배상책임 보험": ("detailed", "배상책임보험", "보장범위확인", "일상생활배상책임"),
    }
    for query, expected in cases.items():
        out = resolve_query(query, rb)
        assert (out["gate_type"], out["insurance_category"], out["customer_need_type"], out["evidence_focus"]) == expected


def test_massive_rule_enrichment_v2_products_and_coverage():
    rb = load_rules("configs/base_rules.xlsx")
    cases = {
        "중입자 치료비 보험": ("detailed", "중입자치료비보험", "보장범위확인", "중입자치료비"),
        "car-t 보험": ("detailed", "항암치료비보험", "보장범위확인", "CAR-T치료비"),
        "여성 유방재건수술 보험": ("detailed", "여성건강보험", "보장범위확인", "유방재건수술비"),
        "난임 치료비 보험": ("detailed", "난임보험", "보장범위확인", "난임치료비"),
        "심장스텐트 보험": ("detailed", "심장질환보험", "보장범위확인", "심혈관중재술비"),
        "치아 치조골이식 보험": ("detailed", "치아보철보험", "보장범위확인", "치조골이식보장"),
        "항공기 지연 여행자보험": ("detailed", "여행자보험", "보장범위확인", "항공기지연보장"),
        "3n5 간편보험": ("detailed", "간편심사보험", "상품조건확인", "3N5간편심사"),
    }
    for query, expected in cases.items():
        out = resolve_query(query, rb)
        assert (out["gate_type"], out["insurance_category"], out["customer_need_type"], out["evidence_focus"]) == expected


def test_typo_similarity_brand_and_coverage():
    rb = load_rules("configs/base_rules.xlsx")

    brand = resolve_query("러이나 치아보험", rb)
    assert brand["insurance_category"] == "치아보험"
    assert brand["customer_need_type"] == "브랜드상품확인"
    assert brand["evidence_focus"] == "라이나"
    assert "match=typo" in brand["evidence_trace"]
    assert brand["review_flag"] == "Y"

    coverage = resolve_query("임프란트 치아보험", rb)
    assert coverage["insurance_category"] == "치아보험"
    assert coverage["customer_need_type"] == "보장범위확인"
    assert coverage["evidence_focus"] == "임플란트보장"
    assert "match=typo" in coverage["evidence_trace"]


def test_light_embedding_hint_does_not_fill_evidence_focus():
    rb = load_rules("configs/base_rules.xlsx")
    out = resolve_query("암 비싼 치료비 보험", rb)
    # 의미 유사 후보는 hint로만 남기고, 확정 evidence_focus를 만들지 않는 것이 원칙이다.
    # exact/contains 룰로 강하게 잡힌 단서가 없다면 review 대상으로 보낸다.
    assert "embedding:" in out["model_hint"] or out["review_flag"] == "Y"
    if "embedding:" in out["model_hint"] and "match=contains" not in out["evidence_trace"]:
        assert out["evidence_focus"] == "null"
        assert out["review_flag"] == "Y"


def test_final_v3_rule_enrichment_new_domains():
    rb = load_rules("configs/base_rules.xlsx")
    cases = {
        "키트루다 암보험": ("detailed", "암보험", "보장범위확인", "면역항암약물치료비"),
        "NGS 유전자검사 보험": ("detailed", "유전자검사보험", "보장범위확인", "NGS유전자패널검사비"),
        "BRCA 여성보험": ("detailed", "여성건강보험", "보장범위확인", "유전성여성암검사비"),
        "맘모톰 여성보험": ("detailed", "여성건강보험", "보장범위확인", "맘모톰수술비"),
        "3.4.5 간편보험": ("detailed", "간편심사보험", "상품조건확인", "345간편심사"),
        "신생아 NICU 태아보험": ("detailed", "태아보험", "보장범위확인", "NICU입원비"),
        "보이스피싱 보험": ("detailed", "보이스피싱보험", "보장범위확인", "보이스피싱피해보장"),
        "대장용종 수술비 보험": ("detailed", "수술비보험", "보장범위확인", "대장용종수술비"),
        "심장판막 보험": ("detailed", "뇌심장보험", "보장범위확인", "심장판막수술비"),
    }
    for query, expected in cases.items():
        out = resolve_query(query, rb)
        assert (out["gate_type"], out["insurance_category"], out["customer_need_type"], out["evidence_focus"]) == expected


def test_disease_benefit_context_not_join_intent():
    rb = load_rules("configs/base_rules.xlsx")
    for query in ["당뇨 진단비 보험", "당뇨 진담비 보험", "고혈압 진단비 보험", "고지혈증 진단비 보험"]:
        out = resolve_query(query, rb)
        assert out["customer_need_type"] == "보장범위확인"
        assert out["customer_need_type"] != "가입가능성확인"
        assert out["customer_need_detail"] == "질환진단비보장확인"
        assert out["evidence_focus"].endswith("진단비")


def test_disease_join_context_still_join_intent():
    rb = load_rules("configs/base_rules.xlsx")
    for query in ["당뇨 보험 가입", "당뇨 있어도 보험", "고혈압 병력 보험", "고지혈증 간편보험"]:
        out = resolve_query(query, rb)
        assert out["customer_need_type"] == "가입가능성확인"
        assert out["customer_need_detail"] in {"유병력가입가능성확인", "간편고지/심사조건확인"}


def test_customer_need_detail_column_present_in_inference(tmp_path):
    q = tmp_path / "queries.csv"
    q.write_text("query\n당뇨 진단비 보험\n", encoding="utf-8")
    out = run_inference(q, base_rules_path="configs/base_rules.xlsx", output_path=None)
    assert "customer_need_detail" in out.columns
    assert out.rows[0]["customer_need_detail"] == "질환진단비보장확인"


def test_dental_fracture_context_overrides_generic_fracture():
    sample_rulebook = load_rules("configs/base_rules.xlsx")
    cases = {
        "치아 골절 보험": ("치아보험", "보장범위확인", "치아골절보장"),
        "치아 파절 골절 진단비": ("치아보험", "보장범위확인", "치아파절진단비"),
        "영구치 파절 보험": ("치아보험", "보장범위확인", "영구치파절보장"),
        "치아 깨짐 보험": ("치아보험", "보장범위확인", "치아파절보장"),
    }
    for query, expected in cases.items():
        result = resolve_query(query, sample_rulebook)
        assert result["insurance_category"] == expected[0], result
        assert result["customer_need_type"] == expected[1], result
        assert result["evidence_focus"] == expected[2], result
        assert "골절보험" not in result["insurance_category"], result


def test_v9_care_need_detail_and_policy_context():
    rb = load_rules("configs/base_rules.xlsx")
    cases = {
        "간병인 보험 면책 기간": ("detailed", "간병인보험", "상품조건확인", "면책기간", "약관조건확인"),
        "간병인 보험 나이 제한": ("detailed", "간병인보험", "가입가능성확인", "가입연령", "가입연령조건확인"),
        "체증 형 간병인 보험": ("detailed", "간병인보험", "상품조건확인", "체증형", "체증형조건확인"),
        "간병비 보험 금액": ("general", "간병비보험", "보험료확인", "보험료", "보험료/가격확인"),
        "통합 간병 보험": ("detailed", "간병보험", "보장범위확인", "통합간병보장", "간병/요양보장확인"),
        "비 갱신 형 간병인 보험": ("detailed", "간병인보험", "상품조건확인", "비갱신형", "비갱신형조건확인"),
    }
    for query, expected in cases.items():
        out = resolve_query(query, rb)
        assert (out["gate_type"], out["insurance_category"], out["customer_need_type"], out["evidence_focus"], out["customer_need_detail"]) == expected


def test_v9_public_care_and_dental_health_insurance_context():
    rb = load_rules("configs/base_rules.xlsx")
    for query in [
        "간호 간병 통합 서비스 보험",
        "간호 간병 통합 서비스",
        "치과 건강 보험 적용",
        "건강 보험 치과",
        "임플란트 건강 보험",
        "65 세 이상 임플란트 건강 보험",
    ]:
        out = resolve_query(query, rb)
        assert out["gate_type"] == "oos"
        assert out["insurance_category"] == "null"
        assert out["customer_need_type"] == "OOS"


def test_v9_numeric_underwriting_typo_blocked_for_years_and_product_numbers():
    rb = load_rules("configs/base_rules.xlsx")
    for query in ["임플란트 가격 2025", "어금니 임플란트 가격 2025", "aig 튼튼한 new 치아 보험 2405 디시"]:
        out = resolve_query(query, rb)
        assert out["insurance_category"] != "간편심사보험"
        assert "225간편심사" not in out["evidence_trace"]
        assert "245간편심사" not in out["evidence_trace"]


def test_v9_dental_category_and_join_method():
    rb = load_rules("configs/base_rules.xlsx")
    cases = {
        "치과 보험": ("general", "치아보험", "상품추천탐색", "null"),
        "치아 교정 보험": ("detailed", "치아교정보험", "보장범위확인", "치아교정보장"),
        "치아 보험 가입 요령": ("general", "치아보험", "가입방법확인", "가입방법"),
    }
    for query, expected in cases.items():
        out = resolve_query(query, rb)
        assert (out["gate_type"], out["insurance_category"], out["customer_need_type"], out["evidence_focus"]) == expected
