# 📄📢 AI-NutriCurator

만성질환 중증도 환자들은 일상적인 커머스 환경에서도 본인의 건강 상태에 적합한 식품을 선택하는 데 정보의 비대칭성 및 상품 탐색 과정에서의 불편함을 겪고 있습니다. 
본 AI서비스는 신뢰도 높은 출처 기반으로 구축된 DB를 바탕으로 정확도 높은 메세지 생성 및 추천 로직을 통해 이를 해소하고자 합니다.

# Team BuildSparkDevelopers

팀장: 소형선 이영주 박수빈

# 📄📢 사용법/실행법/팀 규칙 정리

#
# ㅡㅡㅡㅡㅡㅡㅡㅡㅡㅡㅡㅡㅡㅡㅡㅡㅡㅡㅡㅡㅡㅡㅡㅡㅡㅡㅡㅡㅡㅡㅡㅡㅡㅡㅡ
#

# 🤖 에이전트 개요


START: 유저가 [장바구니 담기] 버튼을 클릭함

## 1️⃣ Node 1 (Orch-01): Eligibility Checking & Routing (Conditional Edge)

### 1. 유저가 질병을 보유하고 있는가?
*@USER-Agent 호출
* IN: USER-01의 Profile Retrieval
* Logic : PASS or WARN

      disease = diabetes + hypertension + kidneydisease + allergy

          ** PASS: disease = 0    -> end
          ** WARN: disease >= 1   -> 2. 이동


### 2. 식품에 유관 성분이 있는가?
*@CHAT-Agent 호출
* IN: CHAT-01의 Evidence Generation
* logic : PASS or WARN

          ** PASS: 부적합성분 없음    -> end,
          ** WARN: 부적합성분 있음    -> to_chat, to_reco

* next: 판정결과에 따라 다른 에이전트 및 tool 호출, 상품특성 JSON 전달

#
# ㅡㅡㅡㅡㅡㅡㅡㅡㅡㅡㅡㅡㅡㅡㅡㅡㅡㅡㅡㅡㅡㅡㅡㅡㅡㅡㅡㅡㅡㅡㅡㅡㅡㅡㅡ
#

## 2️⃣ Node 2 (User-01): Profile Retrieval

유저프로필을 조회하여 건강정보 확인 및 페르소나를 JSON 출력
* MVP: ?user_id?, weight, diabetes, hypertension, kidneydisease, allergy
* Post-MVP: height, activity_level, persona(FK, Post-MVP DB)



### 참고) final_profile DB
Node2(User-02) + priority_map + 유관성분 임계값&문자열 필터링
* 미리 생성해서 DB에 저장된 상태

Logic :
* 임계값 기반 필터링

      diabetes: (-)당(<5g)
                (+)식이섬유(>=14g/1,000kcal)

      hypertension: (-)나트륨(<2,300mg/day),
                    (-)칼륨 > 3500mg
                    (-)총 지방 < 하루 총 열량의 20-25% 이하

      kidneydisease:  CKD 3-5단계 (투석 전, 당뇨 없음)
                      (-)단백질 kg당 0.55-0.60g/kg/일
                      (-)나트륨 2.3g 미만
                      (-)인 800-1,000 mg/일
                      (-)칼슘 800-1,000mg/일
                      (-)25-35 kcal/kg/일

                      CKD 5단계 (투석)
                      (+)단백질 1.0-1.2g/kg/일
                      (-)나트륨 2.3g 미만
                      (-)칼륨 2,000/일로 제한
                      (-)인 800-1,000 mg/일
                      (-)칼슘 800-1,000mg/일
                      (-)25-35 kcal/kg/일
      
      (POST-MVP에서는 (+) 성분 섭취시 긍정피드백을 주는것도 고려)

* 문자열 기반 필터링

      allergy: 우유, 달걀, 땅콩, 견과류, 콩, 밀, 생선, 갑각류 어패류
      원재료 포함성분 및 교차오염성분

* 우선순위 순으로

      priority_map = { allergy: 1, kidneydisease: 2, diabetes : 3, hypertension: 4 }

          질병 우선순위에 따른 필터링성분 및 임계값을 먼저 호출.
          그 다음 순위 질병의 필터링성분을 호출
          -> 이미 호출된 필터링성분은 새로 호출하지 않음
          Priority-Merger -> 질병 우선순위에 따라 Final_Profile 생성

      final_profile = {
          user_id: ,
          성분1: 성분1함량,
          성분2: 성분2함량,
          알러지: 알러젠
          ...

#
# ㅡㅡㅡㅡㅡㅡㅡㅡㅡㅡㅡㅡㅡㅡㅡㅡㅡㅡㅡㅡㅡㅡㅡㅡㅡㅡㅡㅡㅡㅡㅡㅡㅡㅡㅡ
#

## 3️⃣ Node 3 (Chat-01): Evidence Generation

식품성분과 질환 가이드라인을 대조하여 근거기반 적합성 판별후 *JSON 출력*
* IN: final_profile DB, product DB, disease RAG?

      *final_profile DB:
      *product DB: product_id, name, category, brand
                -> 성분함량체크 및 상품 조회 맥락 유지
      *disease RAG: 질병유관 성분 및 성분 가이드(함량)
                -> 식품 성분 적합성
* logic : 질환별 성분 필터링 (simple check)

* 판단결과 예시 ----> **JSON 기반으로 변경 필요

      Scenario : 🚫 영양 성분 초과 (Nutrient Violation)
        - 최종 판정: [WARN]
        - 위반 알러지: []
        - 위반 영양소: ['sodium', 'sugar']
        - 상세 리포트:
          ✅ PROTEIN: 실제 15.0 / 기준 40.0
          🚩 SODIUM: 실제 3000.0 / 기준 2300.0
          🚩 SUGAR: 실제 10.0 / 기준 5.0



## 4️⃣ Node 4 (Reco-01): Vector DB Search & Recommendation

* 상품특성 JSON을 받아서 유사한 상품 조회 및 추천

## 4️⃣ Node 4-1 (sub-Reco-01): Vector DB Search & Recommendation

방식1: 레코에서 준 30-50개 정도의 상품중에서 roles.py 로 3개를 추천
방식2: 레코에서는 3개만 주고 그 3개 상품의 조회맥락과 식품성분이 유저에게 맞는지 판단

## 5️⃣ Node 5 (Resp-01):








#

