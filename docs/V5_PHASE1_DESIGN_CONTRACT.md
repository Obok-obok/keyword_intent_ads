# V5 Phase 1 Light 설계 계약서

## 1. 계약 요약

v5 Phase 1 Light는 보험 검색어를 분석하는 경량 엔진이다. 기존 v22의 출력 방향은 유지하되, 내부 구현을 if 덧대기 방식에서 `Phrase Detector → Protected Span Builder → Evidence Extractor → Semantic Resolver → Contract Validator` 구조로 교체한다.

## 2. 최종 출력 스키마

| 컬럼 | 설명 |
|---|---|
| query | 원본 검색어 |
| query_norm | 정규화 검색어 |
| gate_type | general / detailed / oos |
| insurance_category | 보험 상품군 |
| customer_need_type | 고객 니즈 |
| evidence_focus | 검색어 안의 핵심 단서 |
| evidence_trace | 판단 근거 |
| confidence_flag | high / medium / low / needs_review |
| model_hint | 모델 보조 제안 |
| review_flag | 검토 필요 여부 |

## 3. 허용 gate_type

- general
- detailed
- oos

## 4. 허용 customer_need_type

- 브랜드상품확인
- 상품추천탐색
- 상품비교
- 보험료확인
- 견적/상담요청
- 보장범위확인
- 상품조건확인
- 가입가능성확인
- 가입방법확인
- 청구/보험금문의
- 서류/증빙확인
- 계약관리문의
- 해지/환급문의
- 갱신/유지문의
- 보험용어/제도탐색
- 질병정보탐색
- OOS

## 5. 확장 insurance_category

- 암보험
- 치아보험
- 실손보험
- 간병보험
- 치매보험
- 건강보험
- 종합건강보험
- 간편보험
- 간편심사보험
- 유병자보험
- 인수완화보험
- 시니어보험
- 수술비보험
- 질병수술비보험
- 상해수술비보험
- 입원비보험
- 간병비보험
- 진단비보험
- 암진단비보험
- 뇌심장보험
- 3대질병보험
- 2대질병보험
- 질병보험
- 상해보험
- 후유장해보험
- 질병후유장해보험
- 상해후유장해보험
- 여성보험
- 여성건강보험
- 여성암보험
- 임신출산보험
- 난임보험
- 어린이보험
- 태아보험
- 종신보험
- 정기보험
- 연금보험
- 저축보험
- 변액보험
- 운전자보험
- 자동차보험
- 여행자보험
- 화재보험
- 펫보험
- 배상책임보험
- 기타보험
- null

## 6. Semantic Resolver LEVEL

숫자가 낮을수록 우선순위가 높다.

| LEVEL | 이름 | 설명 |
|---:|---|---|
| 0 | Exact Override | 사람이 직접 수정한 정답 |
| 1 | Hard OOS | 보험 분석 대상이 아닌 건강/생활/질병정보 |
| 2 | Public / Non-insurance | 국민건강보험, 고용보험, 산재보험 등 |
| 3 | Action / Service Intent | 청구, 서류, 해지, 환급 등 |
| 4 | Policy Term / Product Feature | 비갱신, 면책, 325, 355, 인수완화 등 |
| 5 | Coverage / Disease / Treatment | 중입자, 유방암, 질병수술비, 임플란트 등 |
| 6 | Category | 보험 상품군 |
| 7 | Brand | 보험사/브랜드 |
| 8 | Weak Intent | 추천, 비교, 가격, 견적 등 |
| 9 | Fallback | 근거 부족 기본 처리 |

## 7. 상품·담보 해석 3층 구조

검색어는 3층으로 해석한다.

1. `insurance_category`: 상품군
2. `policy_product_feature` / `underwriting_type`: 상품 조건과 인수기준
3. `coverage_focus`: 담보와 치료비 단서

예:
- `325 간편보험` → category=간편심사보험, evidence_focus=325간편심사
- `중입자 암보험` → category=암보험, evidence_focus=중입자치료비
- `여성 유방암 보험` → category=여성암보험, evidence_focus=유방암진단비
- `질병수술 보험` → category=질병수술비보험, evidence_focus=질병수술비

## 8. 모델 계약

모델은 보조 역할이다. 모델은 gate_type, insurance_category, customer_need_type만 힌트로 제공한다. evidence_focus는 절대 생성하지 않는다.

## 9. 피드백 루프 계약

피드백은 콜랩에서 즉시 반영 가능해야 한다.

- `quick_fix_exact`: 특정 query_norm의 정답 고정
- `quick_add_phrase`: 새 phrase 추가
- `quick_add_protected_span`: 오탐 방지 protected phrase 추가
- `quick_add_exclusion`: 특정 surface의 특정 slot 차단

피드백은 `feedback_store.xlsx`에 저장되고 다음 추론부터 자동 반영된다.

## 10. 검수 기준

- 업무 단어가 `infer.py`에 if로 직접 박혀 있으면 실패
- 새 단어 추가가 `base_rules.xlsx` 또는 `feedback_store.xlsx`로 가능해야 통과
- `oos`이면 `insurance_category=null`이어야 통과
- `evidence_focus`는 query evidence 또는 exact override에서만 나와야 통과
- `quick_fix_exact` 후 같은 query가 즉시 수정되어야 통과
- `quick_add_phrase` 후 유사 query가 개선되어야 통과
- `quick_add_exclusion` 후 오탐이 차단되어야 통과

---

# 최종 룰 보강 계약: 최신 상품/담보 확장

마지막 보강에서는 구조 변경 없이 `configs/base_rules.csv` / `configs/base_rules.xlsx`의 phrase 사전을 확장한다. 원칙은 동일하다. 업무 단어를 코드에 `if`로 추가하지 않고, phrase row로 등록해 Phrase Detector와 Semantic Resolver가 처리하게 한다.

## 1. 확장 상품군

다음 category를 추가 허용하고 사전에 반영한다.

```text
암주요치료비보험
순환계질환보험
순환계치료비보험
정신건강보험
생활위험보험
장기요양보험
어린이건강보험
펫의료보험
```

## 2. 확장 담보군

추가 보강 범위는 다음이다.

```text
암주요치료비 / 암통합치료비 / 전이암생활비 / 항암호르몬치료 / 중입자방사선 / 토모테라피 / 하이푸
순환계치료비 / 심혈관치료비 / 뇌혈관치료비 / 협심증 / 부정맥 / 심부전 / 대동맥류
여성 유갑생 / 유방재건 / 유방절제 / 난임진단 / 가임력보존 / 난자동결 / 배아동결 / 임신중독증 / 출산지원금 / 산후우울 / 정신건강 / 흉터치료
태아 선천이상 / 저체중아 / 미숙아 / NICU / 성조숙증 / ADHD / 자폐 / 장기요양등급 / 파킨슨 / 루게릭
대상포진 / 통풍 / 독감 / 일상생활배상책임 / 누수 / 여행 지연 / 휴대품 손해 / 펫 슬개골 / 펫 치과
```

## 3. Resolver 반영 원칙

- 최신 담보는 대부분 `coverage_focus`이며 LEVEL 5로 처리한다.
- 315, 345, 3.1.5, 3.4.5, 건강고지형, 무심사, 초간편 등은 `underwriting_type` 또는 `policy_product_feature`이며 LEVEL 4로 처리한다.
- 상품군은 `insurance_category`에 남기고, 구체 담보·인수기준은 `evidence_focus`에 남긴다.
- 예: `암주요치료비 보험` → category=`암주요치료비보험`, evidence_focus=`암주요치료비`.
- 예: `순환계치료비 보험` → category=`순환계치료비보험`, evidence_focus=`순환계치료비`.
- 예: `난자동결 보험` → category=`난임보험`, evidence_focus=`난자동결보장`.
- 예: `산후우울 보험` → category=`정신건강보험`, evidence_focus=`산후우울보장`.
- 예: `슬개골 강아지보험` → category=`펫보험`, evidence_focus=`슬개골탈구보장`.


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

# 16. Similarity Matcher 최종 계약

## 16.1 목적

Similarity Matcher는 룰 사전 기반 매칭을 대체하지 않는다. 목적은 다음 두 가지다.

```text
1. 오탈자 수준의 매칭 보완
2. 애매한 의미 유사 후보를 model_hint에 제안
```

Similarity Matcher는 Semantic Resolver보다 앞에서 evidence 후보 또는 hint를 만든다. 그러나 최종 판단은 여전히 Semantic Resolver와 Contract Validator가 수행한다.

## 16.2 Typo Similarity Matcher

적용 대상 slot은 whitelist로 제한한다.

```text
brand_name
insurance_category
coverage_focus
policy_product_feature
underwriting_type
```

적용 제외 slot은 다음과 같다.

```text
hard_oos
public_non_private
action_service
weak_intent
insurance_intent
```

오탈자 후보는 한글 자모 분해 기반 문자 유사도를 사용한다. 예를 들어 `라이나`와 `러이나`는 음절 단위로는 한 글자 차이가 크지만, 자모 단위로는 대부분 일치한다.

오탈자 후보가 threshold 이상이면 evidence 후보로 넣을 수 있다.

예:

```text
query = 러이나 치아보험
candidate = brand_name:러이나→라이나
match_type = typo
```

출력:

```text
evidence_focus = 라이나
confidence_flag = medium
review_flag = Y
```

초기 운영에서는 오탈자 보정 결과도 review 대상에 둔다.

## 16.3 Light Embedding Hint

문장 임베딩의 역할은 크게 두지 않는다. 기본 구현은 Colab에서 바로 동작하는 char n-gram vector similarity다.

이 기능은 다음처럼 동작한다.

```text
query와 rule.embedding_text의 유사도 계산
→ threshold 이상이면 model_hint에 후보 기록
→ evidence_focus는 확정하지 않음
→ review_flag=Y로 사람 검수 유도
```

예:

```text
query = 암 비싼 치료비 보험
model_hint = embedding:coverage_focus=암주요치료비|score=0.84|hint_only=true
evidence_focus = null
review_flag = Y
```

## 16.4 금지 원칙

```text
Similarity Matcher는 Hard OOS를 뒤집을 수 없다.
Similarity Matcher는 Public / Non-insurance를 민영 보험 검색어로 바꿀 수 없다.
의미 유사 후보만으로 evidence_focus를 확정하지 않는다.
typo/embedding 결과는 evidence_trace 또는 model_hint에 score를 남긴다.
```

---

# 17. Colab Notebook 실행 계약

Colab 노트북은 운영자가 경로를 직접 수정하지 않아도 실행되어야 한다.

## 17.1 필수 기능

```text
프로젝트 zip 업로드
프로젝트 루트 자동 탐지
검색어 파일 업로드
base_rules.xlsx 자동 탐지
feedback_store.xlsx 템플릿 자동 생성
inference_result.xlsx 생성
review_template.xlsx 생성
결과 파일 다운로드
Quick Fix 함수 실행
feedback_store.xlsx 저장
재추론 실행
업데이트 결과 다운로드
Excel Batch Review 반영
```

## 17.2 Quick Fix 함수

```python
quick_fix_exact(...)
quick_add_phrase(...)
quick_add_protected_span(...)
quick_add_exclusion(...)
compile_review_template(...)
```

## 17.3 주석 계약

노트북의 각 셀에는 다음 설명이 포함되어야 한다.

```text
이 셀이 왜 필요한지
어떤 파일을 입력으로 받는지
어떤 파일을 출력하는지
운영자가 어떤 값을 바꾸면 되는지
피드백이 어떤 시트에 저장되는지
재추론 시 어떤 방식으로 반영되는지
```

## 17.4 출력 파일

```text
inference_result.xlsx
review_template.xlsx
feedback_store.xlsx
inference_result_updated.xlsx
review_template_updated.xlsx
```

---

# 부록. 최종본 반영 사항 — 경량 Similarity와 Colab 운영 풀버전

## A. 지도학습 모델 정책

v5 Phase 1 Light에서는 지도학습 모델을 필수로 두지 않는다. 정답지 데이터가 충분하지 않은 초기 단계에서는 룰 사전과 Semantic Resolver가 더 안전하다. 기존 `TF-IDF + LogisticRegression` 구조는 선택 기능으로 남겨둘 수 있으나, 기본 운영은 다음 구조로 수행한다.

```text
rule exact/contains/regex
→ protected span
→ typo similarity
→ embedding hint
→ semantic resolver
→ contract validator
```

## B. Similarity Matcher 정책

Similarity Matcher는 최종 판단자가 아니다. 두 종류로 제한한다.

1. `Typo Similarity Matcher`
   - 라이나/러이나, 임플란트/임프란트 같은 짧은 오탈자 보정
   - brand_name, insurance_category, coverage_focus, underwriting_type에만 제한 적용. policy_product_feature는 오탐 위험이 커서 기본 typo 대상에서 제외
   - 확실한 경우 evidence_focus를 canonical_value로 채울 수 있으나 evidence_trace에 match=typo, score를 남김

2. `Light Embedding Hint`
   - 딥러닝 문장 임베딩이 아니라 Colab 기본 환경에서 동작하는 local char n-gram cosine similarity
   - 의미 유사 후보를 model_hint에만 기록
   - evidence_focus를 직접 채우지 않음
   - 초기에는 review_flag=Y로 사람이 검토

## C. evidence_focus 원칙

| 매칭 유형 | evidence_focus | confidence/review |
|---|---|---|
| exact / contains / regex | 채움 | high/medium |
| compact_contains | 채움 가능 | medium |
| typo high | 채움 가능 | medium + review_flag=Y |
| embedding hint | 채우지 않음 | needs_review + review_flag=Y |

## D. Colab 운영 계약

Colab 노트북은 다음을 모두 포함해야 한다.

- zip 업로드 및 자동 압축 해제
- 프로젝트 루트 자동 탐지
- 검색어 파일 업로드 또는 샘플 선택
- base_rules / feedback_store 경로 자동 지정
- 전체 추론 실행
- 결과 다운로드
- 검수 대상 필터링
- quick_fix_exact
- quick_add_phrase
- quick_add_protected_span
- quick_add_exclusion
- Excel Batch Review 반영
- 재추론
- 업데이트 결과와 feedback_store 다운로드
- outputs 전체 zip 다운로드

## E. 룰 사전 대폭 보강 범위

최종 룰 사전은 전통 상품군 외에 다음 영역을 포함한다.

- 암 주요치료비, 중입자, 양성자, CAR-T/카티, 표적항암, 면역항암, 유전자검사/NGS
- 여성보험, 유방재건, 맘모톰, 하이푸, 난임, 난자동결, 임신·출산, 산후우울, 갱년기
- 3N5, 325, 355, 무심사, 초간편, 간편고지, 건강고지형, 인수완화
- 질병수술비, 136대수술, 통합치료비, 순환계치료비, 뇌심장 중재술
- 태아/NICU/선천이상, 어린이 ADHD/성조숙증/아토피/소아암
- 치아 보철/보존/촬영/치조골이식/레진/인레이/온레이
- 운전자, 배상책임, 누수, 보이스피싱, 여행 지연, 펫 슬개골/치과/MRI

---

## v6 추가 계약: 질환 문맥 Resolver와 customer_need_detail

### 문제

`당뇨`, `고혈압`, `고지혈증` 같은 질환 단서는 두 가지 의미를 가질 수 있다.

1. 유병력 때문에 보험 가입이 가능한지 확인하는 검색
2. 해당 질환 관련 진단비/수술비/치료비/입원비 보장을 확인하는 검색

따라서 질환 단서가 있다고 무조건 `가입가능성확인`으로 분류하면 안 된다.

### v6 Resolver 원칙

```text
질환 + 가입/고지/병력/간편/인수/거절/심사/있어도 → 가입가능성확인
질환 + 진단비/수술비/입원비/치료비/보장/담보       → 보장범위확인
질환 + 보험만 있음                                → 보장범위확인으로 보수 처리하되 review_flag=Y
```

### 세부 니즈 컬럼

`customer_need_type`은 기존 계약의 대분류로 유지한다. 대신 세부 해석을 위해 `customer_need_detail`을 추가한다.

예시:

| query | customer_need_type | customer_need_detail |
|---|---|---|
| 당뇨 진단비 보험 | 보장범위확인 | 질환진단비보장확인 |
| 당뇨 보험 가입 | 가입가능성확인 | 유병력가입가능성확인 |
| 실비 청구 서류 | 서류/증빙확인 | 청구서류/증빙확인 |
| 325 간편보험 | 상품조건확인 | 인수/간편심사조건확인 |

### 출력 계약 변경

기존 핵심 4컬럼은 유지한다.

```text
gate_type / insurance_category / customer_need_type / evidence_focus
```

다만 운영 검수 컬럼에 `customer_need_detail`을 추가한다.

```text
query
query_norm
gate_type
insurance_category
customer_need_type
evidence_focus
customer_need_detail
evidence_trace
confidence_flag
model_hint
review_flag
```

---

## v7 추가 계약: 치아 골절/파절 문맥 우선 처리

실제 추론 산출물에서 `치아 골절 보험`, `치아 파절 골절 진단비`가 일반 `골절보험`으로 분류되는 오류가 확인되었다. 이는 `골절` phrase가 강한 coverage로 잡히지만, 앞의 `치아/치과/영구치/유치/앞니` 문맥이 category 결정에 충분히 반영되지 않았기 때문이다.

### 처리 원칙

1. `치아 골절`, `치아 파절`, `영구치 파절`, `치아 깨짐`, `치아 외상` 등은 generic 골절이 아니라 치아보험 담보 context로 본다.
2. 해당 phrase는 `coverage_focus`로 추가하고, `category_hint=치아보험`, `need_hint=보장범위확인`, `gate_hint=detailed`로 둔다.
3. 긴 phrase는 `is_protected=Y`로 둬서 내부의 일반 `골절`, `골절 보험` 매칭이 최종 category를 빼앗지 못하게 한다.
4. Resolver는 selected coverage가 매우 구체적이고 높은 priority를 갖는 경우 selected coverage의 `category_hint`를 generic category보다 우선할 수 있다.

### 기대 결과

| query | gate_type | insurance_category | customer_need_type | evidence_focus |
|---|---|---|---|---|
| 치아 골절 보험 | detailed | 치아보험 | 보장범위확인 | 치아골절보장 |
| 치아 파절 골절 진단비 | detailed | 치아보험 | 보장범위확인 | 치아파절진단비 |
| 영구치 파절 보험 | detailed | 치아보험 | 보장범위확인 | 영구치파절보장 |
| 치아 깨짐 보험 | detailed | 치아보험 | 보장범위확인 | 치아파절보장 |
| 골절 보험 | detailed | 골절보험 | 보장범위확인 | 골절진단비 |
