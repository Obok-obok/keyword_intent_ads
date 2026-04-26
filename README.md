# v5 Phase 1 Light — 보험 검색어 이해 엔진

## 1. 프로젝트 개요

이 프로젝트는 구글 검색어, 광고 검색어, 키워드 리포트에 포함된 `query`를 입력받아 보험 검색어의 의미를 구조화하는 **검색어 이해 엔진**입니다.

이 프로그램의 목적은 검색어를 보고 아래 4가지를 판단하는 것입니다.

1. 이 검색어가 보험 광고 분석 대상인지 아닌지 판단합니다.
2. 어떤 보험 상품군에 가까운지 분류합니다.
3. 고객이 무엇을 알고 싶어 하는지 고객 니즈를 분류합니다.
4. 검색어 안에 실제로 존재하는 핵심 단서를 추출합니다.

최종 출력의 핵심 컬럼은 아래 4개입니다.

| 컬럼 | 의미 |
|---|---|
| `gate_type` | `general`, `detailed`, `oos` 중 하나 |
| `insurance_category` | 보험 상품군 |
| `customer_need_type` | 고객 니즈 |
| `evidence_focus` | 검색어 안의 핵심 단서 |

운영 검수와 피드백 루프를 위해 아래 진단 컬럼도 함께 출력합니다.

| 컬럼 | 의미 |
|---|---|
| `query` | 원본 검색어 |
| `query_norm` | 정규화 검색어 |
| `evidence_trace` | 어떤 단어가 어떤 판단 근거가 되었는지 |
| `confidence_flag` | `high`, `medium`, `low`, `needs_review` |
| `model_hint` | 모델이 보조로 제안한 라벨/확신도 |
| `review_flag` | 사람이 검토해야 하는지 여부 |

---

## 2. 기존 if 덧대기 방식의 문제

검색어 분석을 단순 `if "임플란트" in query` 방식으로 만들면 처음에는 빠르게 동작합니다. 하지만 운영 중에는 계속 예외가 쌓입니다.

예를 들어 다음 문제가 발생합니다.

- `비갱신형` 안의 `갱신형`이 같이 잡히는 부분 문자열 오탐
- `국민건강보험 환급금`이 민영 보험의 해지/환급 문의로 오탐
- `임플란트 치아보험 청구`가 보장범위확인으로 오탐
- `암 초기증상 보험`처럼 질병정보와 보험 의도가 섞인 검색어 처리 불안정
- `우리은행 보험`처럼 브랜드 오탐
- `중입자`, `CAR-T`, `카티`, `여성암`, `난임`, `325`, `355` 같은 최신/모듈형 상품 표현 누락

이 프로젝트는 단어별 if를 계속 추가하지 않습니다. 대신 아래 구조로 검색어를 해석합니다.

```text
query
→ normalize
→ Phrase Detector
→ Protected Span Builder
→ Evidence Extractor
→ Semantic Resolver
→ Contract Validator
→ final output
→ Colab Quick Fix
→ feedback_store.xlsx
→ rerun inference
```

---

## 3. 전체 동작 원리

이 프로그램은 검색어를 단순 포함어 기준으로 분류하지 않습니다.

먼저 검색어 안에서 의미 있는 phrase를 찾고, 긴 phrase 또는 오탐 위험 phrase를 보호한 뒤, 검색어 안에 실제로 존재하는 evidence만 추출합니다. 그런 다음 `Semantic Resolver`가 LEVEL 우선순위에 따라 최종 의미를 결정합니다.

예를 들어 다음 검색어를 보겠습니다.

```text
임플란트 치아보험 청구
```

검색어 안에는 세 가지 단서가 있습니다.

| 단서 | 의미 | LEVEL |
|---|---|---:|
| 청구 | Action / Service Intent | LEVEL 3 |
| 임플란트 | Coverage / Treatment | LEVEL 5 |
| 치아보험 | Category | LEVEL 6 |

LEVEL 숫자가 낮을수록 우선순위가 높습니다. 따라서 이 검색어는 `임플란트 보장범위확인`이 아니라 `청구/보험금문의`로 해석됩니다.

최종 결과는 다음과 같습니다.

| 컬럼 | 값 |
|---|---|
| `gate_type` | general |
| `insurance_category` | 치아보험 |
| `customer_need_type` | 청구/보험금문의 |
| `evidence_focus` | 청구 |

---

## 4. 검색어 해석 파이프라인

### 4.1 Phrase Detector

`Phrase Detector`는 검색어 안에서 의미 있는 표현을 찾습니다.

예:

```text
중입자 암보험
```

탐지 결과:

| surface | slot | canonical_value |
|---|---|---|
| 중입자 | coverage_focus | 중입자치료비 |
| 암보험 | insurance_category | 암보험 |

중요한 점은 업무 단어가 코드에 직접 박혀 있지 않다는 것입니다. 단어는 `configs/base_rules.xlsx` 또는 `feedback_store.xlsx`에 들어갑니다.

---

### 4.2 Protected Span Builder

`Protected Span Builder`는 오탐 위험이 큰 구간을 먼저 보호합니다.

예를 들어 `비갱신형` 안에는 `갱신형`이 포함되어 있습니다.

잘못된 방식:

```text
비갱신형 → 비갱신형, 갱신형 둘 다 탐지
```

올바른 방식:

```text
비갱신형 전체 span 보호
→ 내부의 갱신형은 무시
```

또 다른 예는 `국민건강보험 환급금`입니다. 여기에는 `보험`, `환급금`이 있지만 민영 보험 상품 문의가 아닙니다. 따라서 `국민건강보험`을 protected span으로 잡고, 내부 또는 인접 단어가 민영 보험 의도로 오탐되지 않게 합니다.

대표 protected span 예시:

| 검색어 | 보호 span | 막는 오탐 |
|---|---|---|
| 비갱신형 암보험 | 비갱신형 | 갱신형 |
| 국민건강보험 환급금 | 국민건강보험 | 민영 보험 intent |
| 고용보험 실업급여 | 고용보험 | 민영 보험 category |
| 우리은행 보험 | 우리은행 | 보험사 brand |
| 암 초기증상 | 암 초기증상 | 암보험 category |

---

### 4.3 Evidence Extractor

`Evidence Extractor`는 보호 span과 exclusion을 반영한 뒤 실제 evidence 후보를 만듭니다.

예:

```text
여성 유방암 보험
```

추출 결과:

| surface | slot | canonical_value | level |
|---|---|---|---:|
| 유방암 | coverage_focus | 유방암진단비 | 5 |
| 여성 | target_segment | 여성 | 5 |
| 보험 | insurance_intent | 보험 | 8 |

이 단계에서는 아직 최종 라벨을 결정하지 않습니다. 검색어 안에 어떤 근거가 있는지만 기록합니다.

---

### 4.4 Semantic Resolver

`Semantic Resolver`는 evidence 후보 중 최종 판단의 중심이 될 단서를 고릅니다.

우선순위는 아래와 같습니다.

```text
LEVEL 0: Exact Override
LEVEL 1: Hard OOS
LEVEL 2: Public / Non-insurance
LEVEL 3: Action / Service Intent
LEVEL 4: Policy Term / Product Feature
LEVEL 5: Coverage / Disease / Treatment
LEVEL 6: Category
LEVEL 7: Brand
LEVEL 8: Weak Intent
LEVEL 9: Fallback
```

숫자가 낮을수록 고객 의도를 더 강하게 결정합니다.

---

### 4.5 Contract Validator

마지막으로 `Contract Validator`가 출력 계약을 강제합니다.

검증 규칙:

- `gate_type`은 `general`, `detailed`, `oos` 중 하나여야 합니다.
- `insurance_category`는 허용 상품군 또는 `null`이어야 합니다.
- `customer_need_type`은 허용 니즈 중 하나여야 합니다.
- `oos`이면 `insurance_category`는 반드시 `null`입니다.
- `evidence_focus`는 검색어 안 evidence 또는 승인된 exact override에서만 나와야 합니다.
- `detailed`인데 `evidence_focus`가 비어 있으면 `review_flag=Y`로 보냅니다.

---

## 5. Semantic Resolver LEVEL별 상세 원리

### LEVEL 0. Exact Override

사람이 직접 수정한 정답입니다. 모든 자동 판단보다 우선합니다.

예를 들어 `스케일링 치아보험`이 처음에는 다음처럼 틀릴 수 있습니다.

| gate_type | insurance_category | customer_need_type | evidence_focus |
|---|---|---|---|
| general | 치아보험 | 상품추천탐색 | null |

콜랩에서 다음처럼 고칩니다.

```python
quick_fix_exact(
    row_id=12,
    gate_type="detailed",
    insurance_category="치아보험",
    customer_need_type="보장범위확인",
    evidence_focus="스케일링보장"
)
```

이후 같은 `query_norm`이 들어오면 LEVEL 0에서 바로 수정값이 적용됩니다.

---

### LEVEL 1. Hard OOS

보험 광고 분석 대상이 아닌 건강정보, 질병정보, 생활정보 검색어입니다.

대표 표현:

```text
초기증상, 증상, 원인, 수치, 식단, 치료법, 병원, 약, 검사, 운동
```

예:

| query | gate_type | insurance_category | customer_need_type | evidence_focus |
|---|---|---|---|---|
| 암 초기증상 | oos | null | 질병정보탐색 | 암 초기증상 |
| 고지혈증 수치 | oos | null | 질병정보탐색 | 고지혈증 수치 |
| 당뇨 식단 | oos | null | 질병정보탐색 | 당뇨 식단 |

단, 질병 단어가 있어도 보험 의도가 있으면 Hard OOS로 보내지 않습니다.

예:

| query | 해석 |
|---|---|
| 고지혈증 보험 가입 | 가입가능성확인 |
| 당뇨 있어도 보험 | 가입가능성확인 |
| 암 진단비 보험 | 보장범위확인 |

---

### LEVEL 2. Public / Non-insurance

보험이라는 단어가 있지만 민영 보험 상품 검색이 아닌 공공보험·제도성 검색어입니다.

대표 표현:

```text
국민건강보험, 건강보험공단, 고용보험, 산재보험, 4대보험, 자격득실확인서, 실업급여
```

예:

| query | 잘못된 위험 | 올바른 결과 |
|---|---|---|
| 국민건강보험 환급금 | 환급금 → 해지/환급문의 | oos |
| 고용보험 실업급여 | 보험 → 기타보험 | oos |
| 4대보험 계산기 | 보험료확인 오탐 | oos |

---

### LEVEL 3. Action / Service Intent

고객이 상품을 찾는 것이 아니라 절차나 업무를 처리하려는 검색어입니다.

대표 표현:

```text
청구, 보험금, 서류, 진단서, 영수증, 해지, 환급금, 계약조회, 보험증권, 갱신, 유지, 납입, 약관대출
```

예:

| query | customer_need_type | evidence_focus |
|---|---|---|
| 실비보험 청구 | 청구/보험금문의 | 청구 |
| 보험 청구 서류 | 서류/증빙확인 | 서류 |
| 보험 해지 환급금 | 해지/환급문의 | 환급금 |
| 보험 계약 조회 | 계약관리문의 | 계약조회 |
| 실비 갱신 | 갱신/유지문의 | 갱신 |

Action은 Coverage보다 우선합니다. 그래서 `임플란트 치아보험 청구`는 `보장범위확인`이 아니라 `청구/보험금문의`입니다.

---

### LEVEL 4. Policy Term / Product Feature

상품 조건, 약관 조건, 가입 구조, 인수기준 관련 표현입니다.

대표 표현:

```text
비갱신형, 갱신형, 무해지, 저해지, 순수보장형, 만기환급형,
면책기간, 감액기간, 보장개시일, 책임개시일,
간편심사, 간편고지, 유병자, 인수완화, 고지완화,
표준체, 할증체, 부담보,
325, 335, 355, 305, 31010, 3.2.5, 3.3.5, 3.5.5, 3.0.5, 3.10.10
```

예:

| query | insurance_category | customer_need_type | evidence_focus |
|---|---|---|---|
| 325 간편보험 | 간편심사보험 | 상품조건확인 | 325간편심사 |
| 355 유병자보험 | 유병자보험 | 상품조건확인 | 355간편심사 |
| 인수기준 완화 보험 | 인수완화보험 | 가입가능성확인 | 인수기준완화 |
| 비갱신형 암보험 | 암보험 | 상품조건확인 | 비갱신형 |
| 암보험 면책기간 | 암보험 | 상품조건확인 | 면책기간 |

---

### LEVEL 5. Coverage / Disease / Treatment

담보, 급부, 치료, 질환, 최신 치료비, 특정 보장 항목입니다.

보험 검색어는 상품명보다 담보명으로 들어오는 경우가 많습니다. 예를 들어 사용자는 `암보험`보다 `중입자치료비`, `표적항암`, `질병수술비`, `유방암`, `난임`처럼 구체적인 보장 항목을 검색할 수 있습니다.

대표 영역:

```text
치아 치료, 암 진단/치료, 최신 항암 치료, 중입자/양성자 치료,
질병수술/상해수술, 입원/간병, 뇌심장 질환,
여성 특화 질환, 임신/출산/난임, 정신건강,
후유장해, 운전자 담보, 생활위험 담보
```

예:

| query | insurance_category | customer_need_type | evidence_focus |
|---|---|---|---|
| 중입자 암보험 | 암보험 | 보장범위확인 | 중입자치료비 |
| 카티 치료비 보험 | 암보험 | 보장범위확인 | 카티항암약물치료비 |
| 여성 유방암 보험 | 여성암보험 | 보장범위확인 | 유방암진단비 |
| 질병수술 보험 | 질병수술비보험 | 보장범위확인 | 질병수술비 |
| 임플란트 치아보험 | 치아보험 | 보장범위확인 | 임플란트보장 |

---

### LEVEL 6. Category

보험 상품군입니다.

확장 상품군은 다음을 포함합니다.

```text
암보험, 치아보험, 실손보험, 간병보험, 치매보험, 건강보험, 종합건강보험,
간편보험, 간편심사보험, 유병자보험, 인수완화보험, 시니어보험,
수술비보험, 질병수술비보험, 상해수술비보험, 입원비보험, 간병비보험,
진단비보험, 암진단비보험, 뇌심장보험, 3대질병보험, 2대질병보험,
질병보험, 상해보험, 후유장해보험, 질병후유장해보험, 상해후유장해보험,
여성보험, 여성건강보험, 여성암보험, 임신출산보험, 난임보험,
어린이보험, 태아보험, 종신보험, 정기보험, 연금보험, 저축보험, 변액보험,
운전자보험, 자동차보험, 여행자보험, 화재보험, 펫보험, 배상책임보험,
기타보험, null
```

Category만 있으면 보통 `general`입니다.

예:

| query | 결과 |
|---|---|
| 치아보험 | general / 치아보험 / 상품추천탐색 / null |
| 암보험 추천 | general / 암보험 / 상품추천탐색 / null |
| 여성보험 | general / 여성보험 / 상품추천탐색 / null |

---

### LEVEL 7. Brand

보험사 또는 브랜드명입니다.

대표 표현:

```text
라이나, 삼성화재, 현대해상, DB손해보험, KB손해보험, 메리츠화재,
한화손해보험, 흥국화재, 교보생명, 삼성생명, 한화생명, 신한라이프,
동양생명, 미래에셋생명
```

예:

| query | 결과 |
|---|---|
| 라이나 치아보험 | 브랜드상품확인 / 라이나 |
| 삼성화재 운전자보험 | 브랜드상품확인 / 삼성화재 |
| 현대해상 실비 | 브랜드상품확인 / 현대해상 |

브랜드는 오탐이 많으므로 exclusion을 함께 사용합니다. 예를 들어 `우리은행`, `수협`, `신협`, `라이프` 단독 표현은 보험사 브랜드로 해석하지 않게 막습니다.

---

### LEVEL 8. Weak Intent

추천, 비교, 가격, 보험료, 견적, 상담 같은 약한 탐색 의도입니다.

대표 표현:

```text
추천, 순위, 좋은, 비교, 가격, 보험료, 견적, 상담, 가입, 가입방법, 싼, 저렴한
```

예:

| query | 결과 |
|---|---|
| 치아보험 추천 | 상품추천탐색 |
| 암보험 비교 | 상품비교 |
| 실비보험 가격 | 보험료확인 |
| 암보험 견적 | 견적/상담요청 |

Weak Intent만 있고 category가 없으면 confidence를 낮추고 review 대상으로 보냅니다.

---

### LEVEL 9. Fallback

명확한 phrase가 없거나 판단이 불안정한 경우입니다.

예:

| query | 처리 |
|---|---|
| 좋은 보험 | general / 기타보험 / 상품추천탐색 / null / review_flag=Y |
| 보장 좋은 상품 | general / 기타보험 / 상품추천탐색 / null / review_flag=Y |
| 보험 | general / 기타보험 / 상품추천탐색 / null / review_flag=Y |

Fallback 영역은 피드백 루프를 통해 개선합니다.

---

## 6. 상품·담보 해석 3층 구조

이 프로젝트는 보험 검색어를 3층으로 해석합니다.

| 층 | 의미 | 예 |
|---|---|---|
| 1층 | insurance_category | 암보험, 여성보험, 간편심사보험 |
| 2층 | product_feature / underwriting_type | 비갱신형, 무해지, 간편고지, 325, 355, 인수완화 |
| 3층 | coverage_focus | 중입자치료비, 유방암진단비, 질병수술비, 임플란트보장 |

예:

| query | category | feature | coverage | 최종 evidence_focus |
|---|---|---|---|---|
| 325 간편보험 | 간편심사보험 | 325간편심사 | - | 325간편심사 |
| 중입자 암보험 | 암보험 | - | 중입자치료비 | 중입자치료비 |
| 여성 유방암 보험 | 여성암보험 | - | 유방암진단비 | 유방암진단비 |
| 비갱신형 질병수술비 보험 | 질병수술비보험 | 비갱신형 | 질병수술비 | 비갱신형 |

마지막 예시는 LEVEL 4인 `비갱신형`이 LEVEL 5인 `질병수술비`보다 우선하므로 `evidence_focus=비갱신형`입니다. 다만 `evidence_trace`에는 둘 다 남습니다.

---

## 7. 최신 상품/담보 표현 반영

검색어 사전은 전통 상품군뿐 아니라 최근 자주 등장하는 모듈형/담보형 표현까지 반영합니다.

### 7.1 최신 암 치료/암 주요치료비 담보

```text
암주요치료비, 암통합치료비, 전이암생활비, 재발암진단비, 잔존암치료비,
특정암진단비, 고액치료비암진단비, 암치료비, 암치료지원금,
표적항암약물치료비, 항암약물치료비, 항암방사선치료비, 면역항암치료비,
항암호르몬치료비, 카티항암약물치료비, CAR-T치료비, 카티치료비, 킴리아,
중입자치료비, 항암중입자치료비, 중입자방사선치료비, 양성자치료비,
세기조절방사선치료비, 정위적방사선치료비, 토모테라피치료비,
다빈치로봇수술비, 로봇수술비, 하이푸치료비
```

예를 들어 `중입자 암보험`은 category가 `암보험`이고 evidence_focus는 `중입자치료비`입니다. `암주요치료비 보험`은 category가 `암주요치료비보험`이고 evidence_focus는 `암주요치료비`입니다.

### 7.2 순환계/뇌심장 치료비 담보

```text
순환계치료비, 순환계질환보장, 심혈관치료비, 뇌혈관치료비,
급성심근경색진단비, 협심증진단비, 부정맥진단비, 심부전진단비,
대동맥류진단비, 심장판막질환수술비, 혈전용해치료비
```

`순환계치료비 보험`처럼 상품군 표현이 약해도 coverage_focus가 먼저 잡히면 category_hint로 `순환계치료비보험` 또는 `뇌심장보험`을 보완합니다.

### 7.3 여성 생애주기/난임·임신·정신건강 담보

```text
유갑생, 유방갑상선보장, 여성생식기질환보장, 여성암진단비, 유방암진단비,
재진단유방암, 유방암반복보장, 유방재건수술비, 유방절제수술비,
자궁암진단비, 난소암진단비, 자궁경부암진단비, 갑상선암진단비,
자궁근종수술비, 난소낭종수술비, 자궁내막증보장, 골다공증진단비,
갱년기질환보장, 류마티스관절염보장, 난임치료비, 난임진단비,
가임력보존, 난자동결보장, 배아동결보장, 임신질환보장, 임신중독증보장,
출산지원금, 출산축하금, 제왕절개수술비, 다태아출산보장,
산후우울보장, 정신건강보장, 우울증보장, 공황장애보장,
비대성흉터진단비, 켈로이드흉터치료비, 흉터치료비
```

`여성 유방암 보험`은 target_segment인 `여성`과 coverage_focus인 `유방암`이 같이 잡히며, 최종 evidence_focus는 더 구체적인 `유방암진단비`가 됩니다. `산후우울 보험`은 여성건강보험이 아니라 정신건강보험 category_hint를 사용할 수 있습니다.

### 7.4 수술/입원/간병/장기요양 담보

```text
질병수술비, 상해수술비, 종수술비, 1-5종수술비, N대수술비,
백내장수술비, 대장용종수술비, 갑상선수술비, 입원일당, 질병입원일당,
상해입원일당, 상급병실료, 간병비, 간병인사용일당, 요양병원간병비,
치매간병비, 장기요양진단비, 장기요양등급진단비, 요양등급진단비
```

### 7.5 태아·어린이·시니어 담보

```text
신생아질환보장, 선천이상수술비, 저체중아입원비, 미숙아입원비,
NICU입원비, 성조숙증보장, 성장치료보장, 아토피보장, 소아암진단비,
ADHD보장, 자폐스펙트럼보장, 치매진단비, 경도치매진단비,
중증치매진단비, 파킨슨병진단비, 루게릭병진단비
```

### 7.6 생활위험·펫·여행·배상책임 담보

```text
대상포진진단비, 통풍진단비, 독감치료비, 폐렴진단비,
일상생활배상책임, 가족배상책임, 누수배상책임, 임대인배상책임,
화재손해보장, 주택화재보장, 항공기지연보장, 휴대품손해보장,
해외의료비, 여행중단보장, 슬개골탈구보장, 반려동물치료비,
반려견보험, 반려묘보험, 펫치과치료비, 펫피부질환보장
```

### 7.7 운전자 담보

```text
운전자벌금, 교통사고처리지원금, 변호사선임비, 자동차부상치료비,
면허정지위로금, 면허취소위로금, 교통사고합의금, 스쿨존사고, 민식이법
```

---

## 8. 모델의 역할

이 프로젝트에서 모델은 최종 판단자가 아닙니다.

모델은 다음 역할만 수행합니다.

- 룰 근거가 약한 검색어의 `customer_need_type` 보조 제안
- 룰 결과와 모델 결과가 충돌하는 경우 review 대상 선별
- `model_hint` 컬럼에 보조 제안과 확신도 기록

권장 모델은 Phase 1 기준으로 가볍게 유지합니다.

```text
TF-IDF + LogisticRegression
```

모델은 아래 라벨만 학습합니다.

```text
gate_type
insurance_category
customer_need_type
```

모델은 `evidence_focus`를 학습하거나 생성하지 않습니다.

---

## 9. 피드백 루프

피드백은 코드 수정 없이 작동해야 합니다.

### 9.1 quick_fix_exact

특정 검색어 하나를 정확히 고칩니다.

```python
quick_fix_exact(
    row_id=15,
    gate_type="detailed",
    insurance_category="치아보험",
    customer_need_type="보장범위확인",
    evidence_focus="스케일링보장"
)
```

저장 위치:

```text
feedback_store.xlsx / exact_overrides
```

같은 query가 다시 들어오면 LEVEL 0에서 바로 수정값이 적용됩니다.

---

### 9.2 quick_add_phrase

새로운 단어를 일반화합니다.

```python
quick_add_phrase(
    surface="스케일링",
    slot="coverage_focus",
    canonical_value="스케일링보장",
    level=5,
    priority=7500,
    category_hint="치아보험",
    need_hint="보장범위확인",
    gate_hint="detailed",
    is_protected="N"
)
```

이후 아래 검색어가 같이 개선됩니다.

```text
스케일링 치아보험
스케일링 보험
치아보험 스케일링
스케일링 보장
```

---

### 9.3 quick_add_protected_span

오탐 방지용 보호 구간을 추가합니다.

```python
quick_add_protected_span(
    surface="국민건강보험",
    slot="public_non_private",
    canonical_value="국민건강보험",
    level=2,
    priority=9000,
    gate_hint="oos",
    need_hint="OOS"
)
```

---

### 9.4 quick_add_exclusion

특정 단어가 특정 slot으로 해석되지 않게 막습니다.

```python
quick_add_exclusion(
    surface="우리은행",
    block_slot="brand_name",
    reason="은행명이지 보험사 브랜드가 아님"
)
```

---

## 10. Colab 실행 방법

### Step 1. 패키지 업로드

```python
from google.colab import files
uploaded = files.upload()
```

프로젝트 zip을 업로드한 뒤 압축을 풉니다.

```python
import zipfile, pathlib
zip_path = "v5_phase1_light_release.zip"
with zipfile.ZipFile(zip_path, "r") as z:
    z.extractall("/content/v5_phase1_light")
```

### Step 2. 의존성 설치

```python
%cd /content/v5_phase1_light/v5_phase1_light
!pip install -r requirements.txt
```

### Step 3. 샘플 추론

```python
from src.infer import run_inference

result = run_inference(
    query_path="sample_data/sample_queries.xlsx",
    base_rules_path="configs/base_rules.xlsx",
    feedback_store_path=None,
    model_path=None,
    output_path="outputs/inference_result.xlsx",
)
result.head(20)
```

### Step 4. 검수 대상 확인

```python
result[result["review_flag"] == "Y"].head(50)
```

### Step 5. Quick Fix

```python
from src.feedback import quick_fix_exact, quick_add_phrase

quick_fix_exact(
    feedback_store_path="outputs/feedback_store_updated.xlsx",
    result_df=result,
    row_id=0,
    gate_type="detailed",
    insurance_category="치아보험",
    customer_need_type="보장범위확인",
    evidence_focus="스케일링보장",
    memo="콜랩에서 직접 수정"
)
```

### Step 6. 재추론

```python
result2 = run_inference(
    query_path="sample_data/sample_queries.xlsx",
    base_rules_path="configs/base_rules.xlsx",
    feedback_store_path="outputs/feedback_store_updated.xlsx",
    output_path="outputs/inference_result_updated.xlsx",
)
result2.head(20)
```

---

## 11. 예상 문제와 해결 방식

| 문제 | 예 | 해결 방식 |
|---|---|---|
| 부분 문자열 오탐 | 비갱신형 → 갱신형 오탐 | protected span |
| 공공보험 오탐 | 국민건강보험 환급금 | public_non_private level |
| Action/Coverage 충돌 | 임플란트 치아보험 청구 | LEVEL 3 Action 우선 |
| 질병정보/보험의도 혼재 | 고지혈증 보험 가입 | 보험 의도 있으면 Hard OOS 제외 |
| 브랜드 오탐 | 우리은행 보험 | exclusion |
| 최신 담보 누락 | 중입자 암보험 | quick_add_phrase |

---

## 12. 파일 구조

```text
v5_phase1_light/
  README.md
  docs/V5_PHASE1_DESIGN_CONTRACT.md
  notebooks/v5_phase1_colab.ipynb
  src/
    normalize.py
    rules.py
    infer.py
    feedback.py
    model.py
    eval.py
  scripts/
    infer.py
    train_model.py
    run_tests.py
  configs/base_rules.xlsx
  configs/feedback_store_template.xlsx
  sample_data/sample_queries.xlsx
  sample_data/sample_gold.xlsx
  tests/
```

---

## 13. 평가 지표

- `gate_accuracy`
- `category_accuracy`
- `need_accuracy`
- `focus_accuracy`
- `focus_null_accuracy`
- `focus_overfill_rate`
- `oos_false_positive_rate`
- `public_oos_accuracy`
- `feedback_regression_pass_rate`

가장 중요한 것은 단순 정확도만이 아닙니다. **검색어에 없는 evidence를 만들지 않는 것**이 중요합니다.

---

## 14. 한계와 향후 개선

Phase 1은 가볍고 운영 친화적인 구조를 우선합니다.

향후 개선 방향:

- 리뷰 데이터가 충분히 쌓이면 모델 성능 개선
- NER 또는 KoELECTRA/KoBERT 기반 보조 모델 추가
- phrase priority 자동 추천
- 대량 키워드 클러스터링
- 애드그룹 자동 생성 Phase 2 연결
- 상품/약관 매핑 Phase 별도 확장


---

## 재감리 보강 사항

오류 보고 이후 재검수에서 `면책기간 뜻` 같은 보험용어 검색어의 category 보정 누락과 Excel 입출력 안정성 이슈를 보강했다.

- 보험용어/제도탐색 검색어는 상품군이 명확하지 않아도 `기타보험`으로 보완할 수 있다.
- 룰 파일과 피드백 파일의 xlsx 입출력은 pandas.read_excel 의존을 줄이고 openpyxl 직접 처리 방식으로 보강했다.
- 이는 Colab/로컬 환경 차이로 인한 Excel engine 문제를 줄이기 위한 안정화 조치다.


---

## 대폭 룰 보강 v2: 상품·담보·인수기준 사전 확장

이번 보강은 구조 변경이 아니라 `base_rules.csv` / `base_rules.xlsx`의 phrase 사전 확장이다. 핵심은 최신 보험 검색어가 전통 상품명보다 담보명·치료비·인수기준·생애주기 표현으로 들어오는 현상을 반영하는 것이다.

### 보강 범위

- 암 치료비: 암주요치료비, 암통합치료비, 표적항암, 면역항암, CAR-T/카티, 중입자, 양성자, 세기조절방사선, 로봇수술, 하이푸 등
- 여성/생애주기: 유방암, 유방재건, 자궁·난소 질환, 난임, 시험관, 난자동결, 임신중독증, 출산, 산후우울, 여성범죄피해·법률비용 등
- 태아/어린이: 선천이상, 저체중아, NICU, 성조숙증, 성장호르몬, ADHD, 자폐, 소아암 등
- 순환계/성인질환: 뇌혈관, 심장질환, 순환계치료비, 협심증, 부정맥, 심부전, 스텐트, 고혈압·당뇨·고지혈증 등
- 수술/입원/간병: 질병수술, 상해수술, N대수술, 입원일당, 상급병실료, 간병인사용일당, 장기요양등급, 치매등급 등
- 치아: 치아보철/보존, 치조골이식, 인레이/온레이, 치주질환, 파노라마/CT 등
- 운전자/생활/펫/여행/재물/배상: 변호사선임비, 자동차부상치료비, 슬개골탈구, 항공기지연, 누수, 풍수해, 일상생활배상책임 등
- 상품조건/인수기준: 315/325/335/345/355/3N5/3N10, 무심사, 초간편, 인수완화, 부담보, 고지의무, 세만기/년만기, 납입면제 등

### README 해석 원칙

검색어가 `중입자 치료비 보험`이면 category는 `중입자치료비보험` 또는 `암보험` 계열로 보완하고, 핵심 단서인 `evidence_focus`는 `중입자치료비`로 남긴다. 검색어가 `3N5 간편보험`이면 category는 `간편심사보험`, evidence_focus는 `3N5간편심사`가 된다. 검색어가 `여성 유방재건수술 보험`이면 category는 `여성건강보험`, evidence_focus는 `유방재건수술비`가 된다.

### 참고 트렌드 출처

- 2026년 여성보험은 난임·출산·정신건강·여성 사회위험 보장까지 확장되는 흐름이 확인된다.
- 2025~2026년 간편보험은 3.N.5처럼 고지 기간을 더 유연하게 세분화하는 방향으로 확장되고 있다.
- 2025년 이후 건강보험 판매 현장에서는 암주요치료비·순환계치료비·고액 치료비형 담보가 중요 키워드로 언급된다.



---

## 25. Similarity Matcher 보강 — 오탈자/띄어쓰기 보완

이번 리팩토링에서는 기존 지도학습 보조 모델을 필수 구성요소로 두지 않고, **경량 Similarity Matcher**를 추가했습니다. 목적은 모델이 검색어 의미를 마음대로 해석하게 하는 것이 아니라, 룰 사전 매칭의 사각지대를 아주 좁게 보완하는 것입니다.

### 25.1 Similarity Matcher가 하는 일

Similarity Matcher는 두 가지 역할만 합니다.

| 역할 | 설명 | evidence_focus 확정 여부 |
|---|---|---|
| Typo Similarity | `러이나→라이나`, `임프란트→임플란트`처럼 짧은 오탈자를 보정 | 매우 확실하면 채움 |
| Light Embedding Hint | `암 비싼 치료비 보험`처럼 직접 단어가 없지만 유사한 담보 후보를 제안 | 채우지 않고 `model_hint`에만 기록 |

중요한 원칙은 다음과 같습니다.

```text
Similarity Matcher는 최종 판단자가 아니다.
Hard OOS / Public / Non-insurance는 Similarity가 뒤집을 수 없다.
의미 유사 후보만으로는 evidence_focus를 확정하지 않는다.
오탈자 후보는 evidence_trace에 match=typo와 score를 남긴다.
```

### 25.2 오탈자 보정 원리

기존 exact/contains 매칭은 `라이나`는 잡지만 `러이나`는 잡지 못합니다.  
이번 버전은 한글 자모 분해 기반 문자 유사도를 사용합니다.

예를 들어:

```text
라이나 → ㄹㅏㅇㅣㄴㅏ
러이나 → ㄹㅓㅇㅣㄴㅏ
```

한 글자의 모음만 다르므로 유사도가 높게 계산됩니다.  
따라서 아래처럼 후보를 만들 수 있습니다.

| query | detected surface | canonical_value | match_type | score |
|---|---|---|---|---:|
| 러이나 치아보험 | 러이나 | 라이나 | typo | 0.83 이상 |
| 임프란트 치아보험 | 임프란트 | 임플란트보장 | typo | 0.78 이상 |
| 매리츠 운전자보험 | 매리츠 | 메리츠화재 | typo | threshold 이상 |

결과 예시:

| 컬럼 | 값 |
|---|---|
| `query` | 러이나 치아보험 |
| `insurance_category` | 치아보험 |
| `customer_need_type` | 브랜드상품확인 |
| `evidence_focus` | 라이나 |
| `confidence_flag` | medium |
| `review_flag` | Y |
| `evidence_trace` | `brand_name:러이나→라이나|match=typo|score=0.xx|selected=true` |

초기 운영에서는 오탈자 보정 결과도 `review_flag=Y`로 두어 사람이 확인할 수 있게 합니다.

### 25.3 Light Embedding Hint 원리

이 프로젝트는 무거운 문장 임베딩 모델을 기본 설치하지 않습니다. 대신 Colab에서 바로 동작하는 **char n-gram vector similarity**를 사용해, 의미가 비슷해 보이는 후보를 `model_hint`에만 남깁니다.

예:

```text
암 비싼 치료비 보험
```

이 검색어가 룰 surface와 정확히 일치하지 않더라도, 룰 사전의 `embedding_text`와 유사하면 다음과 같은 힌트를 남깁니다.

```text
model_hint = embedding:coverage_focus=암주요치료비|score=0.84|hint_only=true
```

하지만 이 경우에는 `evidence_focus`를 바로 `암주요치료비`로 채우지 않습니다.

권장 출력:

| 컬럼 | 값 |
|---|---|
| `insurance_category` | 암보험 또는 기타보험 |
| `customer_need_type` | 보장범위확인 또는 상품추천탐색 |
| `evidence_focus` | null |
| `model_hint` | embedding 후보 |
| `confidence_flag` | needs_review |
| `review_flag` | Y |

이 설계는 “애매하면 답을 만들지 않는다”는 원칙을 지키기 위한 것입니다.

### 25.4 룰 사전의 추가 컬럼

`base_rules.xlsx`와 `feedback_store.xlsx`의 `phrase_additions`에는 아래 컬럼이 추가되었습니다.

| 컬럼 | 설명 |
|---|---|
| `use_typo` | 오탈자 보정 후보로 사용할지 여부 |
| `typo_threshold` | 오탈자 후보 채택 기준 |
| `use_embedding` | 유사도 힌트 후보로 사용할지 여부 |
| `embedding_text` | 유사도 계산에 사용할 설명 문장 |
| `embedding_threshold` | 유사도 힌트 표시 기준 |

예시:

| surface | slot | canonical_value | use_typo | typo_threshold | use_embedding | embedding_text |
|---|---|---|---|---:|---|---|
| 라이나 | brand_name | 라이나 | Y | 0.82 | N |  |
| 임플란트 | coverage_focus | 임플란트보장 | Y | 0.78 | Y | 치아 임플란트 보철 치료 보장 |
| 암주요치료비 | coverage_focus | 암주요치료비 | Y | 0.78 | Y | 암 고액 치료비 주요 치료비 보장 |

---

## 26. Colab 노트북 풀버전 실행 가이드

`notebooks/v5_phase1_colab.ipynb`는 운영자가 파일 경로를 직접 고치지 않아도 되도록 구성했습니다.

### 26.1 노트북이 자동으로 처리하는 것

```text
프로젝트 zip 업로드
→ 자동 압축 해제
→ 프로젝트 루트 자동 탐지
→ query 파일 업로드
→ base_rules.xlsx 경로 자동 설정
→ feedback_store.xlsx 템플릿 자동 복사
→ 추론 실행
→ 결과/리뷰 템플릿 다운로드
→ Quick Fix 반영
→ 재추론
→ 업데이트 결과 다운로드
```

### 26.2 주요 출력 파일

| 파일 | 설명 |
|---|---|
| `inference_result.xlsx` | 전체 검색어 추론 결과 |
| `review_template.xlsx` | 대량 검수용 템플릿 |
| `feedback_store.xlsx` | Quick Fix 누적 피드백 |
| `inference_result_updated.xlsx` | 피드백 반영 후 재추론 결과 |

### 26.3 Quick Fix 방식

#### 1) 특정 검색어 하나 고정

```python
quick_fix_exact(
    feedback_store_path=FEEDBACK_STORE_PATH,
    result_df=result_df,
    row_id=0,
    gate_type="general",
    insurance_category="치아보험",
    customer_need_type="브랜드상품확인",
    evidence_focus="라이나",
    memo="러이나 오탈자 검수 후 라이나로 확정"
)
```

이 방식은 `exact_overrides`에 저장되며, 같은 검색어가 다시 들어오면 LEVEL 0에서 즉시 적용됩니다.

#### 2) phrase 추가로 일반화

```python
quick_add_phrase(
    feedback_store_path=FEEDBACK_STORE_PATH,
    surface="스케일링",
    slot="coverage_focus",
    canonical_value="스케일링보장",
    level=5,
    priority=7500,
    category_hint="치아보험",
    need_hint="보장범위확인",
    gate_hint="detailed",
    use_typo="Y",
    use_embedding="Y",
    embedding_text="치아 스케일링 치석 제거 치과 치료 보장"
)
```

이 방식은 `phrase_additions`에 저장되며, 유사 검색어까지 개선합니다.

#### 3) 오탐 차단

```python
quick_add_exclusion(
    feedback_store_path=FEEDBACK_STORE_PATH,
    surface="우리은행",
    block_slot="brand_name",
    reason="은행명이지 보험사 브랜드가 아님"
)
```

### 26.4 운영상 권장 방식

```text
1. 먼저 rule-only + similarity 후보로 전체 검색어를 추론한다.
2. review_flag=Y 행만 우선 확인한다.
3. 같은 검색어 반복 오류는 quick_fix_exact로 고정한다.
4. 새로운 담보/상품 표현은 quick_add_phrase로 일반화한다.
5. 오탐은 quick_add_protected_span 또는 quick_add_exclusion으로 차단한다.
6. 재추론해서 반영 여부를 바로 확인한다.
```

---

## 27. 지도학습 모델 정책 변경

기존 `TF-IDF + LogisticRegression` 모델은 선택 기능으로 남아 있지만, Phase 1의 기본 경로에서는 사용하지 않습니다.

이번 리팩토링의 기본 정책은 다음입니다.

```text
Rule-first
+ Typo Similarity
+ Light Embedding Hint
+ Semantic Resolver
+ Feedback Loop
```

정답지 데이터가 충분하지 않은 초기 단계에서는 지도학습 모델보다 이 구조가 더 안전합니다.  
향후 Quick Fix와 대량 리뷰로 approved gold가 충분히 쌓이면 지도학습 모델을 다시 보조 기능으로 붙일 수 있습니다.

---

## 20. 최종 리팩토링 반영 사항: Similarity Matcher와 Colab 운영 풀버전

이번 최종본은 기존 지도학습 모델을 필수로 두지 않습니다. 검색어 이해의 기본 축은 여전히 `룰 사전 + Protected Span + Semantic Resolver + Contract Validator`입니다. Similarity Matcher는 이 구조를 대체하지 않고, 사전 매칭의 빈틈을 작게 보완합니다.

### 20.1 Similarity Matcher의 역할은 작다

Similarity Matcher는 두 가지 경우에만 사용합니다.

| 구분 | 목적 | evidence_focus 채움 여부 | 운영 처리 |
|---|---|---:|---|
| typo / compact_contains | 오탈자, 띄어쓰기 흔들림 보정 | 확실하면 채움 | 초기에는 review_flag=Y 또는 medium |
| embedding hint | 의미가 비슷해 보이는 후보 제안 | 기본적으로 채우지 않음 | model_hint에만 남기고 review_flag=Y |

예를 들어 `러이나 치아보험`은 `라이나`의 짧은 브랜드 오탈자입니다. 이 경우 `brand_name:러이나→라이나|match=typo|score=...`처럼 trace를 남기고 `evidence_focus=라이나`를 채울 수 있습니다. 반대로 `암 비싼 치료비 보험`은 `암주요치료비`와 의미가 가까울 수 있지만, 검색어에 직접 `암주요치료비`가 있는 것은 아니므로 `model_hint`에 후보만 남기고 `evidence_focus`는 확정하지 않습니다.

```text
러이나 치아보험
→ brand_name:러이나→라이나|match=typo|score=0.91|selected=true
→ evidence_focus = 라이나
→ review_flag = Y
```

```text
암 비싼 치료비 보험
→ model_hint = embedding:coverage_focus=암주요치료비|score=0.84|hint_only=true
→ evidence_focus = null
→ review_flag = Y
```

이 정책의 핵심은 다음입니다.

```text
오탈자는 보정한다.
애매한 의미 추론은 정답을 만들지 않는다.
Hard OOS / Public 판단은 similarity가 뒤집을 수 없다.
```

### 20.2 match_score와 priority의 차이

`match_score`는 검색어와 룰 surface가 얼마나 잘 맞는지를 뜻합니다. `priority`는 매칭된 후보 중 업무적으로 무엇이 더 중요한지를 뜻합니다.

| 값 | 의미 |
|---|---|
| level | Action, Coverage, Category 같은 업무 의미 우선순위. 숫자가 낮을수록 우선 |
| priority | 같은 level 안에서 더 중요한 룰을 고르는 세부 우선순위 |
| match_score | exact/contains/typo/embedding 매칭 강도 |
| surface length | 긴 phrase를 짧은 phrase보다 우선하기 위한 보조 기준 |

정렬 기준은 다음입니다.

```python
(level 낮은 순, priority 높은 순, match_score 높은 순, surface 길이 긴 순)
```

단, `brand + category` 같이 조합적으로 의미가 분명한 경우에는 Resolver가 고객 니즈를 보정할 수 있습니다. 예를 들어 `라이나 치아보험`은 category가 LEVEL 6이고 brand가 LEVEL 7이지만, 고객 니즈는 `브랜드상품확인`으로 보는 것이 맞습니다.

### 20.3 룰 사전 보강 범위

최종본의 `base_rules.csv/xlsx`는 전통 상품군뿐 아니라 최신 검색 트렌드형 담보와 모듈형 상품 표현까지 확장했습니다.

보강 영역은 다음과 같습니다.

- 암 주요치료비, 중입자, 양성자, CAR-T/카티, 표적항암, 면역항암, 로봇수술, NGS 유전자검사
- 여성보험, 여성암, 유방재건, 맘모톰, 하이푸, 난임, 난자동결, 임신중독증, 산후우울, 갱년기, 골다공증
- 3N5, 325, 355, 초간편, 무심사, 간편고지, 건강고지형, 무사고 전환, 표준체 전환
- 질병수술비, 136대수술, 통합치료비, 순환계치료비, 뇌심장 중재술, 심장스텐트, 혈전제거술
- 태아, NICU, 선천이상, 미숙아, 어린이 ADHD/성조숙증/아토피/소아암
- 치아보철/보존/촬영/치조골이식/레진/인레이/온레이/치주질환
- 운전자 벌금, 변호사선임비, 교통사고처리지원금, 배상책임, 누수, 보이스피싱, 여행 지연, 펫 슬개골/치과/MRI

### 20.4 Colab 실행은 운영 흐름 그대로 구성한다

노트북은 실무 운영자가 다음 흐름대로 실행할 수 있게 구성되어 있습니다.

```text
1. 프로젝트 zip 업로드
2. 프로젝트 루트 자동 탐지
3. 검색어 xlsx/csv 업로드
4. base_rules.xlsx 자동 탐지
5. feedback_store.xlsx 생성 또는 기존 파일 업로드
6. 전체 추론 실행
7. inference_result.xlsx / review_template.xlsx 다운로드
8. review_flag=Y 우선 확인
9. quick_fix_exact / quick_add_phrase / quick_add_protected_span / quick_add_exclusion 실행
10. 재추론
11. updated_result / updated_review / feedback_store 다운로드
12. 필요 시 전체 outputs를 zip으로 묶어 다운로드
```

피드백 루프는 엑셀 수정을 필수로 하지 않습니다. 콜랩에서 row_id를 보고 바로 고칠 수 있습니다. 다만 대량 검수 시에는 `review_template.xlsx`를 수정한 뒤 `compile_review_template`로 한 번에 반영할 수 있습니다.

### 20.5 Colab Quick Fix 예시

```python
quick_fix_exact(
    feedback_store_path=FEEDBACK_STORE_PATH,
    result_df=result_df,
    row_id=12,
    gate_type="detailed",
    insurance_category="치아보험",
    customer_need_type="보장범위확인",
    evidence_focus="스케일링보장",
    memo="스케일링 치아보험 수동 확정"
)
```

```python
quick_add_phrase(
    feedback_store_path=FEEDBACK_STORE_PATH,
    surface="맘모톰",
    slot="coverage_focus",
    canonical_value="맘모톰수술비",
    level=5,
    priority=7700,
    category_hint="여성건강보험",
    need_hint="보장범위확인",
    gate_hint="detailed",
    use_typo="Y",
    use_embedding="Y",
    embedding_text="여성 유방 양성종양 맘모톰 수술 보장"
)
```

```python
quick_add_exclusion(
    feedback_store_path=FEEDBACK_STORE_PATH,
    surface="우리은행",
    block_slot="brand_name",
    reason="은행명이지 보험사 브랜드가 아님"
)
```

### 20.6 언제 답을 내지 않는가?

아래 조건에서는 억지로 evidence를 만들지 않습니다.

- 의미 유사도 후보만 있고 직접 evidence가 없는 경우
- Hard OOS와 보험 의도가 섞인 경우
- Public / Non-insurance와 민영 보험 category가 충돌하는 경우
- category 없이 weak intent만 있는 경우
- typo score가 낮거나 후보가 여러 개로 갈리는 경우

이 경우 결과는 다음처럼 보수적으로 나옵니다.

```text
evidence_focus = null
confidence_flag = needs_review
review_flag = Y
model_hint = 후보 표시
```

---

## 21. 마감 검수 기준

최종본은 다음 기준을 통과해야 합니다.

| 검수 항목 | 통과 기준 |
|---|---|
| 구조 | 업무 단어가 코드 if로 추가되지 않고 base_rules/feedback_store에 있음 |
| 룰 | 최신 상품/담보/여성/간편심사/운전자/펫/생활위험 표현 포함 |
| Similarity | 오탈자는 보정하되 애매한 의미 유사는 hint_only 처리 |
| OOS | Hard OOS/Public은 similarity가 뒤집지 못함 |
| Colab | 업로드, 자동 경로, 추론, 다운로드, Quick Fix, 재추론이 한 노트북에 있음 |
| 피드백 | feedback_store.xlsx 저장 후 다음 추론에 즉시 반영 |
| 출력 | 10개 출력 컬럼 유지 |
| 테스트 | pytest, CLI, 대표 공격 케이스 통과 |

---

# v4 속도 개선 및 기타보험 오탐 보정 메모

이번 보강에서는 실제 운영 화면에서 확인된 `라이나 치아 보험`, `통합 간병 보험`, `치아 보험 디시` 같은 검색어가 `기타보험`으로 떨어지는 문제를 해결했다.

## 1. 왜 기타보험으로 떨어졌나?

기존 룰에는 `치아보험`, `간병보험`, `건강보험`처럼 붙여 쓴 상품군은 많았지만, 실제 검색어는 다음처럼 띄어쓰기가 흔들린다.

```text
라이나 치아 보험
통합 간병 보험
라이나 생명 무배당 간편한 건강 보험
치아 보험 디시
```

검색어 안의 `보험`만 매칭되고 `치아보험` 또는 `간병보험` 카테고리가 잡히지 않으면, Contract Validator는 상품군을 `기타보험`으로 보완한다. 그래서 실제로는 치아보험/간병보험 검색어인데 기타보험으로 보이는 문제가 생긴다.

## 2. 어떻게 고쳤나?

### 2.1 compact_contains 매칭 추가

검색어와 룰 surface에서 공백을 제거한 compact 문자열을 비교한다.

```text
query = 라이나 치아 보험
query_compact = 라이나치아보험
rule surface = 치아보험
surface_compact = 치아보험
```

따라서 `치아 보험`처럼 띄어쓰기가 들어가도 `치아보험` category를 잡는다.

### 2.2 띄어쓰기 variant 룰 추가

자주 나오는 표현은 명시 룰도 추가했다.

```text
치아 보험 → 치아보험
치과 보험 → 치아보험
간병 보험 → 간병보험
통합 간병 보험 → 간병보험
건강 보험 → 건강보험
```

### 2.3 상품명 조건 표현 보강

다음 표현도 사전에 추가했다.

```text
무배당 → 무배당형
간편한 → 간편심사형
디시 → 커뮤니티 기반 탐색어
```

예를 들어 `라이나 생명 무배당 간편한 건강 보험`은 다음처럼 해석된다.

```text
gate_type = detailed
insurance_category = 건강보험
customer_need_type = 상품조건확인
evidence_focus = 간편심사형
```

## 3. 속도는 어떻게 개선했나?

### 3.1 pandas 의존 제거

대형 룰 사전과 대형 검색어 파일을 처리할 때 pandas import와 DataFrame 반복이 느릴 수 있어, 기본 추론 경로에서는 pandas를 import하지 않는다.

### 3.2 CSV 우선 로딩

`base_rules.xlsx`를 넘겨도 같은 폴더에 `base_rules.csv`가 있으면 CSV를 먼저 읽는다. 대형 룰 사전은 CSV가 훨씬 빠르다.

### 3.3 룰 인덱싱

모든 룰을 검색어마다 전수 검사하지 않고, surface의 2-gram 인덱스로 후보 룰만 좁힌 뒤 contains/compact_contains/regex를 수행한다.

### 3.4 unique query 캐시

`run_inference(..., dedupe=True)`가 기본이다. 같은 `query_norm`이 여러 번 나오면 한 번만 추론하고 결과를 재사용한다.

### 3.5 의미 유사 힌트 기본 OFF

의미 유사 후보는 느리고 오탐 위험도 있어 기본 OFF다. 오탈자 보정은 유지하되, 의미 유사 힌트가 필요할 때만 `enable_semantic_hints=True`로 켠다.

## 4. 권장 실행 방식

```python
from src.infer import run_inference, export_review_template

result = run_inference(
    query_path="/content/google_keyword.xlsx",
    base_rules_path="configs/base_rules.xlsx",   # 내부적으로 base_rules.csv 우선 사용
    feedback_store_path=None,
    output_path="outputs/inference_result.xlsx",
    enable_semantic_hints=False,                  # 속도 때문에 기본 OFF 권장
    dedupe=True                                   # 동일 검색어 캐시
)

export_review_template(result, "outputs/review_template.xlsx")
```


---

## Colab Hotfix v5: pandas import / SimpleTable 변환 오류 대응

일부 Colab 실행 경로에서는 `run_inference()`가 속도 개선을 위해 pandas DataFrame이 아니라 `SimpleTable` 또는 list 형태 결과를 반환할 수 있습니다. 이 상태에서 바로 아래처럼 pandas 전용 문법을 쓰면 오류가 납니다.

```python
result_df["review_flag"].astype(str)
```

대표 오류는 다음입니다.

```text
AttributeError: 'list' object has no attribute 'astype'
NameError: name 'pd' is not defined
```

최신 노트북은 이를 방지하기 위해 공통 import 셀에서 반드시 pandas를 import하고, `as_dataframe()` 헬퍼로 결과를 DataFrame으로 강제 변환합니다.

```python
import pandas as pd

def as_dataframe(obj):
    if isinstance(obj, pd.DataFrame):
        return obj.copy()
    if hasattr(obj, "to_dataframe"):
        return obj.to_dataframe()
    if hasattr(obj, "to_records"):
        return pd.DataFrame(obj.to_records())
    if isinstance(obj, list):
        return pd.DataFrame(obj)
    return pd.DataFrame(obj)
```

추론 셀에서는 다음처럼 `result_table`과 `result_df`를 분리합니다.

```python
result_table = run_inference(...)
review_table = export_review_template(result_table, REVIEW_PATH)

result_df = as_dataframe(result_table)
review_df = as_dataframe(review_table)
```

따라서 검수 필터링 셀은 항상 pandas DataFrame 기준으로 안정적으로 작동합니다.

```python
result_df = as_dataframe(result_df)
review_targets = result_df[
    (result_df["review_flag"].astype(str).str.upper() == "Y") |
    (result_df["confidence_flag"].astype(str).isin(["low", "needs_review"]))
].copy()
```

이 수정은 룰 판단 로직에는 영향을 주지 않고, Colab 표시/필터링 안정성만 보강합니다.

---

## v6 보강: 질환명 검색어 오탐 방지와 세부 니즈 컬럼

### 1. 왜 보강했는가?

기존 Resolver는 `당뇨`, `고혈압`, `고지혈증` 같은 질환 단서가 검색어에 들어오면 유병자/가입 가능성 문맥으로 과도하게 해석할 수 있었다. 예를 들어 `당뇨 진단비 보험`은 고객이 “당뇨가 있어도 가입 가능한지”를 묻는 것이 아니라 “당뇨 관련 진단비 보장이 있는지”를 확인하는 검색어에 가깝다.

따라서 v6에서는 질환명 검색어를 아래처럼 문맥 기반으로 분리한다.

| 검색어 문맥 | 예시 | customer_need_type | customer_need_detail |
|---|---|---|---|
| 질환 + 가입/고지/병력/간편/인수 | `당뇨 보험 가입`, `고혈압 병력 보험`, `고지혈증 간편보험` | 가입가능성확인 | 유병력가입가능성확인 또는 간편고지/심사조건확인 |
| 질환 + 진단비/수술비/입원비/치료비/보장 | `당뇨 진단비 보험`, `고혈압 수술비 보험` | 보장범위확인 | 질환진단비보장확인, 수술비보장확인 등 |
| 질환 + 보험만 있음 | `당뇨 보험` | 보장범위확인으로 보수 처리, 단 review_flag=Y | 당뇨확인 등 |

핵심 원칙은 다음과 같다.

```text
질환명이 있다고 무조건 가입가능성확인으로 보내지 않는다.
가입/고지/병력/인수 문맥이 있을 때만 가입가능성확인으로 본다.
진단비/수술비/입원비/치료비/보장 문맥이 있으면 보장범위확인으로 본다.
애매하면 review_flag=Y로 남겨 사람이 확인한다.
```

### 2. customer_need_detail 컬럼

기존 `customer_need_type`은 운영 계약을 위해 대분류로 유지한다. 다만 실제 리뷰와 애드그룹 설계에는 더 세밀한 니즈가 필요하므로 `customer_need_detail`을 추가했다.

예시:

| query | customer_need_type | customer_need_detail |
|---|---|---|
| `당뇨 진단비 보험` | 보장범위확인 | 질환진단비보장확인 |
| `당뇨 보험 가입` | 가입가능성확인 | 유병력가입가능성확인 |
| `325 간편보험` | 상품조건확인 | 인수/간편심사조건확인 |
| `실비 청구 서류 면책기간` | 서류/증빙확인 | 청구서류/증빙확인 |
| `암보험 면책기간` | 상품조건확인 | 약관조건확인 |
| `중입자 암보험` | 보장범위확인 | 치료비보장확인 |

`customer_need_detail`은 기존 4컬럼 계약을 깨지 않는다. 기존 운영 컬럼은 유지하고, 사람이 결과를 더 빨리 이해하고 세부 애드그룹 후보를 만들 수 있게 돕는 보조 컬럼이다.

### 3. v6에서 추가된 대표 룰

질환 + 급부 문맥을 명확히 잡기 위해 다음 유형의 phrase를 추가했다.

```text
당뇨 진단비 / 당뇨진단비 / 당뇨 진담비
고혈압 진단비 / 고혈압진단비
고지혈증 진단비 / 고지혈증진단비
당뇨 수술비 / 고혈압 수술비 / 고지혈증 수술비
당뇨 입원비 / 당뇨 치료비 / 당뇨 보장
실비 청구 서류 / 실비청구서류 / 실손 청구 서류
```

`진담비`처럼 자주 발생할 수 있는 오타도 일부 보강했다. 다만 오타 매칭은 여전히 `review_flag=Y` 또는 trace 확인 대상으로 운용하는 것을 권장한다.

### 4. 동작 예시

```text
당뇨 진단비 보험
→ coverage_focus:당뇨 진단비→당뇨진단비
→ insurance_category=진단비보험
→ customer_need_type=보장범위확인
→ customer_need_detail=질환진단비보장확인
→ evidence_focus=당뇨진단비
```

```text
당뇨 보험 가입
→ disease_focus:당뇨 보험 가입→당뇨
→ insurance_category=유병자보험
→ customer_need_type=가입가능성확인
→ customer_need_detail=유병력가입가능성확인
→ evidence_focus=당뇨
```

```text
당뇨 보험
→ disease_focus:당뇨→당뇨
→ 가입/보장 문맥이 명확하지 않음
→ customer_need_type=보장범위확인
→ confidence_flag=needs_review
→ review_flag=Y
```

---

---

## v7 보강: 치아 골절/파절 문맥 오탐 방지

실제 추론 결과에서 `치아 골절 보험`, `치아 파절 골절 진단비`가 일반 `골절보험`으로 분류되는 문제가 확인되었습니다. 이 문제는 검색어 안에 `골절`이라는 강한 담보 단어가 있으나, 그 앞의 `치아/치과/영구치/유치/앞니` 문맥을 충분히 반영하지 못해 발생했습니다.

v7에서는 단어별 `if`를 추가하지 않고, 룰 사전과 Resolver 정책을 보강했습니다.

### 보강 원리

1. `치아 골절 보험`, `치아 파절 골절 진단비`, `영구치 파절`, `치아 깨짐` 같은 dental-specific phrase를 `coverage_focus`로 추가합니다.
2. 이 phrase들은 `is_protected=Y`로 등록되어 내부의 일반 `골절`, `골절 보험` 매칭이 최종 판단을 빼앗지 못하게 합니다.
3. 선택된 evidence가 매우 구체적인 dental coverage이고 `category_hint=치아보험`을 갖고 있으면, generic `골절보험` category보다 selected evidence의 category hint를 우선합니다.

### 기대 결과

| query | gate_type | insurance_category | customer_need_type | evidence_focus |
|---|---|---|---|---|
| 치아 골절 보험 | detailed | 치아보험 | 보장범위확인 | 치아골절보장 |
| 치아 파절 골절 진단비 | detailed | 치아보험 | 보장범위확인 | 치아파절진단비 |
| 영구치 파절 보험 | detailed | 치아보험 | 보장범위확인 | 영구치파절보장 |
| 치아 깨짐 보험 | detailed | 치아보험 | 보장범위확인 | 치아파절보장 |

이 보강의 핵심은 `골절` 자체를 없애는 것이 아니라, **치아 문맥이 있는 골절/파절 검색어는 치아보험 담보로 우선 해석**하도록 만드는 것입니다.

---

## V8 출력 리뷰 기반 룰 보강 요약

`inference_result (2).xlsx` 검토 과정에서 `치아 골절 보험`, `치아 파절 골절 진단비`가 일반 `골절보험`으로 분류되는 문제가 발견되어 치아 문맥 골절/파절 룰을 보강했습니다.
또한 `임플란트 가격 2025`가 `225간편심사`로 오탐되는 숫자형 인수기준 부분 문자열 문제를 방지하기 위해 순수 숫자형 underwriting 룰은 좌우 숫자 경계를 확인하도록 수정했습니다.

핵심 보정 예시는 다음과 같습니다.

```text
치아 골절 보험 -> 치아보험 / 보장범위확인 / 치아골절보장
치아 파절 골절 진단비 -> 치아보험 / 보장범위확인 / 치아파절진단비
임플란트 가격 2025 -> 치아보험 / 보장범위확인 / 임플란트보장
암 완치 후 보험 가입 -> 유병자보험 / 가입가능성확인 / 암병력
간호 간병 통합 서비스 보험 -> oos / null / OOS / 공공의료/건강보험제도
```

상세 내용은 `docs/OUTPUT_REVIEW_RULE_PATCH_V8.md`를 참고하세요.


## V9 최신 아웃풋 품질점검 반영: 간병/치아/공공보험/세부 니즈 정합성

업로드된 최신 `inference_result.xlsx` 전체 213,127건을 기준으로 결과를 재점검했고, 아래 보강을 반영했습니다.

### 1. 간병/간병인 customer_need_detail 정합성

`간병인사용일당`은 문자열에 `일당`이 포함되지만 실제 업무 해석상 단순 입원일당보다 `간병/요양보장확인`으로 보는 것이 더 적절합니다. V9에서는 `간병`, `요양`, `간호`가 포함된 focus를 먼저 판단해 customer_need_detail을 보정합니다.

예시:

```text
간병인 보험
→ 간병인보험 / 보장범위확인 / 간병인사용일당 / 간병/요양보장확인

간병인 보험 나이 제한
→ 간병인보험 / 가입가능성확인 / 가입연령 / 가입연령조건확인

체증 형 간병인 보험
→ 간병인보험 / 상품조건확인 / 체증형 / 체증형조건확인
```

### 2. policy term이 실제 상품군을 덮어쓰는 문제 개선

`면책기간`, `감액기간` 같은 약관 조건은 `기타보험` category_hint를 가질 수 있지만, 검색어 안에 `간병인보험`, `치아보험`, `암보험` 같은 실제 category가 있으면 그 상품군이 우선되어야 합니다.

예시:

```text
간병인 보험 면책 기간
→ 기존 위험: 기타보험
→ V9: 간병인보험 / 상품조건확인 / 면책기간 / 약관조건확인
```

### 3. 숫자형 인수기준 오탈자 오탐 차단

`2025`, `2405` 같은 연도·상품번호가 `225`, `245` 간편심사로 오탐되는 문제를 차단했습니다. 숫자형 underwriting rule은 더 이상 typo matcher의 자동 후보가 되지 않습니다.

예시:

```text
임플란트 가격 2025
→ 치아보험 / 보장범위확인 / 임플란트보장
```

### 4. 공공 건강보험/급여 문맥 OOS 보강

민영 보험 상품 검색이 아닌 `건강보험 적용`, `간호간병통합서비스`, `요양급여`, `건강보험 임플란트` 등은 public_non_private로 처리합니다.

예시:

```text
간호 간병 통합 서비스 보험
→ oos / null / OOS / 간호간병통합서비스

건강 보험 임플란트
→ oos / null / OOS / 임플란트건강보험
```

### 5. 치아/치과 문맥 보강

`치과 보험`, `보험 치과`, `손해 보험 치아` 등 띄어쓰기나 어순이 흔들리는 검색어를 치아보험으로 인식하도록 사전을 보강했습니다. 또한 `치아 홈 메우기`, `치아 미백`, `치아 때우는 재료`를 보장범위확인 대상으로 추가했습니다.

자세한 점검 내용은 `docs/OUTPUT_QA_CARE_DETAIL_RULE_PATCH_V9.md`를 확인하세요.


## V10 종합 품질 검수 및 룰 보강 요약

최신 대량 추론 결과에서 발견된 품질 이슈를 기준으로 다음을 보강했습니다.

1. **간병/간병인 customer_need_type 정합성**
   - `간병인 보험 가격`, `간병인 보험료`, `간병비 보험 금액`은 coverage가 잡히더라도 `보험료확인`으로 보정합니다.
   - `간병인 보험 비교`, `간병인 보험 간병비 보험 차이`, `간병비 보험 장단점`은 `상품비교`로 보정합니다.
   - `간병인 보험 추천`, `간병인 보험 후기`, `간병인 보험 필요성`은 `상품추천탐색`으로 보정합니다.

2. **비민영/공공 간병·의료 제도 OOS 처리**
   - `간병인 지원 제도`, `간병인 국가 지원`, `간병비 지원`, `간호 간병 서비스`, `의료 보험 조회` 등은 민영 보험 상품 탐색이 아니므로 `gate_type=oos`, `insurance_category=null`로 처리합니다.

3. **오탈자 유사도 과보정 방지**
   - coverage_focus의 typo threshold를 0.90으로 높였습니다.
   - `임프란트→임플란트`처럼 강한 오탈자는 유지하되, `족간병→재가간병비`, `리치간병→치매간병비` 같은 약한 우연 매칭은 차단합니다.

4. **치아/턱관절 담보 보강**
   - `실란트 보험`, `지르코니아 보험`, `스플린트 보험`, `턱 관절 스플린트 보험`, `턱 관절 치료 보험`을 치아보험/치아치료 보장으로 인식합니다.

이 보강은 단어별 if 추가가 아니라 `base_rules.csv` 룰 추가와 Resolver의 customer_need_type override 원칙으로 구현되었습니다.
