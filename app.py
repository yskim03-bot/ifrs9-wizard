"""
IFRS 9 (K-IFRS 1109) 금융자산 분류 마법사 v3
─────────────────────────────────────────────
실행 방법:
    pip install streamlit pdfplumber python-docx
    streamlit run app.py

v3 신규 기능:
    · AI 계약서 분석 (하이브리드 모드)
      - PDF / DOCX 업로드 → 키워드 기반 자동 분석
      - Step 0~2 자동 제안 → 사용자 승인/수정
      - 승인 후 Step 3(사업모형) 직접 선택으로 점프
    · 분석 신뢰도(confidence) + 근거 조항 표시
    · 단계별 수동 오버라이드 가능
"""

from __future__ import annotations
import io
import re
import streamlit as st

# ── 선택적 임포트 (설치 안 된 경우 대비) ─────────────────────────────────────
try:
    import pdfplumber
    _PDF_OK = True
except ImportError:
    _PDF_OK = False

try:
    from docx import Document as DocxDocument
    _DOCX_OK = True
except ImportError:
    _DOCX_OK = False


# ══════════════════════════════════════════════════════════════════════════════
# 0. SPPI 불충족 사례 딕셔너리 (JSON 구조 — 추후 DB 교체 가능)
# ══════════════════════════════════════════════════════════════════════════════
SPPI_CASES_DICT: dict = {
    "case_F": {
        "id": "case_F", "label": "상품F — 전환사채", "category": "지분연동",
        "instrument_desc": "확정수량의 발행자 지분상품으로 전환가능한 채권",
        "sppi_fail": True,
        "reason": "계약상 현금흐름이 기본대여계약과 일관되지 않는 수익 반영 — 발행자 지분가치에 연계됨",
        "standard_ref": ["§B4.1.14", "§B4.1.7A"],
        "judgment_criteria": "금융자산 주계약 시 내재파생 분리불가(§4.3.2). 전체 SPPI 테스트. 지분가치 연동=§B4.1.7A 위반",
    },
    "case_G": {
        "id": "case_G", "label": "상품G — 역변동금리", "category": "TVM역방향",
        "instrument_desc": "역변동금리(시장이자율과 반비례) 대여금",
        "sppi_fail": True,
        "reason": "이자금액이 원금잔액의 화폐 시간가치 대가가 아님. 금리상승 시 이자 감소",
        "standard_ref": ["§B4.1.14", "§4.1.3⑵"],
        "judgment_criteria": "이자율 방향 확인. 역방향이면 TVM 대가 결여 → FVPL",
    },
    "case_H": {
        "id": "case_H", "label": "상품H — 이자이연+복리미발생", "category": "이자이연",
        "instrument_desc": "영구금융상품 — 지급여력 부족 시 이자이연 가능, 이연이자에 복리 미발생",
        "sppi_fail": True,
        "reason": "이자이연 가능 + 이연이자 복리 미발생 → 이자가 TVM의 진정한 대가가 아님",
        "standard_ref": ["§B4.1.14", "§4.1.3⑵"],
        "judgment_criteria": "이연이자에 복리가 붙으면 SPPI 가능. 영구적 특성 자체는 불충족 이유 아님",
    },
    "case_I": {
        "id": "case_I", "label": "상품I — 탄소가격지수(시장추적)", "category": "비대여변수연동",
        "instrument_desc": "매 보고기간 시장 탄소가격지수 변동 추적하여 이자율 조정 대여금",
        "sppi_fail": True,
        "reason": "기본대여위험·원가가 아닌 탄소가격지수(비대여 변수)에 따라 현금흐름 변동",
        "standard_ref": ["§B4.1.14 상품I", "§B4.1.8A"],
        "judgment_criteria": "cf. 상품EA(탄소배출 목표달성 고정bp 조정): 유의적 차이 없으면 SPPI 가능(§B4.1.10A)",
    },
    "case_road": {
        "id": "case_road", "label": "유료도로 통행량 연동", "category": "기초자산성과연동",
        "instrument_desc": "차량 통행수가 많을수록 현금흐름이 증가하는 금융자산",
        "sppi_fail": True,
        "reason": "계약상 현금흐름이 비금융자산(유료도로) 사용량 성과에 연동 — 기본대여계약 불일치",
        "standard_ref": ["§B4.1.16", "§B4.1.7A"],
        "judgment_criteria": "비소구 특성 자체는 불충족 아님. look-through 결과 기초자산 성과 연동 여부 판단",
    },
    "case_equity_idx": {
        "id": "case_equity_idx", "label": "주가지수 연동 이자·원금", "category": "지분연동",
        "instrument_desc": "이자·원금이 주가·주가지수 변동에 연동되는 채무상품",
        "sppi_fail": True,
        "reason": "기본대여계약 무관 위험(주식시장 위험)에 노출. 레버리지 동반 가능",
        "standard_ref": ["§B4.1.7A", "§B4.1.9"],
        "judgment_criteria": "지분위험 익스포저 = §B4.1.7A 핵심원칙 위반",
    },
    "case_profit": {
        "id": "case_profit", "label": "이익참가사채", "category": "채무자성과연동",
        "instrument_desc": "이자가 채무자의 순이익·수익의 일정 비율로 결정되는 채무상품",
        "sppi_fail": True,
        "reason": "채무자 사업성과에 연동된 수익 반영 → 기본대여계약 불일치",
        "standard_ref": ["§B4.1.7A", "§B4.1.8A"],
        "judgment_criteria": "순전히 신용위험 변동 보상인 구조라면 예외적 SPPI 가능",
    },
    "case_leverage": {
        "id": "case_leverage", "label": "레버리지 내재 상품", "category": "레버리지",
        "instrument_desc": "독립 옵션, 선도계약, 스왑 등 레버리지 내재 금융자산",
        "sppi_fail": True,
        "reason": "레버리지는 현금흐름 변동성을 이자의 경제적 특성을 초과하여 높임 → 이자 성격 상실",
        "standard_ref": ["§B4.1.9"],
        "judgment_criteria": "캡·플로어는 레버리지 없으면 SPPI 가능(§B4.1.11). 독립 옵션·선도·스왑은 항상 레버리지",
    },
    "case_tvm": {
        "id": "case_tvm", "label": "TVM 변형 — 이자율 기간 불일치", "category": "TVM변형",
        "instrument_desc": "이자기산기간 불일치: 1년이자율로 매월 재설정 / 5년만기에 5년이자율로 6개월 재설정",
        "sppi_fail": True,
        "reason": "TVM 요소 변형. 벤치마크 현금흐름과 합리적 시나리오에서 유의적 차이 가능",
        "standard_ref": ["§B4.1.9B", "§B4.1.9C", "§B4.1.9D"],
        "judgment_criteria": "규제이자율 TVM 대용 예외(§B4.1.9E). 미미한 영향이면 무시(§B4.1.18)",
    },
    "case_nonrecourse": {
        "id": "case_nonrecourse", "label": "지분담보 비소구 대여금", "category": "기초자산성과연동",
        "instrument_desc": "지분포트폴리오 담보 비소구 대여금 — 지분가격 하락 시 은행 손실",
        "sppi_fail": True,
        "reason": "채권자가 지분가격 하락 위험(풋옵션 동일 경제효과) 부담. 현금흐름이 지분성과에 연동",
        "standard_ref": ["§B4.1.16A", "§B4.1.17"],
        "judgment_criteria": "비소구 자체는 FVPL 이유 아님. look-through 결과 지분위험 노출 → SPPI 불충족",
    },
    "case_embedded_fa": {
        "id": "case_embedded_fa", "label": "금융자산 주계약 내재파생", "category": "내재파생(FA주계약)",
        "instrument_desc": "채무상품 주계약에 내재된 지분연계 이자·원금 지급계약",
        "sppi_fail": True,
        "reason": "금융자산 주계약 → §4.3.2 분리 금지. 복합계약 전체 SPPI 테스트 시 지분연계로 불충족",
        "standard_ref": ["§4.3.2", "§B4.3.5⑶"],
        "judgment_criteria": "금융부채 주계약과의 핵심 차이: 금융자산 주계약에는 내재파생 분리 금지",
    },
    "case_A_ok": {
        "id": "case_A_ok", "label": "상품A — 인플레이션 연계 (SPPI 충족 참고)",
        "category": "참고:SPPI충족",
        "instrument_desc": "발행통화 인플레이션지수 연계, 비레버리지, 원금 보장 채권",
        "sppi_fail": False,
        "reason": "SPPI 충족: 인플레이션 연계는 TVM을 현행 수준으로 재설정 — TVM 대가에 해당",
        "standard_ref": ["§B4.1.13 상품A", "§B4.1.7A"],
        "judgment_criteria": "채무자 성과·주가지수 추가 연계 시 불충족. 비레버리지 조건 필수 확인",
    },
}


# ══════════════════════════════════════════════════════════════════════════════
# 1. 파일 텍스트 추출
# ══════════════════════════════════════════════════════════════════════════════

def extract_text(file) -> str:
    """PDF 또는 DOCX 파일에서 텍스트 추출"""
    name = file.name.lower()
    if name.endswith(".pdf"):
        if not _PDF_OK:
            return "[오류] pdfplumber 라이브러리가 설치되지 않았습니다. pip install pdfplumber"
        try:
            raw = file.read()
            pages = []
            with pdfplumber.open(io.BytesIO(raw)) as pdf:
                for page in pdf.pages:
                    t = page.extract_text()
                    if t:
                        pages.append(t)
            return "\n".join(pages)
        except Exception as e:
            return f"[오류] PDF 추출 실패: {e}"

    if name.endswith(".docx"):
        if not _DOCX_OK:
            return "[오류] python-docx 라이브러리가 설치되지 않았습니다. pip install python-docx"
        try:
            raw = file.read()
            doc = DocxDocument(io.BytesIO(raw))
            return "\n".join(p.text for p in doc.paragraphs if p.text.strip())
        except Exception as e:
            return f"[오류] DOCX 추출 실패: {e}"

    return "[오류] 지원하지 않는 파일 형식입니다. PDF 또는 DOCX만 지원합니다."


# ══════════════════════════════════════════════════════════════════════════════
# 2. AI 키워드 분석 엔진
# ══════════════════════════════════════════════════════════════════════════════

# 분석 규칙 테이블
# 각 항목: (단계ID, 제안값, 키워드 목록, 신뢰도, 근거 문구, 기준서 조항)
_RULES: list[tuple] = [
    # ── STEP 0: 자산 성격 ────────────────────────────────────────────────────
    ("s_asset", "hybrid",
     ["전환권", "전환사채", "전환청구권", "전환가격", "상환전환우선주", "RCPS",
      "신종자본증권", "조건부전환", "CoCo", "코코본드"],
     "high", "전환권·전환사채·신종자본증권 관련 조항 감지", "§4.3.2"),

    ("s_asset", "equity",
     ["보통주", "우선주", "출자금", "주주", "배당", "의결권", "신주발행", "지분율"],
     "high", "지분·주주 관련 조항 감지", "§4.1.4"),

    ("s_asset", "deriv",
     ["금리스왑", "통화스왑", "이자율스왑", "선물환", "풋옵션", "콜옵션", "파생상품계약"],
     "high", "독립 파생상품 계약 조항 감지", "§4.1.4 / §B4.1.9"),

    ("s_asset", "debt",
     ["원금", "이자율", "사채", "채권", "대여금", "만기", "원리금", "회사채",
      "국채", "지방채", "금융채", "후순위채", "선순위채", "ABS", "MBS", "CLO"],
     "medium", "채권·대여금 관련 조항 감지", "§4.1.2"),

    # ── STEP 1: 주계약 성격 (hybrid일 때만 유효) ─────────────────────────────
    ("s_host", "fa_host",
     ["전환사채", "전환권부사채", "신주인수권부사채", "BW", "CB", "EB",
      "교환사채", "신종자본증권", "영구채", "조건부자본증권"],
     "high", "채권을 주계약으로 하는 복합계약 조항 감지", "§4.3.2"),

    ("s_host", "other_host",
     ["금융부채", "리스", "임차", "운용리스", "상품공급계약", "서비스계약"],
     "medium", "비금융자산·금융부채를 주계약으로 하는 조항 감지", "§4.3.3"),

    # ── STEP 2-①: SPPI 불충족 신호 ──────────────────────────────────────────
    ("s_sppi1", "fail_equity",
     ["전환권", "전환가격", "주가연동", "주가지수연동", "주식전환", "주가기준",
      "코스피연동", "S&P연동", "KOSPI"],
     "high", "주가·지분가치 연동 현금흐름 조항 감지", "§B4.1.14 / §B4.1.7A"),

    ("s_sppi1", "fail_profit",
     ["이익참가", "순이익연동", "수익연동", "이익배분", "성과연동이자",
      "매출연동", "이익률 기준"],
     "high", "채무자 순이익·수익 연동 이자 조항 감지", "§B4.1.7A / §B4.1.8A"),

    ("s_sppi1", "fail_inverse",
     ["역변동금리", "inverse floater", "인버스 플로터", "금리하락시 이자증가",
      "시장금리 반비례"],
     "high", "역변동금리 조항 감지", "§B4.1.14 / §4.1.3⑵"),

    ("s_sppi1", "fail_defer",
     ["이자이연", "이자지급 유예", "이자 미지급", "영구채", "영구사채",
      "이자지급 선택권", "발행자 재량 이자"],
     "high", "이자이연·영구채 조항 감지", "§B4.1.14 / §4.1.3⑵"),

    ("s_sppi1", "fail_commodity",
     ["탄소가격", "원자재연동", "금가격연동", "유가연동", "상품지수연동",
      "탄소배출권", "원자재지수"],
     "high", "원자재·탄소가격지수 연동 조항 감지", "§B4.1.14 / §B4.1.8A"),

    ("s_sppi1", "fail_leverage",
     ["레버리지", "파생내재", "변동성증폭", "승수효과", "선도내재", "스왑내재"],
     "medium", "레버리지 내재 조항 감지", "§B4.1.9"),

    ("s_sppi1", "none",
     ["고정금리", "변동금리", "SOFR", "EURIBOR", "CD금리", "기준금리",
      "원리금", "원금 및 이자", "이자지급일"],
     "medium", "단순 고정·변동금리 원리금 구조 감지", "§B4.1.7A"),

    # ── STEP 2-②: TVM ────────────────────────────────────────────────────────
    ("s_sppi2", "tvm_ok",
     ["3개월 CD금리", "91일물", "3M SOFR", "1개월", "분기별 재설정",
      "고정이자율", "연 3%", "연 4%", "연 5%"],
     "medium", "이자기산기간과 이자율 기간 일치 구조 감지", "§B4.1.9B"),

    # ── STEP 2-③: 계약조건 ───────────────────────────────────────────────────
    ("s_sppi3", "clause_ok",
     ["중도상환", "조기상환", "콜옵션", "만기 전 상환"],
     "medium", "중도상환 조항 감지 (내용에 따라 SPPI 충족 여부 추가 확인 필요)", "§B4.1.10~12"),

    # ── STEP 2-④: 트랑슈 ────────────────────────────────────────────────────
    ("s_sppi4", "tranche_pass",
     ["ABS", "MBS", "CLO", "CDO", "CBO", "유동화", "특수목적법인", "SPC", "트랑슈",
      "자산유동화", "선순위", "후순위"],
     "medium", "유동화·트랑슈 구조 조항 감지 — Look-through 분석 필요", "§B4.1.20~26"),

    ("s_sppi4", "tranche_no",
     ["단일 발행자", "직접 발행", "보증사채", "무보증사채"],
     "low", "단일 발행자 구조 신호 감지", "§B4.1.20"),
]

# 한 단계에 복수 키워드 그룹이 충돌할 경우 우선순위
_PRIORITY = {
    "s_asset":  ["hybrid", "equity", "deriv", "debt"],
    "s_host":   ["fa_host", "other_host"],
    "s_sppi1":  ["fail_equity", "fail_profit", "fail_inverse", "fail_defer",
                 "fail_commodity", "fail_leverage", "none"],
    "s_sppi2":  ["tvm_ok"],
    "s_sppi3":  ["clause_ok"],
    "s_sppi4":  ["tranche_pass", "tranche_no"],
}

_CONF_LABEL = {"high": "높음 🟢", "medium": "중간 🟡", "low": "낮음 🔴"}
_CONF_COLOR = {"high": "#E1F5EE", "medium": "#FAEEDA", "low": "#FCEBEB"}


def ai_analyze(text: str) -> dict:
    """
    계약서 텍스트에서 키워드를 스캔하여 분류 제안을 반환.

    Returns:
        {
          "proposed_answers": {step_id: value},
          "evidence_items":   [{step_id, value, keywords_found, basis, std_ref, confidence}],
          "conflict_flags":   [{step_id, message}],
          "skippable_steps":  [step_id, ...],
          "raw_hit_counts":   {step_id: {value: count}},
        }
    """
    # 1) 키워드 히트 집계
    hits: dict[str, dict[str, list[str]]] = {}  # {step: {val: [matched_kws]}}
    for step_id, val, kws, conf, basis, std_ref in _RULES:
        matched = [kw for kw in kws if kw.lower() in text.lower()]
        if matched:
            hits.setdefault(step_id, {}).setdefault(val, []).extend(matched)

    # 2) 충돌 감지 및 우선순위 적용
    proposed: dict[str, str] = {}
    evidence_items: list[dict] = []
    conflict_flags: list[dict] = []

    for step_id, priority_order in _PRIORITY.items():
        step_hits = hits.get(step_id, {})
        if not step_hits:
            continue

        # 충돌 확인
        matched_vals = [v for v in step_hits if step_hits[v]]
        if len(matched_vals) > 1:
            # 우선순위로 선택
            winner = next((v for v in priority_order if v in matched_vals), matched_vals[0])
            conflict_flags.append({
                "step_id": step_id,
                "message": (
                    f"복수 신호 감지: {', '.join(matched_vals)} "
                    f"→ 우선순위에 따라 **{winner}** 선택. 수동 확인 권장."
                ),
            })
        else:
            winner = matched_vals[0]

        # 신뢰도 결정: 히트 수 기반
        kw_count = len(step_hits.get(winner, []))
        conf_level = "high" if kw_count >= 3 else ("medium" if kw_count >= 1 else "low")

        # 근거 룰 찾기
        rule = next(
            (r for r in _RULES if r[0] == step_id and r[1] == winner),
            (step_id, winner, [], "medium", "자동 감지", "—"),
        )

        proposed[step_id] = winner
        evidence_items.append({
            "step_id":       step_id,
            "value":         winner,
            "keywords_found": step_hits.get(winner, []),
            "basis":         rule[4],
            "std_ref":       rule[5],
            "confidence":    conf_level,
        })

    # 3) 스킵 가능 단계 결정
    # s_bm은 항상 사용자가 직접 선택 — 스킵 불가
    skippable = [s for s in proposed if s != "s_bm"]

    # 4) 트랑슈 감지 시 s_sppi4 포함
    return {
        "proposed_answers": proposed,
        "evidence_items":   evidence_items,
        "conflict_flags":   conflict_flags,
        "skippable_steps":  skippable,
        "raw_hit_counts":   {s: {v: len(kws) for v, kws in hits[s].items()} for s in hits},
    }


# ══════════════════════════════════════════════════════════════════════════════
# 3. 분류 결과 계산 로직 (원본 유지)
# ══════════════════════════════════════════════════════════════════════════════

def sppi_fail_result(fail_key: str, case_key) -> dict:
    msgs = {
        "fail_equity":    "주가·주가지수 연동 이자·원금.",
        "fail_commodity": "원자재·탄소가격지수(시장추적) 연동.",
        "fail_profit":    "채무자 순이익·수익 비율 연동.",
        "fail_inverse":   "역변동금리 — 이자가 TVM 대가가 아닙니다. 금리상승 시 이자 감소.",
        "fail_leverage":  "레버리지 내재 — 현금흐름 변동성이 이자의 경제적 특성을 초과합니다.",
        "fail_defer":     "이자이연 가능 + 이연이자 복리 미발생. 단, 이연이자에 복리가 붙으면 SPPI 가능.",
        "tvm_fail":       "TVM 변형이 유의적.",
        "clause_fail":    "계약조건으로 원리금 불일치 현금흐름 발생(§B4.1.12 예외 미해당).",
        "tranche_fail":   "트랑슈 Look-through 조건 불충족 또는 평가 불가.",
    }
    refs_map = {
        "fail_equity":   ["§B4.1.7A", "§B4.1.14", "§4.1.4"],
        "fail_commodity":["§B4.1.8A", "§B4.1.14 상품I", "§4.1.4"],
        "fail_profit":   ["§B4.1.7A", "§B4.1.8A", "§4.1.4"],
        "fail_inverse":  ["§B4.1.14", "§4.1.3⑵", "§4.1.4"],
        "fail_leverage": ["§B4.1.9", "§4.1.4"],
        "fail_defer":    ["§B4.1.14", "§4.1.3⑵", "§4.1.4"],
        "tvm_fail":      ["§B4.1.9C", "§B4.1.9D", "§4.1.4"],
        "clause_fail":   ["§B4.1.10", "§B4.1.16", "§4.1.4"],
        "tranche_fail":  ["§B4.1.26", "§B4.1.21", "§4.1.4"],
    }
    return {
        "classification": "FVPL", "label": "당기손익-공정가치 (FVPL) — SPPI 불충족",
        "color": "red", "reason": "SPPI 테스트 불충족. " + msgs.get(fail_key, ""),
        "refs": refs_map.get(fail_key, ["§4.1.4"]),
        "ecl": False, "recycling": False, "recycling_note": None,
        "accounting": ["공정가치로 최초 인식 및 후속 측정",
                       "모든 공정가치 변동 → 당기손익", "ECL(손상) 적용 없음"],
        "warning": None, "case_key": case_key,
    }


def compute_result(ans: dict) -> dict:
    at = ans.get("s_asset")
    if at == "deriv":
        return {
            "classification": "FVPL", "label": "당기손익-공정가치 (FVPL)",
            "color": "red",
            "reason": "독립 파생상품은 항상 FVPL로 측정합니다. 레버리지 내재로 SPPI 불충족이며 AC·FVOCI 분류 불가.",
            "refs": ["§4.1.4", "§B4.1.9"], "ecl": False, "recycling": False, "recycling_note": None,
            "accounting": ["공정가치로 최초 인식 및 후속 측정", "모든 공정가치 변동 → 당기손익", "ECL(손상) 적용 없음"],
            "warning": None, "case_key": None,
        }
    if at == "hybrid":
        host = ans.get("s_host")
        if host == "other_host":
            sep = ans.get("s_sep")
            if sep == "sep_ok":
                return {
                    "classification": "FVPL", "label": "내재파생상품 FVPL 분리 + 주계약 별도 처리",
                    "color": "red",
                    "reason": "분리 3요건 충족. 내재파생상품은 FVPL로 측정하고, 주계약은 관련 기준서에 따라 별도 회계처리합니다.",
                    "refs": ["§4.3.3", "§4.3.4", "§B4.3.5"], "ecl": False, "recycling": False, "recycling_note": None,
                    "accounting": ["내재파생상품 → FVPL (공정가치 측정)",
                                   "주계약 → 관련 기준서 별도 처리",
                                   "재평가 금지(계약 유의적 변경 시 제외) [§B4.3.11]"],
                    "warning": "밀접관련 내재파생(§B4.3.8)은 분리하지 않습니다: 레버리지 없는 금리캡·플로어, 인플레이션 리스료, 단위연계특성 등",
                    "case_key": "case_embedded_fa",
                }
            return {
                "classification": "FVPL", "label": "복합계약 전체 → FVPL",
                "color": "red",
                "reason": "분리 3요건 미충족 또는 내재파생상품을 신뢰성 있게 측정할 수 없습니다. 복합계약 전체를 FVPL로 측정합니다.",
                "refs": ["§4.3.6", "§4.3.7"], "ecl": False, "recycling": False, "recycling_note": None,
                "accounting": ["복합계약 전체 → FVPL 측정", "공정가치 변동 전액 → 당기손익"],
                "warning": None, "case_key": "case_embedded_fa",
            }
    if at == "equity":
        trade = ans.get("s_eq_trade")
        if trade == "trade_yes":
            return {
                "classification": "FVPL", "label": "당기손익-공정가치 (FVPL) — 단기매매 지분",
                "color": "red",
                "reason": "단기매매 목적 지분상품은 FVPL로 측정합니다. FVOCI 취소불가 선택권 행사 불가.",
                "refs": ["§4.1.4"], "ecl": False, "recycling": False, "recycling_note": None,
                "accounting": ["공정가치로 측정", "모든 공정가치 변동 → 당기손익",
                               "배당 → 당기손익", "ECL(손상) 적용 없음"],
                "warning": None, "case_key": None,
            }
        if ans.get("s_eq_fvoci") == "fvoci_yes":
            return {
                "classification": "FVOCI", "label": "기타포괄손익-공정가치 (FVOCI) — 지분 취소불가 지정",
                "color": "blue",
                "reason": "단기매매가 아닌 지분상품에 대해 최초 인식시점에 FVOCI 취소불가 선택권을 행사하였습니다.",
                "refs": ["§4.1.4", "§5.7.5", "§5.7.6", "§B5.7.1"], "ecl": False, "recycling": False,
                "recycling_note": "지분상품 FVOCI: 처분 시에도 OCI 누적손익이 P&L로 재분류(Recycling)되지 않습니다. 자본 내 이전만 허용됩니다.",
                "accounting": ["공정가치 변동 전액 → OCI",
                               "배당(투자원가 회수 성격 제외) → 당기손익 [§B5.7.1]",
                               "처분 시 OCI 누적손익 → P&L 재분류 금지 (Recycling 없음) [§5.7.5]",
                               "ECL(손상) 규정 미적용"],
                "warning": "처분 시 OCI → P&L 재분류 없음(Recycling 금지). 손상(ECL) 인식하지 않음. 자본 내 이전만 허용.",
                "case_key": None,
            }
        return {
            "classification": "FVPL", "label": "당기손익-공정가치 (FVPL) — 지분 기본값",
            "color": "orange",
            "reason": "FVOCI 선택권을 행사하지 않은 비단기매매 지분상품은 FVPL로 측정합니다.",
            "refs": ["§4.1.4"], "ecl": False, "recycling": False, "recycling_note": None,
            "accounting": ["공정가치로 측정", "모든 공정가치 변동 → 당기손익", "배당 → 당기손익"],
            "warning": None, "case_key": None,
        }
    case_map = {"fail_equity": "case_equity_idx", "fail_commodity": "case_I",
                "fail_profit": "case_profit", "fail_inverse": "case_G",
                "fail_leverage": "case_leverage", "fail_defer": "case_H"}
    sp1 = ans.get("s_sppi1")
    if sp1 and sp1 != "none":
        return sppi_fail_result(sp1, case_map.get(sp1))
    if ans.get("s_sppi2") == "tvm_fail":
        return sppi_fail_result("tvm_fail", "case_tvm")
    if ans.get("s_sppi3") == "clause_fail":
        return sppi_fail_result("clause_fail", "case_road")
    if ans.get("s_sppi4") == "tranche_fail":
        return sppi_fail_result("tranche_fail", None)
    bm = ans.get("s_bm")
    if bm == "ambiguous":
        return {
            "classification": "FVPL", "label": "추가 검토 필요 → 잠정 FVPL",
            "color": "orange",
            "reason": ("입력된 정보만으로는 사업모형을 명확히 판단하기 어렵습니다. "
                       "내부보고체계, 과거 매도 이력, 관리자 보상 방식 등 추가 증거를 검토하십시오. "
                       "기준서·가이드라인 상충 시 보수적 접근으로 잠정 FVPL 분류합니다."),
            "refs": ["§B4.1.2B", "§B4.1.5"], "ecl": False, "recycling": False, "recycling_note": None,
            "accounting": ["잠정 FVPL로 처리 후 추가 검토", "사업모형 증거 문서화 필요"],
            "warning": "확정 분류 전 반드시 주요경영진 결정 근거(내부보고, 보상체계, 매도이력)를 문서화하십시오.",
            "case_key": None,
        }
    if bm == "trading":
        return {
            "classification": "FVPL", "label": "당기손익-공정가치 (FVPL) — 잔여범주",
            "color": "red", "reason": "공정가치 기준 관리·평가 또는 단기매매 포트폴리오 → FVPL 잔여범주.",
            "refs": ["§B4.1.5", "§B4.1.6", "§4.1.4"], "ecl": False, "recycling": False, "recycling_note": None,
            "accounting": ["공정가치로 측정", "모든 공정가치 변동 → 당기손익", "ECL(손상) 적용 없음"],
            "warning": None, "case_key": None,
        }
    fvo = ans.get("s_fvo")
    if fvo == "fvo_yes":
        return {
            "classification": "FVPL", "label": "당기손익-공정가치 (FVPL) — FVO 지정",
            "color": "orange",
            "reason": "회계불일치 해소를 위한 공정가치 지정선택권(FVO) 행사. 최초 인식시점에 취소불가로 지정합니다.",
            "refs": ["§4.1.5", "§B4.1.29~32"], "ecl": False, "recycling": False, "recycling_note": None,
            "accounting": ["공정가치로 측정", "모든 공정가치 변동 → 당기손익",
                           "최초 인식시점 지정·취소불가", "ECL(손상) 적용 없음"],
            "warning": "FVO 지정은 취소불가입니다. 최초 인식시점에 회계불일치 해소 요건을 면밀히 검토하십시오.",
            "case_key": None,
        }
    if bm == "hold":
        return {
            "classification": "AC", "label": "상각후원가 (AC)",
            "color": "green", "reason": "SPPI 충족 + 계약상 현금흐름 수취 목적 사업모형 → AC 측정.",
            "refs": ["§4.1.2", "§4.1.2⑴", "§B4.1.2C", "§B4.1.3A"], "ecl": True, "recycling": False, "recycling_note": None,
            "accounting": ["최초 인식: 공정가치 (거래원가 포함)",
                           "후속 측정: 유효이자율법 적용 상각후원가",
                           "이자수익 → 당기손익 (유효이자율법)",
                           "ECL(기대신용손실) 손상 모형 적용 [§5.5]",
                           "처분 시 장부금액과 수취대가 차이 → 당기손익"],
            "warning": None, "case_key": None,
        }
    if bm == "both":
        return {
            "classification": "FVOCI", "label": "기타포괄손익-공정가치 (FVOCI) — 채무상품",
            "color": "blue", "reason": "SPPI 충족 + 수취와 매도 둘 다가 목적인 사업모형 → FVOCI 측정.",
            "refs": ["§4.1.2A", "§4.1.2A⑴", "§B4.1.4A", "§B4.1.4C"], "ecl": True, "recycling": True, "recycling_note": None,
            "accounting": ["최초 인식: 공정가치", "후속 측정: 공정가치",
                           "이자수익·ECL(손상)·외환손익 → 당기손익",
                           "그 외 공정가치 변동 → OCI",
                           "처분 시 OCI 누적손익 → P&L 재분류 (Recycling 발생) [§5.7.2]"],
            "warning": "채무상품 FVOCI는 처분 시 OCI에 누적된 손익이 당기손익(P&L)으로 재분류(Recycling)됩니다. 지분상품 FVOCI와의 핵심 차이입니다.",
            "case_key": None,
        }
    return {
        "classification": "FVPL", "label": "당기손익-공정가치 (FVPL)",
        "color": "red", "reason": "분류 기준 미충족 — 잔여범주 FVPL 적용.",
        "refs": ["§4.1.4"], "ecl": False, "recycling": False, "recycling_note": None,
        "accounting": ["공정가치로 측정", "모든 공정가치 변동 → 당기손익"],
        "warning": None, "case_key": None,
    }


# ══════════════════════════════════════════════════════════════════════════════
# 4. 스텝 시퀀스 계산
# ══════════════════════════════════════════════════════════════════════════════

def get_step_sequence(ans: dict) -> list:
    at = ans.get("s_asset")
    if not at:
        return ["s_asset"]
    if at == "deriv":
        return ["s_asset"]
    if at == "equity":
        base = ["s_asset", "s_eq_trade"]
        if ans.get("s_eq_trade") == "trade_no":
            base.append("s_eq_fvoci")
        return base
    if at == "hybrid":
        base = ["s_asset", "s_host"]
        host = ans.get("s_host")
        if not host:
            return base
        if host == "fa_host":
            return base + _debt_sppi_seq(ans)
        return base + ["s_sep"]
    return ["s_asset"] + _debt_sppi_seq(ans)


def _debt_sppi_seq(ans: dict) -> list:
    seq = ["s_sppi1"]
    if not ans.get("s_sppi1") or ans.get("s_sppi1") != "none":
        return seq
    seq.append("s_sppi2")
    if ans.get("s_sppi2") == "tvm_fail":
        return seq
    seq.append("s_sppi3")
    if ans.get("s_sppi3") == "clause_fail":
        return seq
    seq.append("s_sppi4")
    if ans.get("s_sppi4") == "tranche_fail":
        return seq
    seq.append("s_bm")
    bm = ans.get("s_bm")
    if not bm or bm in ("trading", "ambiguous"):
        return seq
    seq.append("s_fvo")
    return seq


def is_terminal(ans: dict) -> bool:
    seq = get_step_sequence(ans)
    return seq[-1] in ans


# ══════════════════════════════════════════════════════════════════════════════
# 5. 스텝 정의 (STEP_DEFS)
# ══════════════════════════════════════════════════════════════════════════════

STEP_DEFS: dict = {
    "s_asset": {
        "tag": "",
        "title": "STEP 0 — 금융자산의 기본 성격",
        "ref": "§4.1.1",
        "desc": "IFRS 9 분류는 자산 성격 판별에서 시작합니다. 가장 적합한 항목을 선택하세요.",
        "helper": None,
        "options": [
            ("debt",   "📄 채무상품",                      "대여금·사채·채권 등 원금+이자 구조"),
            ("equity", "📈 지분상품",                      "보통주·우선주·기타 지분투자 (IAS 32 자본 정의 충족)"),
            ("deriv",  "🔄 독립 파생상품",                  "옵션·선도·스왑 등 — 주계약 없는 단독 파생"),
            ("hybrid", "⚠️ 복합계약 (주계약+내재파생상품)", "전환사채 등 — 내재파생상품 포함 복합금융상품"),
        ],
    },
    "s_host": {
        "tag": "🔴 예외처리",
        "title": "STEP 1 — 내재파생상품 분리 판단: 주계약의 성격",
        "ref": "§4.3.2 / §4.3.3",
        "desc": (
            "**IFRS 9 핵심 원칙 §4.3.2**: 주계약이 금융자산(채무)이면 내재파생상품을 분리하지 않고 "
            "복합계약 전체에 SPPI 테스트를 적용합니다. 이는 금융부채 주계약과의 결정적 차이입니다."
        ),
        "helper": None,
        "options": [
            ("fa_host",    "📄 주계약이 금융자산 (채무상품)",         "→ 내재파생 분리 금지(§4.3.2). 복합계약 전체를 채무상품으로 보고 SPPI 테스트 진행"),
            ("other_host", "🏢 주계약이 금융부채 또는 비금융자산",    "→ 분리 3요건 검토(§4.3.3) 필요"),
        ],
    },
    "s_sep": {
        "tag": "🔴 예외처리",
        "title": "STEP 1-1 — 내재파생상품 분리 3요건 충족 여부",
        "ref": "§4.3.3 / §B4.3.5 / §B4.3.8",
        "desc": (
            "① 경제적 특성·위험이 주계약과 밀접하게 관련되지 않음\n"
            "② 별도 계약 시 파생상품 정의 충족\n"
            "③ 복합계약 전체 공정가치 변동을 당기손익으로 인식하지 않음\n\n"
            "**밀접관련 → 분리 안함(§B4.3.8)**: 레버리지 없는 금리캡·플로어, 인플레이션 리스료, 단위연계특성 등"
        ),
        "helper": None,
        "options": [
            ("sep_ok",   "✅ 3요건 모두 충족 → 내재파생 분리 가능", "내재파생 → FVPL / 주계약 → 관련 기준서 별도 처리"),
            ("sep_fail", "❌ 3요건 미충족 또는 분리·측정 불가",     "복합계약 전체를 FVPL로 측정(§4.3.6)"),
        ],
    },
    "s_sppi1": {
        "tag": "🔵 SPPI 테스트 ①",
        "title": "STEP 2-① — 비대여 변수 연동·레버리지",
        "ref": "§B4.1.7A / §B4.1.8A / §B4.1.9",
        "desc": (
            "계약상 현금흐름이 기본대여계약(원리금 지급)과 일관되지 않는 변수에 연동되거나 "
            "레버리지를 포함합니까?\n\n*(de minimis 영향은 분류에 영향 없음 — §B4.1.18)*"
        ),
        "helper": None,
        "options": [
            ("fail_equity",   "❌ 주가·주가지수 연동 이자·원금",           "전환사채, 주가지수연동 이자 등 — 상품F 유형"),
            ("fail_commodity","❌ 원자재·탄소가격지수(시장추적형) 연동",   "금·원유·탄소가격지수 변동 추적 이자 — 상품I 유형"),
            ("fail_profit",   "❌ 채무자 순이익·수익 비율 연동",           "이익참가사채 등 (신용위험 보상 목적 제외)"),
            ("fail_inverse",  "❌ 역변동금리 — 시장이자율과 반비례",       "금리상승 시 이자 감소 구조 — 상품G 유형"),
            ("fail_leverage", "❌ 레버리지 포함 — 독립 옵션·선도·스왑 수준","현금흐름 변동성이 이자의 경제적 특성 초과"),
            ("fail_defer",    "❌ 이자이연 가능 + 이연이자 복리 미발생",   "이연된 이자에 추가 이자가 발생하지 않음 — 상품H 유형"),
            ("none",          "✅ 위 항목 해당 없음 — 다음 단계 계속",    "기본대여계약과 일관. SPPI 테스트 계속"),
        ],
    },
    "s_sppi2": {
        "tag": "🔵 SPPI 테스트 ②",
        "title": "STEP 2-② — TVM 요소 변형",
        "ref": "§B4.1.9B~9D",
        "desc": "이자율 재설정 방식이 화폐의 시간가치(TVM)를 제대로 반영합니까?",
        "helper": {
            "title": "💡 TVM 판단 도우미 — 보조 질문",
            "body": (
                "**\"이자율 재설정 주기와 해당 이자율의 기간이 일치합니까?\"**\n\n"
                "- ✅ 일치 예시: 1개월 이자율로 매월 재설정 / 3개월 이자율로 분기 재설정\n"
                "- ❌ 불일치 예시: 1년 이자율로 매월 재설정 / 5년 만기에 5년 이자율로 6개월마다 재설정\n\n"
                "불일치 → 벤치마크 현금흐름과 유의적 차이 여부 추가 평가 필요  \n"
                "규제이자율 예외(§B4.1.9E): 시간경과 대가와 대략 일관되면 TVM 대용치 인정"
            ),
        },
        "options": [
            ("tvm_ok",            "✅ 이자기산기간과 이자율 기간 일치 (또는 영향 미미)", "벤치마크 현금흐름과 유의적 차이 없음"),
            ("tvm_modified_minor","⚠️ 변형되나 유의적 차이 없음 (질적·양적 평가 확인)", "벤치마크 비교 결과 유의적 차이 없음 확인됨(§B4.1.9C)"),
            ("tvm_fail",          "❌ TVM 변형이 유의적 — 벤치마크와 유의적 차이",      "이자기산기간 불일치 재설정, 만기 초과 기간 이자율 등"),
        ],
    },
    "s_sppi3": {
        "tag": "🔵 SPPI 테스트 ③",
        "title": "STEP 2-③ — 계약조건 변경 (중도상환·만기연장 등)",
        "ref": "§B4.1.10 / §B4.1.11 / §B4.1.12",
        "desc": "계약조건이 원리금 지급과 일치하지 않는 현금흐름을 발생시킵니까?",
        "helper": None,
        "options": [
            ("clause_ok",       "✅ 없음 또는 SPPI 충족 계약조건만 존재",        "단순 고정·변동이자 / 미지급 원리금 실질 반영 중도상환(§B4.1.11)"),
            ("clause_exception","⚠️ 중도상환 조건 불충족이나 §B4.1.12 예외 적용","할인·할증 취득 + 중도상환금≈액면+미지급이자 + 초기FV미미"),
            ("clause_fail",     "❌ 원리금 불일치 현금흐름 발생 (예외 미해당)",   "주가지수 도달 시 금리재설정, 기초자산 성과 연동 비소구 등"),
        ],
    },
    "s_sppi4": {
        "tag": "🔵 SPPI 테스트 ④",
        "title": "STEP 2-④ — 계약상 연계 트랑슈 (Look-through)",
        "ref": "§B4.1.20~26",
        "desc": (
            "이 금융자산이 다른 금융상품 집합에 대한 지급과 계약상 연계된 트랑슈(Tranche) 구조입니까?\n\n"
            "**Look-through 3조건 §B4.1.21**: ①트랑슈 자체 SPPI ②기초집합 SPPI 특성 ③신용위험 노출도 ≤ 기초집합"
        ),
        "helper": None,
        "options": [
            ("tranche_no",  "✅ 트랑슈 구조 아님 — SPPI 충족",               "일반 채무상품으로 SPPI 충족"),
            ("tranche_pass","⚠️ 트랑슈 구조이나 Look-through 3조건 충족",    "3조건 모두 확인됨(§B4.1.21)"),
            ("tranche_fail","❌ 트랑슈 구조이며 조건 불충족 또는 평가 불가",  "최초 인식시점에 평가 불가 시 → FVPL(§B4.1.26)"),
        ],
    },
    "s_bm": {
        "tag": "🟢 사업모형 테스트",
        "title": "STEP 3 — 사업모형 테스트",
        "ref": "§4.1.1⑴ / §B4.1.2 / §B4.1.2B",
        "desc": (
            "포트폴리오(집합) 수준에서 주요 경영진이 결정한 사업 목적을 선택하세요.  \n"
            "**사업모형은 사실(fact)에 근거해야 합니다** — 내부보고, 보상체계, 과거 매도 이력 등으로 검증."
        ),
        "helper": None,
        "options": [
            ("hold",     "🏦 계약상 현금흐름 수취 (AC 모형)",          "이자·원금 만기 수취 중심. 신용위험 증가 시에만 매도. 이자수익·ECL 기준 내부보고"),
            ("both",     "⚖️ 수취 AND 매도 둘 다 필수 (FVOCI 모형)",   "유동성 관리·만기매칭·이자수익 유지 목적의 정기 매도 필수"),
            ("trading",  "📊 공정가치 실현·단기매매 (FVPL 잔여범주)",   "공정가치 기준 성과 관리·평가. 매도가 주된 현금흐름 창출 수단"),
            ("ambiguous","❓ 판단이 모호함 — 추가 검토 필요",           "내부보고체계, 과거 매도 이력, 관리자 보상 방식 등이 명확하지 않음"),
        ],
    },
    "s_fvo": {
        "tag": "🟡 FVO 최종 확인",
        "title": "STEP 4 — 당기손익 지정권(FVO) 최종 확인",
        "ref": "§4.1.5 / §B4.1.29~32",
        "desc": (
            "AC 또는 FVOCI로 분류 예정이지만, **회계불일치 해소**를 위해 FVPL로 지정하시겠습니까?\n\n"
            "FVO 요건: FVPL 지정으로 인식·측정 불일치(회계불일치)를 **제거하거나 유의적으로 감소**시킬 수 있는 경우.  \n"
            "⚠️ 한 번 지정하면 취소 불가(irrevocable)."
        ),
        "helper": None,
        "options": [
            ("fvo_yes","📌 예 — FVPL로 지정 (FVO, 취소불가)", "회계불일치 제거·유의적 감소 확인됨. 최초 인식시점 지정. 이후 취소 불가."),
            ("fvo_no", "✅ 아니오 — 원래 분류(AC/FVOCI) 유지","FVO 미적용. 분류 확정."),
        ],
    },
    "s_eq_trade": {
        "tag": "🟠 지분상품",
        "title": "STEP A-1 — 지분상품: 단기매매 목적 보유 여부",
        "ref": "§4.1.4",
        "desc": ("단기간 내 매도를 주된 목적으로 취득하거나, "
                 "최근에 취득한 특정 금융상품 포트폴리오의 일부로서 이익 실현 패턴이 있습니까?"),
        "helper": None,
        "options": [
            ("trade_yes","📊 예 — 단기매매 목적",           "FVPL 필수 — FVOCI 취소불가 선택권 행사 불가"),
            ("trade_no", "📌 아니오 — 전략적·장기 보유 목적","최초 인식시점에 FVOCI 취소불가 선택권 행사 여부 검토 가능"),
        ],
    },
    "s_eq_fvoci": {
        "tag": "🟠 지분상품",
        "title": "STEP A-2 — FVOCI 취소불가 선택권(Irrevocable Option) 행사 여부",
        "ref": "§4.1.4 / §5.7.5~5.7.6",
        "desc": (
            "이 선택은 **최초 인식시점에만 가능**하며, 한 번 선택하면 취소할 수 없습니다(irrevocable).  \n"
            "개별 금융상품별로 선택합니다.\n\n"
            "**행사 시**: 공정가치 변동 → OCI, 배당(투자원가 회수 제외) → P&L  \n"
            "**주의**: 처분 시에도 OCI → P&L 재분류(Recycling) 없음. ECL(손상) 미적용."
        ),
        "helper": None,
        "options": [
            ("fvoci_yes","✅ 예 — FVOCI 지정 (취소불가, 상품별)","공정가치 변동 → OCI. 처분 시 Recycling 없음. 손상(ECL) 미적용."),
            ("fvoci_no", "📊 아니오 — FVPL 유지 (기본값)",      "모든 공정가치 변동 → 당기손익"),
        ],
    },
}


# ══════════════════════════════════════════════════════════════════════════════
# 6. Streamlit UI — AI 하이브리드 모드 통합
# ══════════════════════════════════════════════════════════════════════════════

_STEP_LABEL = {
    "s_asset":  "STEP 0 — 자산 성격",
    "s_host":   "STEP 1 — 주계약 성격",
    "s_sep":    "STEP 1-1 — 분리 3요건",
    "s_sppi1":  "STEP 2-① — 비대여변수/레버리지",
    "s_sppi2":  "STEP 2-② — TVM 변형",
    "s_sppi3":  "STEP 2-③ — 계약조건",
    "s_sppi4":  "STEP 2-④ — 트랑슈",
    "s_bm":     "STEP 3 — 사업모형",
    "s_fvo":    "STEP 4 — FVO 확인",
    "s_eq_trade": "STEP A-1 — 지분 단기매매",
    "s_eq_fvoci": "STEP A-2 — FVOCI 선택권",
}

_VAL_KO = {
    "hybrid": "복합계약", "equity": "지분상품", "deriv": "독립 파생상품", "debt": "채무상품",
    "fa_host": "금융자산 주계약", "other_host": "비금융자산·금융부채 주계약",
    "sep_ok": "3요건 충족", "sep_fail": "3요건 미충족",
    "fail_equity": "주가지수 연동", "fail_commodity": "원자재 연동",
    "fail_profit": "채무자 수익 연동", "fail_inverse": "역변동금리",
    "fail_leverage": "레버리지 내재", "fail_defer": "이자이연+복리미발생",
    "none": "비대여변수 없음 (SPPI 통과)",
    "tvm_ok": "TVM 일치", "tvm_modified_minor": "TVM 변형 미미", "tvm_fail": "TVM 변형 유의적",
    "clause_ok": "문제없는 계약조건", "clause_exception": "§B4.1.12 예외 적용", "clause_fail": "원리금 불일치",
    "tranche_no": "트랑슈 아님", "tranche_pass": "트랑슈 — 3조건 충족", "tranche_fail": "트랑슈 — 조건 불충족",
    "hold": "현금흐름 수취 (AC)", "both": "수취+매도 (FVOCI)", "trading": "공정가치/단기매매 (FVPL)", "ambiguous": "모호함",
    "fvo_yes": "FVO 지정", "fvo_no": "FVO 미지정",
    "trade_yes": "단기매매", "trade_no": "장기보유",
    "fvoci_yes": "FVOCI 지정", "fvoci_no": "FVPL 유지",
}


def _init_session():
    defaults = {
        "answers": {},
        "history": [],
        "show_result": False,
        "ai_mode": False,
        "ai_result": None,          # ai_analyze() 반환값
        "ai_overrides": {},          # {step_id: 수동 변경값}
        "ai_confirmed": False,       # 사용자가 '확인 및 승인' 버튼 눌렀는지
        "contract_text_preview": "", # 추출된 텍스트 미리보기
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


def _sidebar_upload():
    """사이드바 — AI 계약서 분석 업로드 패널"""
    st.sidebar.title("🤖 AI 계약서 자동 분석")
    st.sidebar.caption("PDF 또는 DOCX 계약서를 업로드하면\nAI가 핵심 조항을 스캔하여 STEP 0~2를 자동 제안합니다.")
    st.sidebar.divider()

    libs_ok = _PDF_OK or _DOCX_OK
    if not libs_ok:
        st.sidebar.warning(
            "라이브러리 미설치:\n"
            "```\npip install pdfplumber python-docx\n```"
        )

    uploaded = st.sidebar.file_uploader(
        "계약서 업로드 (PDF / DOCX)",
        type=["pdf", "docx"],
        help="전환사채 계약서, 사채 인수계약서, 대출약정서 등",
    )

    if uploaded:
        if st.sidebar.button("🪄 AI 자동 분석 시작", type="primary", use_container_width=True):
            with st.sidebar:
                with st.spinner("텍스트 추출 중..."):
                    text = extract_text(uploaded)
                if text.startswith("[오류]"):
                    st.error(text)
                    return
                with st.spinner("키워드 분석 중..."):
                    result = ai_analyze(text)

            # 세션 상태 저장
            st.session_state.ai_mode = True
            st.session_state.ai_result = result
            st.session_state.ai_overrides = {}
            st.session_state.ai_confirmed = False
            st.session_state.answers = {}
            st.session_state.history = []
            st.session_state.show_result = False
            st.session_state.contract_text_preview = text[:2000]
            st.rerun()

    if st.session_state.ai_mode:
        st.sidebar.divider()
        st.sidebar.success("✅ AI 분석 완료 — 메인 화면에서 결과를 확인하세요")
        if st.sidebar.button("🔄 AI 모드 초기화", use_container_width=True):
            _full_reset()


def _full_reset():
    for k in ["answers", "history", "show_result", "ai_mode", "ai_result",
              "ai_overrides", "ai_confirmed", "contract_text_preview"]:
        if k in st.session_state:
            del st.session_state[k]
    st.rerun()


def _render_ai_confirm():
    """Step B+C — AI 분석 결과 표시 및 사용자 승인 화면"""
    result: dict = st.session_state.ai_result
    overrides: dict = st.session_state.ai_overrides
    proposed: dict = result["proposed_answers"]
    evidence: list = result["evidence_items"]
    conflicts: list = result["conflict_flags"]

    st.markdown(
        '<div style="background:#EEF2FF;border:1.5px solid #6366F1;border-radius:12px;'
        'padding:1rem 1.4rem;margin-bottom:1.2rem">'
        '<span style="font-size:1.2rem;font-weight:700;color:#3730A3">🤖 AI 계약서 분석 결과</span><br>'
        '<span style="font-size:0.85rem;color:#4338CA">아래 제안된 답변을 확인하고, 필요하면 수정한 뒤 승인하세요.</span>'
        '</div>',
        unsafe_allow_html=True,
    )

    # 충돌 경고
    if conflicts:
        for cf in conflicts:
            st.warning(
                f"⚠️ **{_STEP_LABEL.get(cf['step_id'], cf['step_id'])}**: {cf['message']}",
                icon="⚠️",
            )

    # 분석 항목 카드
    st.markdown("### 📋 단계별 AI 제안 — 확인 및 수정")

    # s_bm은 항상 수동이므로 표시 제외
    show_steps = [e for e in evidence if e["step_id"] != "s_bm"]

    if not show_steps:
        st.info("분석된 키워드가 없습니다. 수동 분류를 진행해주세요.")
        if st.button("✏️ 수동 분류로 전환", use_container_width=True):
            st.session_state.ai_mode = False
            st.rerun()
        return

    for ev in show_steps:
        step_id = ev["step_id"]
        step_label = _STEP_LABEL.get(step_id, step_id)
        proposed_val = proposed.get(step_id, "")
        current_val = overrides.get(step_id, proposed_val)
        conf = ev["confidence"]
        conf_color = _CONF_COLOR.get(conf, "#F5F5F5")

        with st.container():
            st.markdown(
                f'<div style="background:{conf_color};border-radius:10px;'
                f'padding:0.8rem 1.1rem;margin-bottom:0.6rem;border:0.5px solid #DDD">'
                f'<strong>{step_label}</strong> '
                f'<span style="font-size:0.78rem;background:#FFF;padding:2px 8px;'
                f'border-radius:4px;margin-left:6px">신뢰도: {_CONF_LABEL[conf]}</span>'
                f'</div>',
                unsafe_allow_html=True,
            )
            col_info, col_edit = st.columns([2, 1])
            with col_info:
                st.markdown(f"**AI 제안**: `{_VAL_KO.get(proposed_val, proposed_val)}`")
                st.markdown(f"**근거**: {ev['basis']}")
                st.markdown(f"**기준서**: `{ev['std_ref']}`")
                kw_str = ", ".join(f"`{k}`" for k in ev["keywords_found"][:6])
                st.caption(f"감지된 키워드: {kw_str}")
            with col_edit:
                # 해당 단계 선택지 가져오기
                step_def = STEP_DEFS.get(step_id)
                if step_def:
                    opts = [(v, lbl) for v, lbl, _ in step_def["options"]]
                    opt_labels = [f"{lbl}" for v, lbl in opts]
                    opt_vals   = [v for v, lbl in opts]
                    try:
                        idx = opt_vals.index(current_val)
                    except ValueError:
                        idx = 0
                    selected = st.selectbox(
                        "✏️ 수정",
                        options=opt_labels,
                        index=idx,
                        key=f"ai_override_{step_id}",
                        label_visibility="collapsed",
                    )
                    new_val = opt_vals[opt_labels.index(selected)]
                    if new_val != overrides.get(step_id, proposed_val):
                        st.session_state.ai_overrides[step_id] = new_val

        st.divider()

    # 계약서 텍스트 미리보기
    with st.expander("📄 추출된 계약서 텍스트 미리보기 (앞 2,000자)", expanded=False):
        preview = st.session_state.contract_text_preview
        st.text_area("", value=preview, height=200, disabled=True,
                     label_visibility="collapsed")

    # 승인 버튼
    st.markdown("---")
    st.markdown(
        "### ✅ 위 내용이 맞다면, 아래 버튼으로 사업모형(STEP 3)을 직접 선택하러 이동하세요."
    )
    st.info(
        "**사업모형(STEP 3)은 내부 운용 방침을 가장 잘 아는 담당자가 직접 선택해야 합니다.**  \n"
        "AI는 계약서 조항만 분석하므로, 실제 포트폴리오 운용 목적은 자동 판단하지 않습니다.",
        icon="ℹ️",
    )

    c1, c2 = st.columns([2, 1])
    with c1:
        if st.button("🚀 확인 및 사업모형 선택으로 이동", type="primary", use_container_width=True):
            # 최종 답변 세팅: proposed + 오버라이드 반영
            final_answers = {}
            for ev in show_steps:
                sid = ev["step_id"]
                final_answers[sid] = st.session_state.ai_overrides.get(sid, proposed.get(sid, ""))

            # s_bm은 제외 (수동 선택 단계)
            st.session_state.answers = final_answers
            st.session_state.ai_confirmed = True
            st.session_state.history = list(final_answers.keys())
            st.rerun()
    with c2:
        if st.button("✏️ 수동 분류로 전환", use_container_width=True):
            st.session_state.ai_mode = False
            st.session_state.answers = {}
            st.rerun()


def _render_bm_step(ai_mode: bool = False):
    """Step D — 사업모형 수동 선택 (AI 모드 후 도달하는 단계)"""
    step = STEP_DEFS["s_bm"]
    ans = st.session_state.answers

    if ai_mode:
        st.success(
            "✅ **AI 분석 완료 — STEP 0~2가 자동으로 설정되었습니다.**  \n"
            "아래에서 **사업모형(STEP 3)**만 직접 선택하면 최종 분류 결과가 나옵니다.",
        )
        # 자동 설정된 답변 요약 표시
        with st.expander("🤖 AI가 설정한 이전 단계 요약", expanded=True):
            for k, v in ans.items():
                label = _STEP_LABEL.get(k, k)
                val_ko = _VAL_KO.get(v, v)
                st.markdown(f"- **{label}**: `{val_ko}`")
        st.divider()

    if step["tag"]:
        st.markdown(
            f'<span style="background:#ECFDF5;color:#065F46;padding:4px 12px;'
            f'border-radius:6px;font-size:0.8rem;font-weight:700">{step["tag"]}</span>',
            unsafe_allow_html=True,
        )
        st.write("")

    st.subheader(step["title"])
    st.caption(f"📌 기준서 참조: `{step['ref']}`")
    st.markdown(step["desc"])
    st.write("")

    chosen = ans.get("s_bm")
    for val, label, sub in step["options"]:
        is_sel = chosen == val
        btn_label = f"{'✔ ' if is_sel else ''}{label}\n\n_{sub}_"
        if st.button(btn_label, key=f"btn_bm_{val}",
                     type="primary" if is_sel else "secondary"):
            st.session_state.answers["s_bm"] = val
            st.rerun()

    st.divider()

    if chosen:
        # BM이 hold 또는 both이면 FVO 단계도 필요
        if chosen in ("hold", "both"):
            if st.button("다음 → FVO 확인", type="primary", use_container_width=True):
                if "s_bm" not in st.session_state.history:
                    st.session_state.history.append("s_bm")
                st.rerun()
        else:
            if st.button("최종 결과 보기", type="primary", use_container_width=True):
                if "s_bm" not in st.session_state.history:
                    st.session_state.history.append("s_bm")
                st.session_state.show_result = True
                st.rerun()


def main():
    st.set_page_config(
        page_title="IFRS 9 금융자산 분류 마법사",
        page_icon="📊",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    _init_session()

    # 전역 스타일
    st.markdown("""
    <style>
    .stButton > button {
        border-radius: 10px; border: 1.5px solid #D0D5DD;
        background: #FAFAFA; width: 100%; text-align: left;
        padding: 0.6rem 1rem; font-size: 0.92rem; line-height: 1.55;
        transition: all 0.15s; white-space: normal;
    }
    .stButton > button:hover { border-color: #1D9E75; background: #E9FBF4; }
    [data-testid="stSidebar"] { background: #F0F4FF; }
    </style>
    """, unsafe_allow_html=True)

    # ── 사이드바 ──────────────────────────────────────────────────────────────
    _sidebar_upload()

    # ── 메인 헤더 ─────────────────────────────────────────────────────────────
    st.title("📊 IFRS 9 금융자산 분류 마법사")
    st.markdown(
        "> K-IFRS 1109호 4장 · 부록B · PwC 실무 가이드라인  "
        "| **AI 하이브리드 모드** 지원  "
        "| 모든 결과에 **§ 조항 번호** 포함"
    )
    st.divider()

    ans = st.session_state.answers

    # ══════════════════════════════════════════════════════════════════════════
    # 분기 A: 결과 화면
    # ══════════════════════════════════════════════════════════════════════════
    if st.session_state.show_result:
        _render_result(ans)
        return

    # ══════════════════════════════════════════════════════════════════════════
    # 분기 B: AI 모드
    # ══════════════════════════════════════════════════════════════════════════
    if st.session_state.ai_mode:

        # B-1: AI 확인 전 — 분석 결과 리뷰 화면
        if not st.session_state.ai_confirmed:
            _render_ai_confirm()
            return

        # B-2: AI 확인 후 — s_bm에 답 없으면 사업모형 선택
        if "s_bm" not in ans:
            _render_bm_step(ai_mode=True)
            return

        # B-3: s_bm 답 있고 hold/both이면 FVO 단계
        bm = ans.get("s_bm")
        if bm in ("hold", "both") and "s_fvo" not in ans:
            _render_fvo_step()
            return

        # B-4: 모든 답 있으면 결과
        st.session_state.show_result = True
        st.rerun()
        return

    # ══════════════════════════════════════════════════════════════════════════
    # 분기 C: 수동 마법사 모드 (기존 로직)
    # ══════════════════════════════════════════════════════════════════════════
    seq = get_step_sequence(ans)
    current_step_id = seq[-1]

    if is_terminal(ans):
        st.session_state.show_result = True
        st.rerun()

    # 진행 상태 바
    progress_val = min(len(seq) / 11, 0.95)
    st.progress(progress_val, text=f"단계 {len(seq)} 진행 중")

    step = STEP_DEFS.get(current_step_id)
    if not step:
        st.error("알 수 없는 단계입니다. 처음부터 다시 시작하세요.")
        _full_reset()
        return

    if step["tag"]:
        st.markdown(
            f'<span style="background:#EEF2FF;color:#3730A3;padding:3px 10px;'
            f'border-radius:4px;font-size:0.78rem;font-weight:600">'
            f'{step["tag"]}</span>',
            unsafe_allow_html=True,
        )
        st.write("")

    st.subheader(step["title"])
    st.caption(f"📌 기준서 참조: `{step['ref']}`")
    st.markdown(step["desc"])

    if step["helper"]:
        with st.expander(step["helper"]["title"], expanded=True):
            st.markdown(step["helper"]["body"])

    st.write("")

    chosen = ans.get(current_step_id)
    for val, label, sub in step["options"]:
        is_sel = chosen == val
        btn_label = f"{'✔ ' if is_sel else ''}{label}\n\n_{sub}_"
        if st.button(btn_label, key=f"btn_{current_step_id}_{val}",
                     type="primary" if is_sel else "secondary"):
            _pick(current_step_id, val)

    st.divider()

    col_back, col_next, col_reset = st.columns([1, 1, 1])
    with col_back:
        if st.session_state.history:
            if st.button("← 이전 단계", use_container_width=True):
                _go_back()
    with col_next:
        if chosen:
            if st.button("다음 →", type="primary", use_container_width=True):
                _go_next()
        else:
            st.button("다음 →", disabled=True, use_container_width=True)
    with col_reset:
        if st.button("🔄 처음부터", use_container_width=True):
            _full_reset()

    if ans:
        with st.expander("입력 경로 확인", expanded=False):
            for k, v in ans.items():
                st.code(f"{k}  →  {v}", language=None)


def _render_fvo_step():
    """AI 모드에서 FVO 단계 렌더링"""
    step = STEP_DEFS["s_fvo"]
    ans = st.session_state.answers
    chosen = ans.get("s_fvo")

    st.markdown(
        '<span style="background:#FEF9C3;color:#713F12;padding:3px 10px;'
        'border-radius:4px;font-size:0.78rem;font-weight:600">🟡 FVO 최종 확인</span>',
        unsafe_allow_html=True,
    )
    st.write("")
    st.subheader(step["title"])
    st.caption(f"📌 기준서 참조: `{step['ref']}`")
    st.markdown(step["desc"])
    st.write("")

    for val, label, sub in step["options"]:
        is_sel = chosen == val
        if st.button(f"{'✔ ' if is_sel else ''}{label}\n\n_{sub}_",
                     key=f"btn_fvo_{val}",
                     type="primary" if is_sel else "secondary"):
            st.session_state.answers["s_fvo"] = val
            if "s_fvo" not in st.session_state.history:
                st.session_state.history.append("s_fvo")
            st.rerun()

    st.divider()
    if chosen:
        if st.button("최종 결과 보기", type="primary", use_container_width=True):
            st.session_state.show_result = True
            st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# 7. 결과 화면
# ══════════════════════════════════════════════════════════════════════════════

def _render_result(ans: dict):
    r = compute_result(ans)

    color_map = {
        "green":  ("#E1F5EE", "#085041", "#0F6E56", "✅"),
        "blue":   ("#E6F1FB", "#0C447C", "#185FA5", "🔵"),
        "orange": ("#FAEEDA", "#633806", "#854F0B", "🟡"),
        "red":    ("#FCEBEB", "#791F1F", "#A32D2D", "🔴"),
    }
    bg, fg, border, icon = color_map.get(r["color"], ("#F5F5F5", "#333", "#999", "📋"))

    st.progress(1.0, text="✅ 분류 완료!")

    # AI 모드 배지
    if st.session_state.get("ai_mode") and st.session_state.get("ai_confirmed"):
        st.info("🤖 이 결과는 **AI 자동 분석(STEP 0~2) + 사용자 직접 선택(STEP 3)**의 하이브리드 방식으로 도출되었습니다.", icon="🤖")

    # 결과 배너
    st.markdown(
        f'<div style="background:{bg};border:2px solid {border};border-radius:14px;'
        f'padding:1.4rem 1.8rem;margin-bottom:1.2rem">'
        f'<div style="font-size:1.6rem;font-weight:700;color:{fg};margin-bottom:.4rem">'
        f'{icon} {r["label"]}</div>'
        f'<div style="font-size:0.93rem;color:{fg};line-height:1.7">{r["reason"]}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )

    # 기준서 조항
    st.markdown("### 📚 적용 기준서 조항")
    ref_cols = st.columns(min(len(r["refs"]), 5))
    for i, ref in enumerate(r["refs"]):
        ref_cols[i % 5].code(ref, language=None)

    st.divider()

    # 회계처리 요약표
    st.markdown("### 📋 회계처리 요약표")
    _render_accounting_table(r)

    st.divider()

    # ECL · Recycling
    st.markdown("### ⚙️ 추가 처리 사항")
    if r["ecl"]:
        st.success(
            "**ECL(기대신용손실) 손상 모형 적용 대상입니다.**  \n"
            "매 보고기간 말에 기대신용손실(ECL)을 산정하고 손실충당금을 인식해야 합니다. [§5.5]"
        )
    else:
        st.info("**ECL(손상) 적용 없음** — 이 분류에는 손상 인식 규정이 적용되지 않습니다.")

    if r["recycling"]:
        st.warning(
            "**채무상품 FVOCI**: 처분 시 OCI에 누적된 손익이 당기손익(P&L)으로 재분류됩니다. [§5.7.2]  \n"
            "지분상품 FVOCI(Recycling 금지)와의 핵심 차이입니다.",
            icon="⚠️",
        )
    elif r.get("recycling_note"):
        st.warning(r["recycling_note"], icon="⚠️")
    else:
        st.info("**Recycling 없음** — OCI 잔액은 처분 후에도 당기손익으로 이전되지 않습니다.")

    if r["warning"]:
        st.warning(r["warning"], icon="⚠️")

    st.divider()

    # SPPI 사례 JSON
    case_key = r.get("case_key")
    if case_key and case_key in SPPI_CASES_DICT:
        case = SPPI_CASES_DICT[case_key]
        st.markdown("### 🗂️ 유사 사례 참고 (SPPI_CASES_DICT)")
        c1, c2 = st.columns(2)
        with c1:
            st.markdown(f"**상품**: {case['label']}")
            st.markdown(f"**유형**: `{case['category']}`")
            st.markdown(f"**기준서**: {', '.join(case['standard_ref'])}")
        with c2:
            st.markdown(f"**불충족 이유**: {case['reason']}")
            st.markdown(f"**판단 기준**: {case['judgment_criteria']}")
        with st.expander("📄 JSON 원본 보기", expanded=False):
            st.json(case)
        st.divider()

    # 입력 경로
    st.markdown("### 🗺️ 입력 경로 요약")
    path_cols = st.columns(3)
    for i, (k, v) in enumerate(ans.items()):
        path_cols[i % 3].code(f"{_STEP_LABEL.get(k,k)}: {_VAL_KO.get(v,v)}", language=None)

    # 버튼
    st.write("")
    c1, c2, c3 = st.columns(3)
    with c1:
        if st.button("← 이전 단계로", use_container_width=True):
            st.session_state.show_result = False
            seq = get_step_sequence(ans) if not st.session_state.get("ai_confirmed") else ["s_fvo"]
            if seq:
                ans.pop(seq[-1], None)
            if st.session_state.get("ai_confirmed"):
                ans.pop("s_fvo", None)
                ans.pop("s_bm", None)
            st.rerun()
    with c2:
        if st.button("🔄 처음부터 다시", type="primary", use_container_width=True):
            _full_reset()
    with c3:
        if st.button("📋 텍스트 리포트", use_container_width=True):
            _show_text_report(r, ans)


def _render_accounting_table(r: dict):
    cls = r["classification"]
    is_equity_fvoci = cls == "FVOCI" and "지분" in r["label"]

    if cls == "AC":
        rows = [
            ("최초 인식", "공정가치 + 거래원가"),
            ("후속 측정", "유효이자율법 상각후원가"),
            ("이자수익", "당기손익 (P&L) — 유효이자율법"),
            ("평가손익", "해당 없음 (공정가치 변동 미반영)"),
            ("ECL 손상", "✅ 적용 — 12개월/전체기간 ECL [§5.5]"),
            ("처분 손익", "당기손익 (P&L)"),
            ("OCI Recycling", "해당 없음"),
        ]
    elif cls == "FVOCI" and not is_equity_fvoci:
        rows = [
            ("최초 인식", "공정가치"),
            ("후속 측정", "공정가치"),
            ("이자수익", "당기손익 (P&L) — 유효이자율법"),
            ("평가손익", "기타포괄손익 (OCI)"),
            ("ECL 손상", "✅ 적용 — P&L 반영 [§5.5]"),
            ("처분 시 OCI 재분류", "✅ P&L로 Recycling 발생 [§5.7.2]"),
            ("OCI Recycling", "✅ 처분 시 발생 (채무상품 FVOCI)"),
        ]
    elif cls == "FVOCI" and is_equity_fvoci:
        rows = [
            ("최초 인식", "공정가치"),
            ("후속 측정", "공정가치"),
            ("배당", "당기손익 (P&L) [§B5.7.1]"),
            ("평가손익", "기타포괄손익 (OCI)"),
            ("ECL 손상", "❌ 미적용"),
            ("처분 시 OCI 재분류", "❌ P&L 재분류 금지 — 자본 내 이전만 [§5.7.5]"),
            ("OCI Recycling", "❌ 금지 (지분상품 FVOCI)"),
        ]
    else:
        rows = [
            ("최초 인식", "공정가치"),
            ("후속 측정", "공정가치"),
            ("이자/배당", "당기손익 (P&L)"),
            ("평가손익", "당기손익 (P&L) — 전액"),
            ("ECL 손상", "❌ 미적용"),
            ("처분 손익", "당기손익 (P&L)"),
            ("OCI Recycling", "해당 없음"),
        ]

    lines = ["| 항목 | 내용 |", "|---|---|"]
    for item, content in rows:
        lines.append(f"| {item} | {content} |")
    st.markdown("\n".join(lines))


# ══════════════════════════════════════════════════════════════════════════════
# 8. 헬퍼 함수
# ══════════════════════════════════════════════════════════════════════════════

def _pick(step_id: str, val: str):
    st.session_state.answers[step_id] = val
    st.rerun()


def _go_next():
    ans = st.session_state.answers
    seq = get_step_sequence(ans)
    if ans.get(seq[-1]):
        st.session_state.history.append(seq[-1])
        if is_terminal(ans):
            st.session_state.show_result = True
        st.rerun()


def _go_back():
    if not st.session_state.history:
        return
    prev_id = st.session_state.history.pop()
    seq = get_step_sequence(st.session_state.answers)
    if prev_id in seq:
        for sid in seq[seq.index(prev_id):]:
            st.session_state.answers.pop(sid, None)
    st.session_state.show_result = False
    st.rerun()


def _show_text_report(r: dict, ans: dict):
    lines = [
        "=" * 65,
        "  IFRS 9 금융자산 분류 결과 리포트",
        "=" * 65,
        f"  분류: {r['label']}",
        "",
        "[ 분류 근거 ]",
        f"  {r['reason']}",
        "",
        "[ 적용 기준서 조항 ]",
        "  " + "  |  ".join(r["refs"]),
        "",
        "[ 후속 측정 원칙 ]",
    ]
    for item in r["accounting"]:
        lines.append(f"  ✦ {item}")
    lines += [
        "",
        f"[ ECL 손상 적용 ]   {'✅ 적용 (§5.5)' if r['ecl'] else '❌ 미적용'}",
        f"[ Recycling 발생 ]  {'✅ 처분 시 발생 (채무 FVOCI)' if r['recycling'] else '❌ 없음'}",
    ]
    if r.get("recycling_note"):
        lines.append(f"  ※ {r['recycling_note']}")
    if r["warning"]:
        lines += ["", "[ 주의사항 ]", f"  ⚠️  {r['warning']}"]
    lines += ["", "[ 입력 경로 ]"]
    for k, v in ans.items():
        lines.append(f"  {_STEP_LABEL.get(k,k)}: {_VAL_KO.get(v,v)}")
    if st.session_state.get("ai_mode") and st.session_state.get("ai_confirmed"):
        lines += ["", "[ 분류 방식 ]", "  🤖 AI 하이브리드 (STEP 0~2 자동 + STEP 3 수동)"]
    lines += ["", "=" * 65]
    st.code("\n".join(lines), language=None)


# ══════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    main()
