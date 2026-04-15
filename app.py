"""
IFRS 9 (K-IFRS 1109) 금융자산 분류 마법사
─────────────────────────────────────────
실행 방법:
    pip install streamlit
    streamlit run app.py

설계 기준:
    · 기업회계기준서 KIFRS 1109호 4장, 부록B
    · PwC IFRS 9 금융상품의 분류 및 측정 실무 가이드라인
    · FVTPL → FVPL 용어 통일
    · 모든 결과에 § 조항 번호 포함
    · SPPI_CASES_DICT JSON 12개 내장 (추후 DB 확장 가능)
"""

import streamlit as st
import json

# ──────────────────────────────────────────────────────────────────────────────
# 0. SPPI 불충족 사례 딕셔너리 (JSON 구조 — 추후 DB 교체 가능)
# ──────────────────────────────────────────────────────────────────────────────
SPPI_CASES_DICT: dict = {
    "case_F": {
        "id": "case_F",
        "label": "상품F — 전환사채",
        "category": "지분연동",
        "instrument_desc": "확정수량의 발행자 지분상품으로 전환가능한 채권",
        "sppi_fail": True,
        "reason": "계약상 현금흐름이 기본대여계약과 일관되지 않는 수익 반영 — 발행자 지분가치에 연계됨",
        "standard_ref": ["§B4.1.14", "§B4.1.7A"],
        "judgment_criteria": "금융자산 주계약 시 내재파생 분리불가(§4.3.2). 전체 SPPI 테스트. 지분가치 연동=§B4.1.7A 위반",
    },
    "case_G": {
        "id": "case_G",
        "label": "상품G — 역변동금리",
        "category": "TVM역방향",
        "instrument_desc": "역변동금리(시장이자율과 반비례) 대여금",
        "sppi_fail": True,
        "reason": "이자금액이 원금잔액의 화폐 시간가치 대가가 아님. 금리상승 시 이자 감소",
        "standard_ref": ["§B4.1.14", "§4.1.3⑵"],
        "judgment_criteria": "이자율 방향 확인. 역방향이면 TVM 대가 결여 → FVPL",
    },
    "case_H": {
        "id": "case_H",
        "label": "상품H — 이자이연+복리미발생",
        "category": "이자이연",
        "instrument_desc": "영구금융상품 — 지급여력 부족 시 이자이연 가능, 이연이자에 복리 미발생",
        "sppi_fail": True,
        "reason": "이자이연 가능 + 이연이자 복리 미발생 → 이자가 TVM의 진정한 대가가 아님",
        "standard_ref": ["§B4.1.14", "§4.1.3⑵"],
        "judgment_criteria": "이연이자에 복리가 붙으면 SPPI 가능. 영구적 특성 자체는 불충족 이유 아님",
    },
    "case_I": {
        "id": "case_I",
        "label": "상품I — 탄소가격지수(시장추적)",
        "category": "비대여변수연동",
        "instrument_desc": "매 보고기간 시장 탄소가격지수 변동 추적하여 이자율 조정 대여금",
        "sppi_fail": True,
        "reason": "기본대여위험·원가가 아닌 탄소가격지수(비대여 변수)에 따라 현금흐름 변동",
        "standard_ref": ["§B4.1.14 상품I", "§B4.1.8A"],
        "judgment_criteria": "cf. 상품EA(탄소배출 목표달성 고정bp 조정): 유의적 차이 없으면 SPPI 가능(§B4.1.10A)",
    },
    "case_road": {
        "id": "case_road",
        "label": "유료도로 통행량 연동",
        "category": "기초자산성과연동",
        "instrument_desc": "차량 통행수가 많을수록 현금흐름이 증가하는 금융자산",
        "sppi_fail": True,
        "reason": "계약상 현금흐름이 비금융자산(유료도로) 사용량 성과에 연동 — 기본대여계약 불일치",
        "standard_ref": ["§B4.1.16", "§B4.1.7A"],
        "judgment_criteria": "비소구 특성 자체는 불충족 아님. look-through 결과 기초자산 성과 연동 여부 판단",
    },
    "case_equity_idx": {
        "id": "case_equity_idx",
        "label": "주가지수 연동 이자·원금",
        "category": "지분연동",
        "instrument_desc": "이자·원금이 주가·주가지수 변동에 연동되는 채무상품",
        "sppi_fail": True,
        "reason": "기본대여계약 무관 위험(주식시장 위험)에 노출. 레버리지 동반 가능",
        "standard_ref": ["§B4.1.7A", "§B4.1.9"],
        "judgment_criteria": "지분위험 익스포저 = §B4.1.7A 핵심원칙 위반",
    },
    "case_profit": {
        "id": "case_profit",
        "label": "이익참가사채",
        "category": "채무자성과연동",
        "instrument_desc": "이자가 채무자의 순이익·수익의 일정 비율로 결정되는 채무상품",
        "sppi_fail": True,
        "reason": "채무자 사업성과에 연동된 수익 반영 → 기본대여계약 불일치",
        "standard_ref": ["§B4.1.7A", "§B4.1.8A"],
        "judgment_criteria": "순전히 신용위험 변동 보상인 구조라면 예외적 SPPI 가능",
    },
    "case_leverage": {
        "id": "case_leverage",
        "label": "레버리지 내재 상품",
        "category": "레버리지",
        "instrument_desc": "독립 옵션, 선도계약, 스왑 등 레버리지 내재 금융자산",
        "sppi_fail": True,
        "reason": "레버리지는 현금흐름 변동성을 이자의 경제적 특성을 초과하여 높임 → 이자 성격 상실",
        "standard_ref": ["§B4.1.9"],
        "judgment_criteria": "캡·플로어는 레버리지 없으면 SPPI 가능(§B4.1.11). 독립 옵션·선도·스왑은 항상 레버리지",
    },
    "case_tvm": {
        "id": "case_tvm",
        "label": "TVM 변형 — 이자율 기간 불일치",
        "category": "TVM변형",
        "instrument_desc": "이자기산기간 불일치: 1년이자율로 매월 재설정 / 5년만기에 5년이자율로 6개월 재설정",
        "sppi_fail": True,
        "reason": "TVM 요소 변형. 벤치마크 현금흐름과 합리적 시나리오에서 유의적 차이 가능",
        "standard_ref": ["§B4.1.9B", "§B4.1.9C", "§B4.1.9D"],
        "judgment_criteria": "규제이자율 TVM 대용 예외(§B4.1.9E). 미미한 영향이면 무시(§B4.1.18)",
    },
    "case_nonrecourse": {
        "id": "case_nonrecourse",
        "label": "지분담보 비소구 대여금",
        "category": "기초자산성과연동",
        "instrument_desc": "지분포트폴리오 담보 비소구 대여금 — 지분가격 하락 시 은행 손실",
        "sppi_fail": True,
        "reason": "채권자가 지분가격 하락 위험(풋옵션 동일 경제효과) 부담. 현금흐름이 지분성과에 연동",
        "standard_ref": ["§B4.1.16A", "§B4.1.17"],
        "judgment_criteria": "비소구 자체는 FVPL 이유 아님. look-through 결과 지분위험 노출 → SPPI 불충족",
    },
    "case_embedded_fa": {
        "id": "case_embedded_fa",
        "label": "금융자산 주계약 내재파생",
        "category": "내재파생(FA주계약)",
        "instrument_desc": "채무상품 주계약에 내재된 지분연계 이자·원금 지급계약",
        "sppi_fail": True,
        "reason": "금융자산 주계약 → §4.3.2 분리 금지. 복합계약 전체 SPPI 테스트 시 지분연계로 불충족",
        "standard_ref": ["§4.3.2", "§B4.3.5⑶"],
        "judgment_criteria": "금융부채 주계약과의 핵심 차이: 금융자산 주계약에는 내재파생 분리 금지",
    },
    "case_A_ok": {
        "id": "case_A_ok",
        "label": "상품A — 인플레이션 연계 (SPPI 충족 참고)",
        "category": "참고:SPPI충족",
        "instrument_desc": "발행통화 인플레이션지수 연계, 비레버리지, 원금 보장 채권",
        "sppi_fail": False,
        "reason": "SPPI 충족: 인플레이션 연계는 TVM을 현행 수준으로 재설정 — TVM 대가에 해당",
        "standard_ref": ["§B4.1.13 상품A", "§B4.1.7A"],
        "judgment_criteria": "채무자 성과·주가지수 추가 연계 시 불충족. 비레버리지 조건 필수 확인",
    },
}


# ──────────────────────────────────────────────────────────────────────────────
# 1. 분류 결과 계산 로직
# ──────────────────────────────────────────────────────────────────────────────

def sppi_fail_result(fail_key: str, case_key: str | None) -> dict:
    """SPPI 불충족 공통 결과 생성"""
    msgs = {
        "fail_equity":    "주가·주가지수 연동 이자·원금. 기본대여계약과 일관되지 않는 위험(주식시장 위험)에 노출됩니다.",
        "fail_commodity": "원자재·탄소가격지수(시장추적) 연동. 기본대여위험·원가가 아닌 변수에 따라 현금흐름이 변동합니다.",
        "fail_profit":    "채무자 순이익·수익 비율 연동. 채무자의 사업성과에 연동된 수익이 반영됩니다.",
        "fail_inverse":   "역변동금리 — 이자금액이 화폐의 시간가치 대가가 아닙니다. 금리상승 시 이자가 감소합니다.",
        "fail_leverage":  "레버리지 내재 — 현금흐름 변동성이 이자의 경제적 특성을 초과합니다.",
        "fail_defer":     "이자이연 가능 + 이연이자 복리 미발생 — 이자가 TVM의 진정한 대가가 아닙니다. 단, 이연이자에 복리가 붙으면 SPPI 가능.",
        "tvm_fail":       "TVM 요소 변형이 유의적. 벤치마크 현금흐름과 합리적 시나리오에서 유의적 차이가 발생합니다.",
        "clause_fail":    "계약조건으로 인해 원리금 지급과 일치하지 않는 현금흐름이 발생합니다(§B4.1.12 예외 미해당).",
        "tranche_fail":   "계약상 연계 트랑슈 구조에서 Look-through 조건을 충족하지 못하거나 최초 인식시점에 평가가 불가합니다.",
    }
    refs = {
        "fail_equity":    ["§B4.1.7A", "§B4.1.14", "§4.1.4"],
        "fail_commodity": ["§B4.1.8A", "§B4.1.14 상품I", "§4.1.4"],
        "fail_profit":    ["§B4.1.7A", "§B4.1.8A", "§4.1.4"],
        "fail_inverse":   ["§B4.1.14", "§4.1.3⑵", "§4.1.4"],
        "fail_leverage":  ["§B4.1.9", "§4.1.4"],
        "fail_defer":     ["§B4.1.14", "§4.1.3⑵", "§4.1.4"],
        "tvm_fail":       ["§B4.1.9C", "§B4.1.9D", "§4.1.4"],
        "clause_fail":    ["§B4.1.10", "§B4.1.16", "§4.1.4"],
        "tranche_fail":   ["§B4.1.26", "§B4.1.21", "§4.1.4"],
    }
    return {
        "classification": "FVPL",
        "label": "당기손익-공정가치 (FVPL) — SPPI 불충족",
        "color": "red",
        "reason": "SPPI 테스트 불충족. " + msgs.get(fail_key, ""),
        "refs": refs.get(fail_key, ["§4.1.4"]),
        "ecl": False,
        "recycling": False,
        "recycling_note": None,
        "accounting": [
            "공정가치로 최초 인식 및 후속 측정",
            "모든 공정가치 변동 → 당기손익",
            "ECL(손상) 적용 없음",
        ],
        "warning": None,
        "case_key": case_key,
    }


def compute_result(ans: dict) -> dict:
    """세션 상태의 답변을 바탕으로 분류 결과 딕셔너리 반환"""
    at = ans.get("s_asset")

    # ── 독립 파생상품 ──────────────────────────────────────────────────────────
    if at == "deriv":
        return {
            "classification": "FVPL",
            "label": "당기손익-공정가치 (FVPL)",
            "color": "red",
            "reason": "독립 파생상품은 항상 FVPL로 측정합니다. 레버리지가 내재되어 있어 SPPI 불충족이며, AC·FVOCI 분류가 불가합니다.",
            "refs": ["§4.1.4", "§B4.1.9"],
            "ecl": False,
            "recycling": False,
            "recycling_note": None,
            "accounting": [
                "공정가치로 최초 인식 및 후속 측정",
                "모든 공정가치 변동 → 당기손익",
                "ECL(손상) 적용 없음",
            ],
            "warning": None,
            "case_key": None,
        }

    # ── 복합계약 ───────────────────────────────────────────────────────────────
    if at == "hybrid":
        host = ans.get("s_host")
        if host == "other_host":
            sep = ans.get("s_sep")
            if sep == "sep_ok":
                return {
                    "classification": "FVPL",
                    "label": "내재파생상품 FVPL 분리 + 주계약 별도 처리",
                    "color": "red",
                    "reason": "분리 3요건 충족. 내재파생상품은 FVPL로 측정하고, 주계약은 관련 기준서에 따라 별도 회계처리합니다.",
                    "refs": ["§4.3.3", "§4.3.4", "§B4.3.5"],
                    "ecl": False,
                    "recycling": False,
                    "recycling_note": None,
                    "accounting": [
                        "내재파생상품 → FVPL (공정가치 측정)",
                        "주계약 → 관련 기준서 별도 처리",
                        "재평가 금지(계약 유의적 변경 시 제외) [§B4.3.11]",
                    ],
                    "warning": "밀접관련 내재파생(§B4.3.8)은 분리하지 않습니다: 레버리지 없는 금리캡·플로어, 인플레이션 리스료, 단위연계특성 등",
                    "case_key": "case_embedded_fa",
                }
            else:  # sep_fail
                return {
                    "classification": "FVPL",
                    "label": "복합계약 전체 → FVPL",
                    "color": "red",
                    "reason": "분리 3요건 미충족 또는 내재파생상품을 신뢰성 있게 측정할 수 없습니다. 복합계약 전체를 FVPL로 측정합니다.",
                    "refs": ["§4.3.6", "§4.3.7"],
                    "ecl": False,
                    "recycling": False,
                    "recycling_note": None,
                    "accounting": [
                        "복합계약 전체 → FVPL 측정",
                        "공정가치 변동 전액 → 당기손익",
                    ],
                    "warning": None,
                    "case_key": "case_embedded_fa",
                }
        # fa_host → 채무상품 경로(SPPI)로 계속

    # ── 지분상품 ───────────────────────────────────────────────────────────────
    if at == "equity":
        trade = ans.get("s_eq_trade")
        if trade == "trade_yes":
            return {
                "classification": "FVPL",
                "label": "당기손익-공정가치 (FVPL) — 단기매매 지분",
                "color": "red",
                "reason": "단기매매 목적 지분상품은 FVPL로 측정합니다. FVOCI 취소불가 선택권을 행사할 수 없습니다.",
                "refs": ["§4.1.4"],
                "ecl": False,
                "recycling": False,
                "recycling_note": None,
                "accounting": [
                    "공정가치로 측정",
                    "모든 공정가치 변동 → 당기손익",
                    "배당 → 당기손익",
                    "ECL(손상) 적용 없음",
                ],
                "warning": None,
                "case_key": None,
            }
        fvoci_election = ans.get("s_eq_fvoci")
        if fvoci_election == "fvoci_yes":
            return {
                "classification": "FVOCI",
                "label": "기타포괄손익-공정가치 (FVOCI) — 지분 취소불가 지정",
                "color": "blue",
                "reason": "단기매매가 아닌 지분상품에 대해 최초 인식시점에 FVOCI 취소불가 선택권을 행사하였습니다.",
                "refs": ["§4.1.4", "§5.7.5", "§5.7.6", "§B5.7.1"],
                "ecl": False,
                "recycling": False,
                "recycling_note": "지분상품 FVOCI: 처분 시에도 OCI 누적손익이 P&L로 재분류(Recycling)되지 않습니다. 자본 내 이전만 허용됩니다.",
                "accounting": [
                    "공정가치 변동 전액 → OCI",
                    "배당(투자원가 회수 성격 제외) → 당기손익 [§B5.7.1]",
                    "처분 시 OCI 누적손익 → P&L 재분류 금지 (Recycling 없음) [§5.7.5]",
                    "ECL(손상) 규정 미적용",
                ],
                "warning": "처분 시 OCI → P&L 재분류 없음(Recycling 금지). 손상(ECL) 인식하지 않음. 자본 내 이전만 허용.",
                "case_key": None,
            }
        # fvoci_no
        return {
            "classification": "FVPL",
            "label": "당기손익-공정가치 (FVPL) — 지분 기본값",
            "color": "orange",
            "reason": "FVOCI 선택권을 행사하지 않은 비단기매매 지분상품은 FVPL로 측정합니다.",
            "refs": ["§4.1.4"],
            "ecl": False,
            "recycling": False,
            "recycling_note": None,
            "accounting": [
                "공정가치로 측정",
                "모든 공정가치 변동 → 당기손익",
                "배당 → 당기손익",
            ],
            "warning": None,
            "case_key": None,
        }

    # ── 채무상품 / 복합계약(FA 주계약) — SPPI 테스트 ─────────────────────────
    case_map = {
        "fail_equity":    "case_equity_idx",
        "fail_commodity": "case_I",
        "fail_profit":    "case_profit",
        "fail_inverse":   "case_G",
        "fail_leverage":  "case_leverage",
        "fail_defer":     "case_H",
    }
    sp1 = ans.get("s_sppi1")
    if sp1 and sp1 != "none":
        return sppi_fail_result(sp1, case_map.get(sp1))

    if ans.get("s_sppi2") == "tvm_fail":
        return sppi_fail_result("tvm_fail", "case_tvm")

    if ans.get("s_sppi3") == "clause_fail":
        return sppi_fail_result("clause_fail", "case_road")

    if ans.get("s_sppi4") == "tranche_fail":
        return sppi_fail_result("tranche_fail", None)

    # ── 사업모형 테스트 ────────────────────────────────────────────────────────
    bm = ans.get("s_bm")
    if bm == "ambiguous":
        return {
            "classification": "FVPL",
            "label": "추가 검토 필요 → 잠정 FVPL",
            "color": "orange",
            "reason": (
                "입력된 정보만으로는 사업모형을 명확히 판단하기 어렵습니다. "
                "내부보고체계, 과거 매도 이력, 관리자 보상 방식 등 추가 증거를 검토하십시오. "
                "기준서·가이드라인 상충 시 보수적 접근으로 잠정 FVPL 분류합니다."
            ),
            "refs": ["§B4.1.2B", "§B4.1.5"],
            "ecl": False,
            "recycling": False,
            "recycling_note": None,
            "accounting": [
                "잠정 FVPL로 처리 후 추가 검토",
                "사업모형 증거 문서화 필요",
            ],
            "warning": "확정 분류 전 반드시 주요경영진 결정 근거(내부보고, 보상체계, 매도이력)를 문서화하십시오.",
            "case_key": None,
        }
    if bm == "trading":
        return {
            "classification": "FVPL",
            "label": "당기손익-공정가치 (FVPL) — 잔여범주",
            "color": "red",
            "reason": "공정가치 기준 관리·평가 또는 단기매매 포트폴리오 → FVPL 잔여범주.",
            "refs": ["§B4.1.5", "§B4.1.6", "§4.1.4"],
            "ecl": False,
            "recycling": False,
            "recycling_note": None,
            "accounting": [
                "공정가치로 측정",
                "모든 공정가치 변동 → 당기손익",
                "ECL(손상) 적용 없음",
            ],
            "warning": None,
            "case_key": None,
        }

    # ── FVO 최종 확인 ─────────────────────────────────────────────────────────
    fvo = ans.get("s_fvo")
    if fvo == "fvo_yes":
        return {
            "classification": "FVPL",
            "label": "당기손익-공정가치 (FVPL) — FVO 지정",
            "color": "orange",
            "reason": "회계불일치 해소를 위한 공정가치 지정선택권(FVO) 행사. 최초 인식시점에 취소불가로 지정합니다.",
            "refs": ["§4.1.5", "§B4.1.29~32"],
            "ecl": False,
            "recycling": False,
            "recycling_note": None,
            "accounting": [
                "공정가치로 측정",
                "모든 공정가치 변동 → 당기손익",
                "최초 인식시점 지정·취소불가",
                "ECL(손상) 적용 없음",
            ],
            "warning": "FVO 지정은 취소불가입니다. 최초 인식시점에 회계불일치 해소 요건을 면밀히 검토하십시오.",
            "case_key": None,
        }

    # ── AC ────────────────────────────────────────────────────────────────────
    if bm == "hold":
        return {
            "classification": "AC",
            "label": "상각후원가 (AC)",
            "color": "green",
            "reason": "SPPI 충족 + 계약상 현금흐름 수취 목적 사업모형 → AC 측정.",
            "refs": ["§4.1.2", "§4.1.2⑴", "§B4.1.2C", "§B4.1.3A"],
            "ecl": True,
            "recycling": False,
            "recycling_note": None,
            "accounting": [
                "최초 인식: 공정가치 (거래원가 포함)",
                "후속 측정: 유효이자율법 적용 상각후원가",
                "이자수익 → 당기손익 (유효이자율법)",
                "ECL(기대신용손실) 손상 모형 적용 [§5.5]",
                "처분 시 장부금액과 수취대가 차이 → 당기손익",
            ],
            "warning": None,
            "case_key": None,
        }

    # ── FVOCI (채무상품) ──────────────────────────────────────────────────────
    if bm == "both":
        return {
            "classification": "FVOCI",
            "label": "기타포괄손익-공정가치 (FVOCI) — 채무상품",
            "color": "blue",
            "reason": "SPPI 충족 + 수취와 매도 둘 다가 목적인 사업모형 → FVOCI 측정.",
            "refs": ["§4.1.2A", "§4.1.2A⑴", "§B4.1.4A", "§B4.1.4C"],
            "ecl": True,
            "recycling": True,
            "recycling_note": None,
            "accounting": [
                "최초 인식: 공정가치",
                "후속 측정: 공정가치",
                "이자수익·ECL(손상)·외환손익 → 당기손익",
                "그 외 공정가치 변동 → OCI",
                "처분 시 OCI 누적손익 → P&L 재분류 (Recycling 발생) [§5.7.2]",
            ],
            "warning": "채무상품 FVOCI는 처분 시 OCI에 누적된 손익이 당기손익(P&L)으로 재분류(Recycling)됩니다. 지분상품 FVOCI와의 핵심 차이입니다.",
            "case_key": None,
        }

    # fallback
    return {
        "classification": "FVPL",
        "label": "당기손익-공정가치 (FVPL)",
        "color": "red",
        "reason": "분류 기준 미충족 — 잔여범주 FVPL 적용.",
        "refs": ["§4.1.4"],
        "ecl": False,
        "recycling": False,
        "recycling_note": None,
        "accounting": ["공정가치로 측정", "모든 공정가치 변동 → 당기손익"],
        "warning": None,
        "case_key": None,
    }


# ──────────────────────────────────────────────────────────────────────────────
# 2. 스텝 시퀀스 계산 (답변 상태에 따라 동적으로 결정)
# ──────────────────────────────────────────────────────────────────────────────

def get_step_sequence(ans: dict) -> list[str]:
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
            return base + _debt_sppi_sequence(ans)
        # other_host
        return base + ["s_sep"]
    # debt (또는 fa_host 이후)
    return ["s_asset"] + _debt_sppi_sequence(ans)


def _debt_sppi_sequence(ans: dict) -> list[str]:
    seq = ["s_sppi1"]
    sp1 = ans.get("s_sppi1")
    if not sp1 or sp1 != "none":
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
    """현재 답변이 최종 결과를 낼 수 있는 상태인지 확인"""
    seq = get_step_sequence(ans)
    last = seq[-1]
    return last in ans


# ──────────────────────────────────────────────────────────────────────────────
# 3. 각 스텝 정의
# ──────────────────────────────────────────────────────────────────────────────

STEP_DEFS: dict = {
    "s_asset": {
        "tag": "",
        "title": "STEP 0 — 금융자산의 기본 성격",
        "ref": "§4.1.1",
        "desc": "IFRS 9 분류는 자산 성격 판별에서 시작합니다. 가장 적합한 항목을 선택하세요.",
        "helper": None,
        "options": [
            ("debt",   "📄 채무상품",          "대여금·사채·채권 등 원금+이자 구조"),
            ("equity", "📈 지분상품",           "보통주·우선주·기타 지분투자 (IAS 32 자본 정의 충족)"),
            ("deriv",  "🔄 독립 파생상품",      "옵션·선도·스왑 등 — 주계약 없는 단독 파생"),
            ("hybrid", "⚠️ 복합계약 (주계약+내재파생)", "전환사채 등 — 내재파생상품 포함 복합금융상품"),
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
            ("fa_host",    "📄 주계약이 금융자산 (채무상품)",              "→ 내재파생 분리 금지(§4.3.2). 복합계약 전체를 채무상품으로 보고 SPPI 테스트 진행"),
            ("other_host", "🏢 주계약이 금융부채 또는 비금융자산",          "→ 분리 3요건 검토(§4.3.3) 필요"),
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
            ("sep_ok",   "✅ 3요건 모두 충족 → 내재파생 분리 가능",   "내재파생 → FVPL / 주계약 → 관련 기준서 별도 처리"),
            ("sep_fail", "❌ 3요건 미충족 또는 분리·측정 불가",        "복합계약 전체를 FVPL로 측정(§4.3.6)"),
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
            ("fail_equity",    "❌ 주가·주가지수 연동 이자·원금",                    "전환사채, 주가지수연동 이자 등 — 상품F·case_equity_idx 유형"),
            ("fail_commodity", "❌ 원자재·탄소가격지수(시장추적형) 연동",             "금·원유·탄소가격지수 변동 추적 이자 — 상품I 유형"),
            ("fail_profit",    "❌ 채무자 순이익·수익 비율 연동",                    "이익참가사채 등 (신용위험 보상 목적 제외)"),
            ("fail_inverse",   "❌ 역변동금리 — 시장이자율과 반비례",                "금리상승 시 이자 감소 구조 — 상품G 유형"),
            ("fail_leverage",  "❌ 레버리지 포함 — 독립 옵션·선도·스왑 수준",        "현금흐름 변동성이 이자의 경제적 특성 초과"),
            ("fail_defer",     "❌ 이자이연 가능 + 이연이자 복리 미발생",             "이연된 이자에 추가 이자가 발생하지 않음 — 상품H 유형"),
            ("none",           "✅ 위 항목 해당 없음 — 다음 단계 계속",              "기본대여계약과 일관. SPPI 테스트 계속"),
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
            ("tvm_ok",             "✅ 이자기산기간과 이자율 기간 일치 (또는 영향 미미)",          "벤치마크 현금흐름과 유의적 차이 없음"),
            ("tvm_modified_minor", "⚠️ 변형되나 유의적 차이 없음 (질적·양적 평가 확인 필요)",     "벤치마크 비교 결과 유의적 차이 없음 확인됨(§B4.1.9C)"),
            ("tvm_fail",           "❌ TVM 변형이 유의적 — 벤치마크와 유의적 차이",               "이자기산기간 불일치 재설정, 만기 초과 기간 이자율 등"),
        ],
    },
    "s_sppi3": {
        "tag": "🔵 SPPI 테스트 ③",
        "title": "STEP 2-③ — 계약조건 변경 (중도상환·만기연장 등)",
        "ref": "§B4.1.10 / §B4.1.11 / §B4.1.12",
        "desc": "계약조건이 원리금 지급과 일치하지 않는 현금흐름을 발생시킵니까?",
        "helper": None,
        "options": [
            ("clause_ok",        "✅ 없음 또는 SPPI 충족 계약조건만 존재",                  "단순 고정·변동이자 / 미지급 원리금 실질 반영 중도상환(§B4.1.11)"),
            ("clause_exception", "⚠️ 중도상환 조건 불충족이나 §B4.1.12 예외 적용",           "할인·할증 취득 + 중도상환금≈액면+미지급이자 + 초기FV미미"),
            ("clause_fail",      "❌ 원리금 불일치 현금흐름 발생 (예외 미해당)",              "주가지수 도달 시 금리재설정, 기초자산 성과 연동 비소구 등"),
        ],
    },
    "s_sppi4": {
        "tag": "🔵 SPPI 테스트 ④",
        "title": "STEP 2-④ — 계약상 연계 트랑슈 (Look-through)",
        "ref": "§B4.1.20~26",
        "desc": (
            "이 금융자산이 다른 금융상품 집합에 대한 지급과 계약상 연계된 트랑슈(Tranche) 구조입니까?\n\n"
            "**Look-through 3조건 §B4.1.21**: "
            "①트랑슈 자체 SPPI ②기초집합 SPPI 특성 ③신용위험 노출도 ≤ 기초집합"
        ),
        "helper": None,
        "options": [
            ("tranche_no",   "✅ 트랑슈 구조 아님 — SPPI 충족",                    "일반 채무상품으로 SPPI 충족"),
            ("tranche_pass", "⚠️ 트랑슈 구조이나 Look-through 3조건 충족",          "3조건 모두 확인됨(§B4.1.21)"),
            ("tranche_fail", "❌ 트랑슈 구조이며 조건 불충족 또는 평가 불가",         "최초 인식시점에 평가 불가 시 → FVPL(§B4.1.26)"),
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
            ("hold",      "🏦 계약상 현금흐름 수취 (AC 모형)",                "이자·원금 만기 수취 중심. 신용위험 증가 시에만 매도. 이자수익·ECL 기준 내부보고"),
            ("both",      "⚖️ 수취 AND 매도 둘 다 필수 (FVOCI 모형)",         "유동성 관리·만기매칭·이자수익 유지 목적의 정기 매도 필수"),
            ("trading",   "📊 공정가치 실현·단기매매 (FVPL 잔여범주)",         "공정가치 기준 성과 관리·평가. 매도가 주된 현금흐름 창출 수단"),
            ("ambiguous", "❓ 판단이 모호함 — 추가 검토 필요",                "내부보고체계, 과거 매도 이력, 관리자 보상 방식 등이 명확하지 않음"),
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
            ("fvo_yes", "📌 예 — FVPL로 지정 (FVO, 취소불가)",  "회계불일치 제거·유의적 감소 확인됨. 최초 인식시점 지정. 이후 취소 불가."),
            ("fvo_no",  "✅ 아니오 — 원래 분류(AC/FVOCI) 유지",  "FVO 미적용. 분류 확정."),
        ],
    },
    "s_eq_trade": {
        "tag": "🟠 지분상품",
        "title": "STEP A-1 — 지분상품: 단기매매 목적 보유 여부",
        "ref": "§4.1.4",
        "desc": (
            "단기간 내 매도를 주된 목적으로 취득하거나, "
            "최근에 취득한 특정 금융상품 포트폴리오의 일부로서 이익 실현 패턴이 있습니까?"
        ),
        "helper": None,
        "options": [
            ("trade_yes", "📊 예 — 단기매매 목적",            "FVPL 필수 — FVOCI 취소불가 선택권 행사 불가"),
            ("trade_no",  "📌 아니오 — 전략적·장기 보유 목적", "최초 인식시점에 FVOCI 취소불가 선택권 행사 여부 검토 가능"),
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
            ("fvoci_yes", "✅ 예 — FVOCI 지정 (취소불가, 상품별)", "공정가치 변동 → OCI. 처분 시 Recycling 없음. 손상(ECL) 미적용."),
            ("fvoci_no",  "📊 아니오 — FVPL 유지 (기본값)",        "모든 공정가치 변동 → 당기손익"),
        ],
    },
}


# ──────────────────────────────────────────────────────────────────────────────
# 4. Streamlit UI
# ──────────────────────────────────────────────────────────────────────────────

def main():
    st.set_page_config(
        page_title="IFRS 9 금융자산 분류 마법사",
        page_icon="📊",
        layout="centered",
    )

    # 세션 상태 초기화
    if "answers" not in st.session_state:
        st.session_state.answers = {}
    if "history" not in st.session_state:
        st.session_state.history = []
    if "show_result" not in st.session_state:
        st.session_state.show_result = False

    # 스타일
    st.markdown(
        """
        <style>
        .stButton > button {
            border-radius: 8px;
            border: 1px solid #D0D5DD;
            background: #FAFAFA;
            width: 100%;
            text-align: left;
            padding: 0.55rem 0.9rem;
            font-size: 0.92rem;
            transition: all 0.15s;
            white-space: normal;
        }
        .stButton > button:hover {
            border-color: #1D9E75;
            background: #E9FBF4;
        }
        div[data-testid="stHorizontalBlock"] { gap: 0.4rem; }
        </style>
        """,
        unsafe_allow_html=True,
    )

    # ── 헤더 ──────────────────────────────────────────────────────────────────
    st.title("📊 IFRS 9 금융자산 분류 마법사")
    st.caption(
        "기준서: K-IFRS 1109호 4장 · 부록B · PwC 실무 가이드라인  |  "
        "용어: FVPL (당기손익-공정가치) · AC · FVOCI  |  모든 결과에 § 조항 포함"
    )
    st.divider()

    ans = st.session_state.answers

    # ── 결과 화면 ──────────────────────────────────────────────────────────────
    if st.session_state.show_result:
        _render_result(ans)
        return

    # ── 진행 중 스텝 ───────────────────────────────────────────────────────────
    seq = get_step_sequence(ans)
    current_step_id = seq[-1]

    # 마지막 스텝에 답이 있으면 결과 보여줄 준비
    # (is_terminal로 체크)
    if is_terminal(ans):
        st.session_state.show_result = True
        st.rerun()

    # 프로그레스 바
    # 전체 최대 스텝 수를 11로 고정(경로에 따라 다르지만 상한치)
    progress_val = min(len(seq) / 11, 0.95)
    st.progress(progress_val, text=f"단계 {len(seq)} 진행 중")

    # 스텝 렌더링
    step = STEP_DEFS.get(current_step_id)
    if not step:
        st.error("알 수 없는 단계입니다. 처음부터 다시 시작하세요.")
        _reset()
        return

    # 태그
    if step["tag"]:
        st.markdown(
            f'<span style="background:#EEF2FF;color:#3730A3;padding:3px 10px;'
            f'border-radius:4px;font-size:0.78rem;font-weight:600">'
            f'{step["tag"]}</span>',
            unsafe_allow_html=True,
        )
        st.write("")

    # 제목 & 참조
    st.subheader(step["title"])
    st.caption(f"📌 기준서 참조: `{step['ref']}`")

    # 설명
    st.markdown(step["desc"])

    # TVM 도우미 (helper)
    if step["helper"]:
        with st.expander(step["helper"]["title"], expanded=True):
            st.markdown(step["helper"]["body"])

    st.write("")

    # 선택지 버튼
    chosen = ans.get(current_step_id)
    for val, label, sub in step["options"]:
        is_sel = chosen == val
        btn_label = f"{'✔ ' if is_sel else ''}{label}\n\n_{sub}_"
        if st.button(btn_label, key=f"btn_{current_step_id}_{val}",
                     type="primary" if is_sel else "secondary"):
            _pick(current_step_id, val)

    st.divider()

    # 이전 / 다음 내비게이션
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
            _reset()

    # 입력 경로 미리보기
    if ans:
        with st.expander("입력 경로 확인", expanded=False):
            for k, v in ans.items():
                st.code(f"{k}  →  {v}", language=None)


def _pick(step_id: str, val: str):
    st.session_state.answers[step_id] = val
    st.rerun()


def _go_next():
    ans = st.session_state.answers
    seq = get_step_sequence(ans)
    current_id = seq[-1]
    if ans.get(current_id):
        st.session_state.history.append(current_id)
        new_seq = get_step_sequence(ans)
        # 다음 스텝이 추가됐는지 확인
        if is_terminal(ans):
            st.session_state.show_result = True
        st.rerun()


def _go_back():
    if not st.session_state.history:
        return
    prev_id = st.session_state.history.pop()
    # 현재 스텝 답 제거
    current_seq = get_step_sequence(st.session_state.answers)
    for sid in current_seq[current_seq.index(prev_id):]:
        st.session_state.answers.pop(sid, None)
    st.session_state.show_result = False
    st.rerun()


def _reset():
    st.session_state.answers = {}
    st.session_state.history = []
    st.session_state.show_result = False
    st.rerun()


# ──────────────────────────────────────────────────────────────────────────────
# 5. 결과 화면 렌더링
# ──────────────────────────────────────────────────────────────────────────────

def _render_result(ans: dict):
    r = compute_result(ans)

    # 색상 매핑
    color_map = {
        "green":  ("#E1F5EE", "#085041", "✅"),
        "blue":   ("#E6F1FB", "#0C447C", "🔵"),
        "orange": ("#FAEEDA", "#633806", "🟡"),
        "red":    ("#FCEBEB", "#791F1F", "🔴"),
    }
    bg, fg, icon = color_map.get(r["color"], ("#F5F5F5", "#333", "📋"))

    st.progress(1.0, text="분류 완료")

    # 분류 결과 배너
    st.markdown(
        f'<div style="background:{bg};border:1px solid {fg};border-radius:12px;'
        f'padding:1.2rem 1.5rem;margin-bottom:1rem">'
        f'<div style="font-size:1.5rem;font-weight:600;color:{fg}">{icon} {r["label"]}</div>'
        f'<div style="font-size:0.9rem;color:{fg};margin-top:.5rem;line-height:1.65">{r["reason"]}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )

    # 기준서 조항
    st.markdown("**📚 적용 기준서 조항**")
    cols = st.columns(min(len(r["refs"]), 4))
    for i, ref in enumerate(r["refs"]):
        cols[i % 4].code(ref, language=None)

    st.divider()

    # 후속 측정 원칙 & 회계처리
    st.markdown("**📋 후속 측정 원칙 및 회계처리**")
    for item in r["accounting"]:
        st.markdown(f"- {item}")

    # ECL 안내
    if r["ecl"]:
        st.info(
            "**ECL(기대신용손실) 손상 모형 적용 대상입니다.**  \n"
            "매 보고기간 말 기대신용손실을 인식해야 합니다. [§5.5]",
            icon="ℹ️",
        )
    else:
        st.markdown(
            '<div style="background:#F5F5F5;border-radius:8px;padding:.6rem .9rem;'
            'font-size:0.85rem;color:#666;margin:.5rem 0">'
            '⬜ ECL(손상) 적용 없음</div>',
            unsafe_allow_html=True,
        )

    # Recycling 안내
    if r["recycling"]:
        st.warning(
            "**채무상품 FVOCI**: 처분 시 OCI에 누적된 손익이 당기손익(P&L)으로 "
            "재분류(Recycling)됩니다. [§5.7.2]  \n"
            "지분상품 FVOCI(Recycling 금지)와의 핵심 차이입니다.",
            icon="⚠️",
        )
    elif r.get("recycling_note"):
        st.warning(r["recycling_note"], icon="⚠️")

    # 추가 경고
    if r["warning"]:
        st.warning(r["warning"], icon="⚠️")

    st.divider()

    # SPPI 사례 JSON (매칭 사례가 있을 때)
    case_key = r.get("case_key")
    if case_key and case_key in SPPI_CASES_DICT:
        case = SPPI_CASES_DICT[case_key]
        st.markdown("**🗂️ SPPI_CASES_DICT 매칭 사례 데이터**")
        st.caption(
            f"id: `{case['id']}` | category: `{case['category']}` | "
            f"sppi_fail: `{case['sppi_fail']}`"
        )
        with st.expander("JSON 전체 보기", expanded=False):
            st.json(case)
        st.markdown(f"**불충족 이유**: {case['reason']}")
        st.markdown(f"**판단 기준**: {case['judgment_criteria']}")
        st.markdown(f"**기준서 참조**: {', '.join(case['standard_ref'])}")
        st.divider()

    # 입력 경로 요약
    st.markdown("**🗺️ 입력 경로 요약**")
    with st.expander("답변 이력 전체 보기", expanded=False):
        for k, v in ans.items():
            st.code(f"{k:20s}  →  {v}", language=None)

    # 버튼
    st.write("")
    col1, col2, col3 = st.columns([1, 1, 1])
    with col1:
        if st.button("← 이전 단계로", use_container_width=True):
            st.session_state.show_result = False
            # 마지막 스텝의 답 제거
            seq = get_step_sequence(ans)
            if seq:
                ans.pop(seq[-1], None)
            st.rerun()
    with col2:
        if st.button("🔄 처음부터 다시", type="primary", use_container_width=True):
            _reset()
    with col3:
        # 결과 텍스트 클립보드용 출력
        if st.button("📋 결과 텍스트 출력", use_container_width=True):
            _show_text_report(r, ans)


def _show_text_report(r: dict, ans: dict):
    """텍스트 형식 결과 리포트 출력"""
    lines = [
        "=" * 60,
        "IFRS 9 금융자산 분류 결과 리포트",
        "=" * 60,
        f"분류: {r['label']}",
        "",
        "[ 분류 근거 ]",
        r["reason"],
        "",
        "[ 적용 기준서 조항 ]",
        "  " + " | ".join(r["refs"]),
        "",
        "[ 후속 측정 원칙 및 회계처리 ]",
    ]
    for item in r["accounting"]:
        lines.append(f"  - {item}")
    lines.append("")
    lines.append(f"[ ECL 손상 적용 여부 ]  {'적용' if r['ecl'] else '미적용'}")
    lines.append(f"[ Recycling 발생 여부 ]  {'발생(채무상품 FVOCI)' if r['recycling'] else '없음'}")
    if r.get("recycling_note"):
        lines.append(f"  ※ {r['recycling_note']}")
    if r["warning"]:
        lines.append(f"\n[ 주의사항 ]\n  {r['warning']}")
    lines.append("")
    lines.append("[ 입력 경로 ]")
    for k, v in ans.items():
        lines.append(f"  {k}: {v}")
    lines.append("=" * 60)
    st.code("\n".join(lines), language=None)


# ──────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    main()
