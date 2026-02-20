# -*- coding: utf-8 -*-


{
  "hypertension": {
    "sodium_max": 2300,
    "potassium_min": 3500,
    "fat_ratio_max": 0.25
  },
  "ckd_pre_dialysis": {
    "sodium_max": 2000,
    "potassium_max": 2000,  // 고혈압과 달리 'MAX' 제한
    "protein_max_g_per_kg": 0.8,
    "phosphorus_max": 800
  },
  "diabetes": {
    "sugar_max_ratio": 0.1, // 총 열량의 10% 이하
    "fiber_min": 25
  }
}

"""수학적 근거: 혈압 감소폭의 비율 (Ratio of Effect Size)가장 신뢰도 높은 지표인 '나트륨 저감에 따른 수축기 혈압 감소량'을 비교해 보겠습니다. (WHO & BMJ 메타분석 데이터 기준)고혈압 환자의 효과: $-5.8 \text{mmHg}$일반인(정상 혈압)의 효과: $-1.2 \sim -2.0 \text{mmHg}$이 두 값을 나누어 '민감도 비율'을 계산해 보면 다음과 같습니다.$$\text{비율} = \frac{\text{고혈압 환자 효과}(-5.8)}{\text{일반인 효과}(-2.0)} = \mathbf{2.9 \text{배}}$$최대치인 -1.2mmHg를 기준으로 하면 4.8배까지 차이가 납니다.즉, 보수적으로 잡아도 고혈압 환자는 같은 식단 변화에 대해 일반인보다 약 3배 더 민감하게 반응"""



# Base code for each : sub-agent and llm

#1. Sub-agent

class SubstitutionReco:

    def __init__(self, user_profile):
        """
        user_profile: 'hypertension', 'kidney_disease', or 'diabetes'
        """
        self.user_profile = user_profile



    def calculate_health_score(self, product):
        """
        Final Decision Algorithm: Scores product from 0-100 based on disease.
        """
        score = 100
'''
        serving_g = product['serving_size']['grams']   #식품마다 식품표시에 표기된 내용량이 총제공량당/100g당/1개단위 다름

        # Normalize essential values

        norm_sodium = self.normalize(product['nutrition_per_serving']['sodium_mg'], serving_g)

        norm_sugar = self.normalize(product['nutrition_per_serving']['sugars_g'], serving_g)
'''


## 고혈압

        if self.user_profile == "hypertension":
        # Penalty: -10 points for every 100mg of Sodium per 100g
        score -= (norm_sodium / 100) * 10

        def calculate_hypertension_score(k_mg, na_mg):
            """
            고혈압 점수 산정 (Michaelis-Menten 곡선 기반)
            칼륨(K): 최소 섭취량(3500mg)까지 급격히 상승, 권장 섭취량(4700mg) 이상은 수렴 (5점 내외 차이)
            나트륨(Na): Na/K 비율에 고혈압 환자 민감도 가중치(w=3)를 적용하여 감점

            Score_K = V_max × K / (C_k + K)
            Score   = Score_K - (Na/K × w × C)
            """
            V_max = 102   # 이론적 점수 최대치
            C_k = 150     # 반포화 상수 (4700mg 이상 수렴 유도)
            w = 3         # 고혈압 환자 민감도 가중치 (일반인 대비 2.9배 → 보수적 3배)
            C = 10        # 스케일 보정 상수

            if k_mg <= 0:
                return 0

            # 1. 칼륨 점수 (Michaelis-Menten)
            score_k = min(V_max * (k_mg / (C_k + k_mg)), 100)

            # 2. Na/K 비율 기반 감점
            penalty = (na_mg / k_mg) * w * C

            # 3. 최종 점수 (0점 미만은 0점 처리)
            final_score = score_k - penalty

            return max(final_score, 0)



##당뇨환자

        if self.user_profile == "diabetes":
        # Penalty: -10 points for every 5g of Sugar per 100g
        score -= (norm_sugar / 5) * 10


        # [변수 추출] (Key가 없을 경우를 대비해 .get() 사용 및 기본값 0 설정)
        carb = product_data.get("carbohydrate", 0)
        sugar = product_data.get("sugar", 0)
        fiber = product_data.get("dietary_fiber", 0)
        eryth = product_data.get("erythritol", 0)
        allu = product_data.get("allulose", 0)
        kcal = product_data.get("calories", 0)

        # [수식 2] 순탄수화물 계산 (Net Carbs)
        # 총 탄수화물 - (식이섬유 + 에리스리톨 + 알룰로오스)
        # 단, 결과값이 실제 포함된 '당류'보다는 작을 수 없도록 보정
        net_carb = max(sugar, carb - (fiber + eryth + allu))

        # [수식 3] 순탄수 열량 비중 (R_cal)
        r_cal = (net_carb * 4 / kcal * 100) if kcal > 0 else 0

        # [수식 4] 순탄수 대비 당류 비율 (R_sugar)
        r_sugar = (sugar / net_carb * 100) if net_carb > 0 else 0

        # [수식 5] 최종 점수 산정 (100점 만점)
        w1, w2 = 0.6, 0.4
        score = 100 - (w1 * r_cal + w2 * r_sugar)

        # 페널티: 당류 비율이 10%를 초과할 경우 -15점
        if r_sugar > 10:
            score -= 15

        # 6. 결과 데이터 추가 및 반환
        analysis = {
            "net_carbohydrate": round(net_carb, 2),
            "diabetes_score": round(max(0, score), 2),
            "is_safe_sugar_ratio": r_sugar <= 10
        }

        # 기존 데이터에 분석 결과 병합
        return {**product_data, **analysis}

# --- 실행 예시 ---
product_list = {
    "0": {
        "product_id": "201905000000",
        "name": "설화눈꽃팝김부각스낵",
        "calories": 150, "carbohydrate": 20, "sugar": 1,
        "dietary_fiber": 10, "erythritol": 1, "allulose": 1
    }
}

# 당류 5g 미만 필터링 + 수식 적용

# 점수순 정렬
final_recommendations.sort(key=lambda x: x['diabetes_score'], reverse=True)

print(final_recommendations[0])





###신장이상

        if self.user_profile == "kidney_disease"
        # Instant Fail for Phosphorus additives
        if product.get('flags', {}).get('has_phos_additives', False):
        score -= 100
        # Penalty for Sodium density
        score -= (norm_sodium / 140) * 10  #120mg 식약처에서 식품 100g당 120mg이면 저염 표시 가능. 시중 120mg 미만은

        return max(0, score)

    def validate_swap(self, chosen_item, recommended_item):
        """
        The 'Math Gate': Returns True if recommended is mathematically superior.
        """

        chosen_score = self.calculate_health_score(chosen_item)

        recommended_score = self.calculate_health_score(recommended_item)

        # It is correct if the recommended item has a higher health score

        return recommended_score > chosen_score

    def generate_llm_prompt(self, chosen_item, recommended_item, is_valid):

        """
        Generates the instructions for the LLM to display the pop-up.
        """

        if not is_valid:
          return {

              "action": "DISPLAY_SUCCESS",
              "message": f"Great choice! Your selection of {chosen_item['name']} fits your profile well."
          }

        # Calculate the 'Benefit' for the Comparison Card
        sodium_diff = chosen_item['nutrition_per_serving']['sodium_mg'] - recommended_item['nutrition_per_serving']['sodium_mg']
        prompt = {
            "action": "DISPLAY_WARNING_SUBSTITUTION",
            "context": f"User has {self.user_profile}. They chose {chosen_item['name']}.",
            "recommendation": recommended_item['name'],
            "comparison_data": {
            "chosen_sodium": chosen_item['nutrition_per_serving']['sodium_mg'],
            "swap_sodium": recommended_item['nutrition_per_serving']['sodium_mg'],
            "benefit": "Lower Sodium Density" if self.user_profile == "hypertension" else "Kidney Safe"
            },

            "llm_instruction": "Generate a supportive but firm pop-up message suggesting the swap based on the mathematical improvement."
            }
        return prompt







# 2 LLM

# Making Generative ai -> generate message for the user to inform them that the chosen product is not suitable

LLM

import json

import google.generativeai as genai # this is great for generating quick pop up messages

genai.configure(api_key="YOUR_GEMINI_API_KEY")

model = genai.GenerativeAI(model_name="gemini-1.5-flash")

def get_dietary_advice(user_data, calculated_metrics):

"""

Sends structured data to the LLM to generate a personalized pop-up.

"""

# THE SYSTEM PROMPT: This defines the 'Brain' and 'Rules' of your LLM  --> ** details : adjust later , not important right now

system_instruction = """

You are a professional Clinical Dietitian for a mobile app.

Your job is to provide a brief, supportive, and scientifically accurate recommendation.

GUIDELINES:

1. Output MUST start with one of three labels: [WARNING], [SUITABLE], or [GREAT CHOICE].

2. Follow the label with 1-2 sentences explaining why, based on the specific nutrient values.

3. If the user has a disease (e.g., Diabetes), prioritize that context.

4. Keep the tone helpful, never judgmental.

"""

# THE DATA PACKET: Combining user context + mathematical facts -------> agent must do this and give the info to the llm (me)

user_prompt = f"""

USER PROFILE:

- Disease: {user_data['disease']}

- Primary Concern: {user_data['concern']}

PRODUCT DATA (Calculated by Agent):

- Product Name: {calculated_metrics['product_name']}

- Health Score: {calculated_metrics['score']}/100

- Risk Flag: {calculated_metrics['risk_level']} (High/Med/Low)

- Key Fact: {calculated_metrics['primary_reason']}

Generate the pop-up message.

"""

# API CALL (Simulated for this snippet)

# response = openai.chat.completions.create(

#     model="gpt-4o",

#     messages=[

#         {"role": "system", "content": system_instruction},

#         {"role": "user", "content": user_prompt}

#     ]

# )

# SIMULATED LLM OUTPUT based on the prompt logic:

if calculated_metrics['risk_level'] == "High":

return f"[WARNING] This {calculated_metrics['product_name']} contains {calculated_metrics['primary_reason']}. For someone with {user_data['disease']}, this could lead to a sudden spike in blood pressure. Try the low-sodium version instead!"

else:

return f"[GREAT CHOICE] This is perfectly aligned with your {user_data['disease']} diet. It is high in fiber and low in processed sugars."

# --- EXAMPLE USAGE ---

# 1. This comes from your User Profile database

user = {"name": "Sara", "disease": "Hypertension", "concern": "Sodium intake"}

# 2. This comes from your 'Deterministic' Math Agent (from previous steps)

results_from_agent = {

"product_name": "Instant Ramen Noodles",

"score": 20,

"risk_level": "High",

"primary_reason": "1800mg of Sodium (78% of Daily Value)"

}

# 3. Get the message

popup_message = get_dietary_advice(user, results_from_agent)

print(popup_message)