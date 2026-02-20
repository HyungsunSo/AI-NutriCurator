"""
식품원재료.csv  ←→  가공식품2500건.csv  영양성분 매칭 스크립트
================================================================
실행 방법:
  pip install pandas scikit-learn anthropic tqdm

  # LLM 없이 TF-IDF만 사용 (빠르지만 정확도 낮음)
  python food_matcher.py

  # Claude API 사용 (권장 – 정확도 높음)
  ANTHROPIC_API_KEY=sk-ant-... python food_matcher.py

출력:
  식품원재료_영양성분추가.csv  : 영양성분 컬럼이 추가된 최종 결과
  matching_log.csv            : 매칭 상세 로그 (검증용)
"""

import os, re, json, time
import pandas as pd
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from tqdm import tqdm

# ────────────────────────────────────────────────────────
# ▶ 설정 (필요에 따라 수정)
# ────────────────────────────────────────────────────────
RAW_CSV        = "식품원재료.csv"
DB_CSV         = "가공식품2500건.csv"
OUTPUT_CSV     = "식품원재료_영양성분추가.csv"
LOG_CSV        = "matching_log.csv"

TOP_K               = 5     # TF-IDF 후보 수
TFIDF_MIN_SCORE     = 0.15  # 이 점수 미만이면 매칭 불가로 처리 (LLM 호출 생략)
LLM_BATCH_SIZE      = 20    # 1회 LLM 호출당 제품 수
LLM_MODEL           = "claude-sonnet-4-20250514"

# 가져올 영양성분 컬럼
NUTRITION_COLS = [
    "에너지(kcal)",
    "단백질(g)",
    "지방(g)",
    "회분(g)",
    "탄수화물(g)",
    "당류(g)",
    "나트륨(mg)",
    "콜레스테롤(mg)",
    "포화지방산(g)",
    "트랜스지방산(g)",
    "영양성분함량기준량",
    "1회섭취참고량",
    "식품중량",
]

# 가공식품DB 컬럼명이 다를 경우 매핑 (키=실제, 값=표준)
COL_ALIAS = {
    "열량(kcal)": "에너지(kcal)",
}


# ────────────────────────────────────────────────────────
# 1. 데이터 로드
# ────────────────────────────────────────────────────────
def load_data():
    print("\n[1/4] 데이터 로드")
    # 식품원재료: 첫 행이 한글 헤더(중복)이므로 skiprows=1
    raw = pd.read_csv(RAW_CSV, encoding="utf-8-sig", skiprows=1)
    raw.columns = raw.columns.str.strip()
    raw["제품명"] = raw["제품명"].fillna("").astype(str).str.strip()
    raw = raw[raw["제품명"] != ""].reset_index(drop=True)

    db = pd.read_csv(DB_CSV, encoding="utf-8-sig")
    db = db.rename(columns=COL_ALIAS)
    db.columns = db.columns.str.strip()
    db["식품명"] = db["식품명"].fillna("").astype(str).str.strip()

    print(f"  ✔ 식품원재료: {len(raw):,}건")
    print(f"  ✔ 가공식품DB: {len(db):,}건")

    avail  = [c for c in NUTRITION_COLS if c in db.columns]
    missing = [c for c in NUTRITION_COLS if c not in db.columns]
    if missing:
        print(f"  ⚠ 가공식품DB에 없는 컬럼 (무시됨): {missing}")
    return raw, db, avail


# ────────────────────────────────────────────────────────
# 2. TF-IDF 인덱스 + 후보 추출
# ────────────────────────────────────────────────────────
def normalize(text: str) -> str:
    """특수문자 제거 + 소문자 정규화"""
    text = re.sub(r"[^\w가-힣a-zA-Z0-9]", " ", str(text))
    return text.lower().strip()


def build_tfidf(db: pd.DataFrame):
    print("\n[2/4] TF-IDF 인덱스 구축")
    corpus = db["식품명"].apply(normalize).tolist()
    vec = TfidfVectorizer(
        analyzer="char_wb",   # 문자 n-gram (한국어 형태소 분석기 없이도 효과적)
        ngram_range=(2, 4),
        min_df=1,
        sublinear_tf=True,
    )
    mat = vec.fit_transform(corpus)
    print(f"  ✔ 행렬 크기: {mat.shape[0]:,} × {mat.shape[1]:,}")
    return vec, mat


def get_candidates(query: str, vec, mat, db, top_k=TOP_K):
    q_vec = vec.transform([normalize(query)])
    scores = cosine_similarity(q_vec, mat)[0]
    idx = np.argsort(scores)[::-1][:top_k]
    return [
        {"index": int(i), "식품명": db.iloc[i]["식품명"], "score": float(scores[i])}
        for i in idx
    ]


def extract_all_candidates(raw, db, vec, mat):
    print("  후보 추출 중...")
    all_cands = []
    for name in tqdm(raw["제품명"], desc="  TF-IDF"):
        all_cands.append(get_candidates(name, vec, mat, db))
    return all_cands


# ────────────────────────────────────────────────────────
# 3. Claude API 배치 매칭
# ────────────────────────────────────────────────────────
SYSTEM_PROMPT = """당신은 식품 데이터 매칭 전문가입니다.

입력: JSON 배열. 각 원소는 {"id": 번호, "query": 검색할제품명, "candidates": [{"index":숫자,"식품명":이름}, ...]}
출력: JSON 배열만 (설명 없이). 형식: [{"id": 번호, "matched_index": 숫자또는null, "reason": "간단한이유"}, ...]

매칭 규칙:
- 핵심 품목명(닭가슴살, 어묵, 팝콘, 두부 등)이 같아야 함
- 맛/향 차이(마늘맛 vs 오리지널)는 허용
- 브랜드 차이는 허용
- 완전히 다른 식품이거나 후보가 모두 부적합하면 null
- 유사도가 낮고 연관이 없으면 null (억지 매칭 금지)"""


def llm_match_batch(client, batch: list) -> list:
    payload = json.dumps(batch, ensure_ascii=False)
    for attempt in range(3):
        try:
            resp = client.messages.create(
                model=LLM_MODEL,
                max_tokens=2048,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": payload}],
            )
            raw_text = resp.content[0].text.strip()
            raw_text = re.sub(r"```[^\n]*\n?", "", raw_text).strip()
            return json.loads(raw_text)
        except Exception as e:
            print(f"\n  ⚠ LLM 오류 (재시도 {attempt+1}/3): {e}")
            time.sleep(2 ** attempt)
    # 실패 시 폴백: top-1 후보
    return [
        {"id": b["id"],
         "matched_index": b["candidates"][0]["index"] if b["candidates"] else None,
         "reason": "LLM_FAILED_FALLBACK"}
        for b in batch
    ]


def run_llm_matching(raw, all_cands, client):
    print("  LLM 매칭 중...")
    n = len(raw)
    matched_db_idx = [None] * n
    reasons        = [""] * n

    # 유사도가 너무 낮으면 LLM 생략 (API 비용 절감)
    needs_llm = [
        i for i, cands in enumerate(all_cands)
        if cands and cands[0]["score"] >= TFIDF_MIN_SCORE
    ]
    skip_count = n - len(needs_llm)
    print(f"  LLM 호출 대상: {len(needs_llm):,}건  |  자동 null: {skip_count:,}건 (유사도 {TFIDF_MIN_SCORE} 미만)")

    batch_input = [
        {
            "id": i,
            "query": raw.iloc[i]["제품명"],
            "candidates": [{"index": c["index"], "식품명": c["식품명"]} for c in all_cands[i]],
        }
        for i in needs_llm
    ]

    for start in tqdm(range(0, len(batch_input), LLM_BATCH_SIZE), desc="  LLM 배치"):
        batch = batch_input[start: start + LLM_BATCH_SIZE]
        results = llm_match_batch(client, batch)
        for r in results:
            idx = r["id"]
            matched_db_idx[idx] = r.get("matched_index")
            reasons[idx]        = r.get("reason", "")
        time.sleep(0.3)  # rate limit 방지

    return matched_db_idx, reasons


# ────────────────────────────────────────────────────────
# 4. 병합 & 저장
# ────────────────────────────────────────────────────────
def merge_and_save(raw, db, all_cands, matched_db_idx, reasons, avail_cols):
    print("\n[4/4] 영양성분 병합 & 저장")

    raw["_매칭식품명"]    = [db.iloc[mi]["식품명"] if mi is not None else "" for mi in matched_db_idx]
    raw["_tfidf최고점수"] = [round(cands[0]["score"], 4) if cands else 0.0 for cands in all_cands]
    raw["_매칭이유"]      = reasons

    for col in avail_cols:
        raw[col] = pd.NA

    for i, mi in enumerate(matched_db_idx):
        if mi is not None:
            for col in avail_cols:
                raw.at[i, col] = db.iloc[mi][col]

    raw.to_csv(OUTPUT_CSV, index=False, encoding="utf-8-sig")

    log_cols = ["제품명", "_매칭식품명", "_tfidf최고점수", "_매칭이유"] + avail_cols[:4]
    raw[[c for c in log_cols if c in raw.columns]].to_csv(LOG_CSV, index=False, encoding="utf-8-sig")

    matched = sum(1 for m in matched_db_idx if m is not None)
    print(f"\n{'='*52}")
    print(f"  전체:       {len(raw):>8,}건")
    print(f"  매칭 성공:  {matched:>8,}건  ({matched/len(raw)*100:.1f}%)")
    print(f"  매칭 실패:  {len(raw)-matched:>8,}건")
    print(f"{'='*52}")
    print(f"  ✅ 결과: {OUTPUT_CSV}")
    print(f"  📋 로그: {LOG_CSV}")


# ────────────────────────────────────────────────────────
# 메인
# ────────────────────────────────────────────────────────
if __name__ == "__main__":
    raw, db, avail_cols = load_data()
    vec, mat = build_tfidf(db)

    print("\n[3/4] 매칭 실행")
    all_cands = extract_all_candidates(raw, db, vec, mat)

    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if api_key:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        print(f"  ✔ Claude API 사용 ({LLM_MODEL})")
        matched_db_idx, reasons = run_llm_matching(raw, all_cands, client)
    else:
        print("  ⚠ ANTHROPIC_API_KEY 없음 → TF-IDF top-1으로 자동 선택")
        matched_db_idx = [
            cands[0]["index"] if cands and cands[0]["score"] >= TFIDF_MIN_SCORE else None
            for cands in all_cands
        ]
        reasons = [
            f"tfidf:{cands[0]['score']:.3f}" if cands and cands[0]["score"] >= TFIDF_MIN_SCORE else "score_too_low"
            for cands in all_cands
        ]

    merge_and_save(raw, db, all_cands, matched_db_idx, reasons, avail_cols)
