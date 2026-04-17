"""
IFRS 9 (K-IFRS 1109) 금융자산 분류 마법사 v2
─────────────────────────────────────────────
실행 방법:
    pip install streamlit
    streamlit run app.py

개선 사항 (v2):
    · STEP_DEFS: 비유 설명, helper 확장(s_host/s_sppi4/s_bm), 가이드형 선택지
    · 기준서 참조: st.expander 로 핵심 문구 제공
    · 사이드바: 실무 용어 사전 상시 노출
    · 진행 상태: 단계 번호·퍼센트 시각화
    · 결과 페이지: 회계처리 요약표(st.table), 알림 박스 적극 활용
"""

import streamlit as st

# ══════════════════════════════════════════════════════════════════════════════
# 0. SPPI 불충족 사례 딕셔너리  (JSON 구조 — 추후 DB 교체 가능)
# ══════════════════════════════════════════════════════════════════════════════
SPPI_CASES_DICT: dict = {
    "case_F": {
        "id": "case_F", "label": "상품F — 전환사채", "category": "지분연동",
        "instrument_desc": "확정수량의 발행자 지분상품으로 전환가능한 채권",
        "sppi_fail": True,
        "reason": "계약상 현금흐름이 기본대여계약과 일관되지 않는 수익 반영 — 발행자 지분가치에 연계됨",
        "standard_ref": ["§B4.1.14", "§B4.1.7A"],
        "judgment_criteria": "금융자산 주계약 시 내재파생 분리불가(§4.3.2). 지분가치 연동=§B4.1.7A 위반",
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
        "id": "case_A_ok", "label": "상품A — 인플레이션 연계 (SPPI 충족 참고)", "category": "참고:SPPI충족",
        "instrument_desc": "발행통화 인플레이션지수 연계, 비레버리지, 원금 보장 채권",
        "sppi_fail": False,
        "reason": "SPPI 충족: 인플레이션 연계는 TVM을 현행 수준으로 재설정 — TVM 대가에 해당",
        "standard_ref": ["§B4.1.13 상품A", "§B4.1.7A"],
        "judgment_criteria": "채무자 성과·주가지수 추가 연계 시 불충족. 비레버리지 조건 필수 확인",
    },
}

# ══════════════════════════════════════════════════════════════════════════════
# 1. 기준서 조항 핵심 문구 사전  (st.expander 에 표시)
# ══════════════════════════════════════════════════════════════════════════════
STD_TEXTS: dict = {
    "§4.1.1": "금융자산은 최초 인식 시 (a) 금융자산의 관리를 위한 사업모형, (b) 금융자산의 계약상 현금흐름 특성에 근거하여 상각후원가·FVOCI·FVPL로 분류한다.",
    "§4.3.2": "복합계약의 주계약이 이 기준서의 적용범위에 해당하는 자산이라면, 내재파생상품을 별도로 회계처리하지 않는다. 복합계약 전체에 §4.1.1~4.1.5를 적용한다.",
    "§4.3.3": "주계약이 이 기준서의 적용범위에 해당하는 자산이 아닌 경우, 내재파생상품은 ① 경제적 특성·위험이 주계약과 밀접하게 관련되지 않고 ② 별도 계약이라면 파생상품 정의를 충족하며 ③ 공정가치 변동을 당기손익으로 인식하지 않는 경우에 분리한다.",
    "§B4.1.7A": "이자는 화폐의 시간가치, 신용위험, 기타 기본대여 위험·원가, 이윤에 대한 대가로만 구성되어야 한다. 기본대여계약과 일관되지 않는 그 밖의 위험이나 변동성에 노출시키는 계약상 현금흐름은 SPPI를 충족하지 않는다.",
    "§B4.1.9": "레버리지는 현금흐름의 변동성을 증가시켜 이자의 경제적 특성을 상실하게 만든다. 독립적인 옵션, 선도, 스왑은 레버리지를 내재한다.",
    "§B4.1.9C": "TVM 변형 평가 시, 수정되지 않은 금융상품(기준 상품)의 현금흐름과 비교하여 미할인 현금흐름 차이가 유의적인지를 합리적으로 가능한 시나리오 범위에서 평가한다.",
    "§B4.1.21": "계약상 연계 트랑슈: (a) 트랑슈 자체 계약조건이 SPPI 충족, (b) 기초 금융상품 집합이 SPPI 특성 충족, (c) 트랑슈의 신용위험 익스포저가 기초집합의 신용위험을 초과하지 않을 때 SPPI를 충족할 수 있다.",
    "§B4.1.2B": "사업모형은 단순한 주장이 아닌 사실에 근거하여 결정된다. 평가 증거에는 금융자산의 성과가 어떻게 평가·보고되는지, 위험이 어떻게 관리되는지, 경영진이 어떻게 보상받는지가 포함된다.",
    "§4.1.5": "기업은 최초 인식 시점에 인식·측정 불일치(회계불일치)를 제거하거나 유의적으로 감소시키기 위해 금융자산을 FVPL로 측정하도록 취소불가로 지정할 수 있다.",
    "§4.1.4": "지분상품 투자에 대해 단기매매 목적이 아닌 경우, 최초 인식 시점에 공정가치 변동을 OCI에 표시하는 취소불가 선택을 할 수 있다. 이 경우 어떠한 손익도 나중에 당기손익으로 재분류되지 않는다.",
    "§5.7.5": "지분상품 FVOCI 지정 시, 처분·제거 시에도 OCI에 누적된 손익을 당기손익으로 재분류하지 않는다. 다만, 자본 내의 이전은 허용된다.",
    "§5.5 (ECL)": "기대신용손실 모형: 최초 인식 후 신용위험이 유의적으로 증가한 경우 전체기간 ECL을, 그렇지 않은 경우 12개월 ECL을 손실충당금으로 인식한다.",
}

# ══════════════════════════════════════════════════════════════════════════════
# 2. 분류 결과 계산 로직  (원본 로직 유지)
# ══════════════════════════════════════════════════════════════════════════════

def sppi_fail_result(fail_key: str, case_key) -> dict:
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
    refs_map = {
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
        "classification": "FVPL", "label": "당기손익-공정가치 (FVPL) — SPPI 불충족",
        "color": "red", "reason": "SPPI 테스트 불충족. " + msgs.get(fail_key, ""),
        "refs": refs_map.get(fail_key, ["§4.1.4"]),
        "ecl": False, "recycling": False, "recycling_note": None,
        "accounting": ["공정가치로 최초 인식 및 후속 측정", "모든 공정가치 변동 → 당기손익", "ECL(손상) 적용 없음"],
        "warning": None, "case_key": case_key,
    }


def compute_result(ans: dict) -> dict:
    at = ans.get("s_asset")
    if at == "deriv":
        return {
            "classification": "FVPL", "label": "당기손익-공정가치 (FVPL) — 독립 파생상품",
            "color": "red", "reason": "독립 파생상품은 항상 FVPL로 측정합니다. 레버리지가 내재되어 있어 SPPI 불충족이며, AC·FVOCI 분류가 불가합니다.",
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
                    "color": "red", "reason": "분리 3요건 충족. 내재파생상품은 FVPL로 측정하고, 주계약은 관련 기준서에 따라 별도 회계처리합니다.",
                    "refs": ["§4.3.3", "§4.3.4", "§B4.3.5"], "ecl": False, "recycling": False, "recycling_note": None,
                    "accounting": ["내재파생상품 → FVPL (공정가치 측정)", "주계약 → 관련 기준서 별도 처리", "재평가 금지(계약 유의적 변경 시 제외) [§B4.3.11]"],
                    "warning": "밀접관련 내재파생(§B4.3.8)은 분리하지 않습니다: 레버리지 없는 금리캡·플로어, 인플레이션 리스료, 단위연계특성 등",
                    "case_key": "case_embedded_fa",
                }
            return {
                "classification": "FVPL", "label": "복합계약 전체 → FVPL",
                "color": "red", "reason": "분리 3요건 미충족 또는 내재파생상품을 신뢰성 있게 측정할 수 없습니다. 복합계약 전체를 FVPL로 측정합니다.",
                "refs": ["§4.3.6", "§4.3.7"], "ecl": False, "recycling": False, "recycling_note": None,
                "accounting": ["복합계약 전체 → FVPL 측정", "공정가치 변동 전액 → 당기손익"],
                "warning": None, "case_key": "case_embedded_fa",
            }
    if at == "equity":
        trade = ans.get("s_eq_trade")
        if trade == "trade_yes":
            return {
                "classification": "FVPL", "label": "당기손익-공정가치 (FVPL) — 단기매매 지분",
                "color": "red", "reason": "단기매매 목적 지분상품은 FVPL로 측정합니다. FVOCI 취소불가 선택권을 행사할 수 없습니다.",
                "refs": ["§4.1.4"], "ecl": False, "recycling": False, "recycling_note": None,
                "accounting": ["공정가치로 측정", "모든 공정가치 변동 → 당기손익", "배당 → 당기손익", "ECL(손상) 적용 없음"],
                "warning": None, "case_key": None,
            }
        if ans.get("s_eq_fvoci") == "fvoci_yes":
            return {
                "classification": "FVOCI", "label": "기타포괄손익-공정가치 (FVOCI) — 지분 취소불가 지정",
                "color": "blue", "reason": "단기매매가 아닌 지분상품에 대해 최초 인식시점에 FVOCI 취소불가 선택권을 행사하였습니다.",
                "refs": ["§4.1.4", "§5.7.5", "§5.7.6", "§B5.7.1"], "ecl": False, "recycling": False,
                "recycling_note": "지분상품 FVOCI: 처분 시에도 OCI 누적손익이 P&L로 재분류(Recycling)되지 않습니다. 자본 내 이전만 허용됩니다.",
                "accounting": ["공정가치 변동 전액 → OCI", "배당(투자원가 회수 성격 제외) → 당기손익 [§B5.7.1]",
                                "처분 시 OCI 누적손익 → P&L 재분류 금지 (Recycling 없음) [§5.7.5]", "ECL(손상) 규정 미적용"],
                "warning": "처분 시 OCI → P&L 재분류 없음(Recycling 금지). 손상(ECL) 인식하지 않음. 자본 내 이전만 허용.",
                "case_key": None,
            }
        return {
            "classification": "FVPL", "label": "당기손익-공정가치 (FVPL) — 지분 기본값",
            "color": "orange", "reason": "FVOCI 선택권을 행사하지 않은 비단기매매 지분상품은 FVPL로 측정합니다.",
            "refs": ["§4.1.4"], "ecl": False, "recycling": False, "recycling_note": None,
            "accounting": ["공정가치로 측정", "모든 공정가치 변동 → 당기손익", "배당 → 당기손익"],
            "warning": None, "case_key": None,
        }
    case_map = {"fail_equity": "case_equity_idx", "fail_commodity": "case_I", "fail_profit": "case_profit",
                "fail_inverse": "case_G", "fail_leverage": "case_leverage", "fail_defer": "case_H"}
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
            "classification": "FVPL", "label": "추가 검토 필요 → 잠정 FVPL", "color": "orange",
            "reason": "입력된 정보만으로는 사업모형을 명확히 판단하기 어렵습니다. 내부보고체계, 과거 매도 이력, 관리자 보상 방식 등 추가 증거를 검토하십시오. 기준서·가이드라인 상충 시 보수적 접근으로 잠정 FVPL 분류합니다.",
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
            "color": "orange", "reason": "회계불일치 해소를 위한 공정가치 지정선택권(FVO) 행사. 최초 인식시점에 취소불가로 지정합니다.",
            "refs": ["§4.1.5", "§B4.1.29~32"], "ecl": False, "recycling": False, "recycling_note": None,
            "accounting": ["공정가치로 측정", "모든 공정가치 변동 → 당기손익", "최초 인식시점 지정·취소불가", "ECL(손상) 적용 없음"],
            "warning": "FVO 지정은 취소불가입니다. 최초 인식시점에 회계불일치 해소 요건을 면밀히 검토하십시오.",
            "case_key": None,
        }
    if bm == "hold":
        return {
            "classification": "AC", "label": "상각후원가 (AC)",
            "color": "green", "reason": "SPPI 충족 + 계약상 현금흐름 수취 목적 사업모형 → AC 측정.",
            "refs": ["§4.1.2", "§4.1.2⑴", "§B4.1.2C", "§B4.1.3A"], "ecl": True, "recycling": False, "recycling_note": None,
            "accounting": ["최초 인식: 공정가치 (거래원가 포함)", "후속 측정: 유효이자율법 적용 상각후원가",
                           "이자수익 → 당기손익 (유효이자율법)", "ECL(기대신용손실) 손상 모형 적용 [§5.5]",
                           "처분 시 장부금액과 수취대가 차이 → 당기손익"],
            "warning": None, "case_key": None,
        }
    if bm == "both":
        return {
            "classification": "FVOCI", "label": "기타포괄손익-공정가치 (FVOCI) — 채무상품",
            "color": "blue", "reason": "SPPI 충족 + 수취와 매도 둘 다가 목적인 사업모형 → FVOCI 측정.",
            "refs": ["§4.1.2A", "§4.1.2A⑴", "§B4.1.4A", "§B4.1.4C"], "ecl": True, "recycling": True, "recycling_note": None,
            "accounting": ["최초 인식: 공정가치", "후속 측정: 공정가치",
                           "이자수익·ECL(손상)·외환손익 → 당기손익", "그 외 공정가치 변동 → OCI",
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
# 3. 스텝 시퀀스 계산
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
# 4. STEP_DEFS — 전면 개선판
#    · desc: 비유/쉬운 설명 + 판단 핵심 한 줄
#    · helper: s_host, s_sppi4, s_bm 신규 추가 / s_sppi2 유지
#    · options: 가이드형 sub 문구 ("만약 ~라면 이 항목을 선택하세요")
# ══════════════════════════════════════════════════════════════════════════════

STEP_DEFS: dict = {
    # ── STEP 0: 자산 성격 ────────────────────────────────────────────────────
    "s_asset": {
        "tag": "",
        "title": "STEP 0 — 금융자산의 기본 성격을 알려주세요",
        "ref": "§4.1.1",
        "ref_key": "§4.1.1",
        "desc": (
            "🏷️ **이 단계는 금융상품의 '혈액형'을 확인하는 단계입니다.** "
            "같은 채권이라도 전환사채처럼 특별한 조건이 붙어있으면 다른 경로로 분류됩니다.\n\n"
            "보유하고 있는 금융자산이 아래 중 어떤 성격에 가장 가까운지 선택하세요."
        ),
        "helper": None,
        "options": [
            ("debt",   "📄 채무상품 — 원금+이자 구조",
             "만약 '원금과 이자를 돌려받는 계약'(대출채권·회사채·국채 등)이라면 이 항목을 선택하세요."),
            ("equity", "📈 지분상품 — 주식·출자금",
             "만약 '주주로서 회사의 일부를 소유하는 계약'(보통주·우선주·출자증권)이라면 이 항목을 선택하세요."),
            ("deriv",  "🔄 독립 파생상품 — 옵션·선도·스왑",
             "만약 주계약 없이 단독으로 거래되는 옵션·금리스왑·선물환 등이라면 이 항목을 선택하세요."),
            ("hybrid", "⚠️ 복합계약 — 채권 안에 파생이 숨어있는 구조",
             "만약 전환사채·신종자본증권처럼 채권(주계약)과 옵션·파생(내재파생)이 결합된 상품이라면 이 항목을 선택하세요."),
        ],
    },

    # ── STEP 1: 복합계약 주계약 ──────────────────────────────────────────────
    "s_host": {
        "tag": "🔴 예외처리 — 내재파생상품",
        "title": "STEP 1 — 복합계약의 '주계약'이 무엇인지 확인하세요",
        "ref": "§4.3.2 / §4.3.3",
        "ref_key": "§4.3.2",
        "desc": (
            "🧩 **이 단계는 '복합계약 해체 전에 열쇠가 채권용인지 확인'하는 단계입니다.** "
            "IFRS 9는 채권(금융자산)이 주계약이면 내부 파생상품을 꺼내지 않고 전체를 하나로 분석합니다. "
            "반면 금융부채·비금융자산이 주계약이면 파생상품을 분리해서 따로 처리할 수 있습니다.\n\n"
            "**핵심: 주계약이 '채권·대여금 등 금융자산'이면 분리 금지 — 전체에 SPPI 테스트 적용**"
        ),
        "helper": {
            "title": "💡 실무 상품 예시 — 어느 경로에 해당하나요?",
            "body": (
                "**📄 금융자산이 주계약인 경우 (→ 분리 금지, SPPI 테스트 전체 적용)**\n"
                "- 전환사채 (주계약: 사채 / 내재: 전환권)\n"
                "- 신종자본증권 (주계약: 후순위채 / 내재: 이자이연 옵션)\n"
                "- 조건부전환사채 COCOS (주계약: 채권 / 내재: 주식전환 트리거)\n\n"
                "**🏢 비금융자산·금융부채가 주계약인 경우 (→ 분리 요건 3가지 검토)**\n"
                "- 리스계약에 내재된 환율연계 임차료 (주계약: 비금융 리스)\n"
                "- 금융부채에 내재된 주가연계 이자 (주계약: 금융부채)"
            ),
        },
        "options": [
            ("fa_host",    "📄 주계약이 금융자산 (채권·대여금 등 채무상품)",
             "만약 복합계약의 뼈대가 '이자와 원금을 받는 채권 또는 대여금 구조'라면 이 항목을 선택하세요. → 내재파생 분리 금지, 전체 SPPI 테스트"),
            ("other_host", "🏢 주계약이 금융부채 또는 비금융자산 (리스·상품계약 등)",
             "만약 주계약이 금융부채이거나 리스·상품공급계약 등 비금융자산이라면 이 항목을 선택하세요. → 분리 3요건 검토"),
        ],
    },

    # ── STEP 1-1: 분리 요건 ──────────────────────────────────────────────────
    "s_sep": {
        "tag": "🔴 예외처리 — 분리 3요건",
        "title": "STEP 1-1 — 내재파생상품을 분리할 수 있는 3가지 조건을 확인하세요",
        "ref": "§4.3.3 / §B4.3.5 / §B4.3.8",
        "ref_key": "§4.3.3",
        "desc": (
            "🔬 **이 단계는 '복합계약에서 파생상품 부분만 꺼낼 수 있는지' 확인하는 단계입니다.**\n\n"
            "분리 3요건:\n"
            "① 경제적 특성·위험이 주계약과 밀접하게 관련되지 **않음**\n"
            "② 별도 계약이라면 파생상품 정의를 **충족**\n"
            "③ 복합계약 전체의 공정가치 변동을 당기손익으로 인식하지 **않음**\n\n"
            "**분리 안 하는 예외 (§B4.3.8)**: 레버리지 없는 금리캡·플로어, 인플레이션 리스료, 단위연계특성"
        ),
        "helper": None,
        "options": [
            ("sep_ok",   "✅ 3요건 모두 충족 — 내재파생상품을 분리할 수 있음",
             "만약 위 3가지 조건이 모두 '해당된다'고 판단되면 이 항목을 선택하세요. → 내재파생 FVPL, 주계약 별도 처리"),
            ("sep_fail", "❌ 3요건 미충족 또는 분리·측정이 실질적으로 불가능",
             "만약 3가지 중 하나라도 충족하지 못하거나, 내재파생을 따로 측정하기 어렵다면 이 항목을 선택하세요. → 복합계약 전체 FVPL"),
        ],
    },

    # ── STEP 2-①: SPPI 비대여변수 ────────────────────────────────────────────
    "s_sppi1": {
        "tag": "🔵 SPPI 테스트 ①",
        "title": "STEP 2-① — 이자·원금이 '이상한 변수'에 연동되어 있나요?",
        "ref": "§B4.1.7A / §B4.1.8A / §B4.1.9",
        "ref_key": "§B4.1.7A",
        "desc": (
            "💧 **이 단계는 '이자가 순수한 대여 비용인지, 아니면 주식·원자재 같은 딴 것과 섞인 건지' 확인하는 단계입니다.**\n\n"
            "IFRS 9는 이자가 오직 **화폐의 시간가치 + 신용위험 + 기본대여원가 + 이윤**으로만 구성되어야 한다고 봅니다. "
            "주가나 원자재 가격, 채무자 이익 같은 '대여와 무관한 요소'가 섞이면 SPPI 실격입니다.\n\n"
            "*(영향이 매우 미미한 de minimis 특성은 무시 가능 — §B4.1.18)*"
        ),
        "helper": None,
        "options": [
            ("fail_equity",    "❌ 주가·주가지수 연동 이자 또는 원금",
             "만약 이자율이나 상환금액이 코스피·S&P500 같은 주가지수나 특정 주식 가격에 따라 달라진다면 이 항목을 선택하세요. (예: 전환사채, ELS 연계채권)"),
            ("fail_commodity", "❌ 원자재·탄소가격지수(시장추적형) 연동",
             "만약 금·원유·탄소가격지수 등 원자재 시장가격이 이자율 결정 기준이 된다면 이 항목을 선택하세요."),
            ("fail_profit",    "❌ 채무자 순이익·매출 비율 연동 이자",
             "만약 이자가 발행회사의 순이익이나 매출의 일정 %로 결정된다면 이 항목을 선택하세요. (예: 이익참가사채, 수익채권)"),
            ("fail_inverse",   "❌ 역변동금리 — 시장금리 오르면 이자가 오히려 내려가는 구조",
             "만약 시장금리가 상승할수록 이 상품의 이자가 감소하는 역방향 구조라면 이 항목을 선택하세요. (예: Inverse Floater)"),
            ("fail_leverage",  "❌ 레버리지 내재 — 독립 옵션·선도·스왑 수준의 변동성",
             "만약 이 상품이 단독 거래 시 파생상품으로 분류될 수준의 레버리지를 포함하고 있다면 이 항목을 선택하세요."),
            ("fail_defer",     "❌ 이자이연 가능 + 이연이자에 복리 미발생",
             "만약 발행자가 이자 지급을 미룰 수 있는데 그 밀린 이자에 이자(복리)가 붙지 않는다면 이 항목을 선택하세요. (예: AT1 신종자본증권 일부 유형)"),
            ("none",           "✅ 위 항목 모두 해당 없음 — 순수 원리금 구조",
             "만약 이자가 시장금리(SOFR·EURIBOR 등)나 고정금리에만 연동되고, 위 항목이 전혀 해당되지 않는다면 이 항목을 선택하세요. → 다음 단계 계속"),
        ],
    },

    # ── STEP 2-②: TVM 변형 ───────────────────────────────────────────────────
    "s_sppi2": {
        "tag": "🔵 SPPI 테스트 ②",
        "title": "STEP 2-② — 이자율 재설정 방식이 '시간 흐름'과 맞게 설계되어 있나요?",
        "ref": "§B4.1.9B~9D",
        "ref_key": "§B4.1.9C",
        "desc": (
            "⏱️ **이 단계는 '이자율 단위와 지급 주기가 같은 짝끼리 맞는지' 확인하는 단계입니다.** "
            "예를 들어 '월급을 연봉 기준으로 계산하지 않고 월 기준으로 계산해야 올바르다'는 것과 같은 원리입니다."
        ),
        "helper": {
            "title": "💡 TVM 판단 도우미 — 이자율 기간 일치 확인",
            "body": (
                "**핵심 질문: '이자율 재설정 주기'와 '해당 이자율의 만기 기간'이 일치합니까?**\n\n"
                "| 재설정 주기 | 사용하는 이자율 기간 | 일치 여부 |\n"
                "|---|---|---|\n"
                "| 매월 | 1개월 이자율 (1M SOFR) | ✅ 일치 |\n"
                "| 분기 | 3개월 이자율 (3M EURIBOR) | ✅ 일치 |\n"
                "| 매월 | **1년** 이자율 | ❌ 불일치 |\n"
                "| 6개월 | **5년** 이자율 (만기=5년) | ❌ 불일치 |\n\n"
                "불일치 → 벤치마크(기간 일치 가상 금융상품) 현금흐름과 비교 평가 필요  \n"
                "**규제이자율 예외 §B4.1.9E**: 중앙은행·금융감독 규제금리가 TVM을 대략적으로 반영한다면 허용  \n"
                "**AT1 신종자본증권**: 이자이연 조건과 TVM 변형 여부를 동시에 검토"
            ),
        },
        "options": [
            ("tvm_ok",             "✅ 이자기산기간과 이자율 기간이 일치 (또는 영향이 미미)",
             "만약 '월 재설정에 1개월 금리'처럼 기간이 맞거나, 불일치 영향이 거의 없다면 이 항목을 선택하세요."),
            ("tvm_modified_minor", "⚠️ 기간 불일치가 있으나 벤치마크와 유의적 차이 없음 확인됨",
             "만약 기간이 약간 맞지 않지만 벤치마크 비교 결과 현금흐름 차이가 유의적이지 않다고 판단되면 이 항목을 선택하세요."),
            ("tvm_fail",           "❌ TVM 변형이 유의적 — 벤치마크 현금흐름과 유의적 차이 확인됨",
             "만약 이자율 기간 불일치가 명백하고 벤치마크 현금흐름과 유의적 차이가 발생한다면 이 항목을 선택하세요. (예: 1년 금리로 매월 재설정)"),
        ],
    },

    # ── STEP 2-③: 계약조건 변경 ─────────────────────────────────────────────
    "s_sppi3": {
        "tag": "🔵 SPPI 테스트 ③",
        "title": "STEP 2-③ — 계약에 '원리금 이외의 현금흐름'을 만드는 특수 조건이 있나요?",
        "ref": "§B4.1.10 / §B4.1.11 / §B4.1.12",
        "ref_key": "§B4.1.7A",
        "desc": (
            "📋 **이 단계는 '계약서의 특수 조항이 원리금 지급 흐름을 방해하는지' 확인하는 단계입니다.** "
            "중도상환·만기연장 조건 자체는 문제없지만, 그 조건이 원리금과 맞지 않는 금액을 만들어내면 SPPI를 통과하지 못합니다."
        ),
        "helper": None,
        "options": [
            ("clause_ok",        "✅ 특수 조건 없음, 또는 SPPI를 깨지 않는 조건만 존재",
             "만약 단순 고정·변동금리 채권이거나, 중도상환 금액이 '미지급 원리금 + 합리적 보상' 수준이라면 이 항목을 선택하세요."),
            ("clause_exception", "⚠️ 중도상환 조건이 SPPI 기준을 약간 벗어나나 §B4.1.12 예외에 해당",
             "만약 할인·할증 발행 채권인데 중도상환 금액이 액면+미지급이자 수준이고 그 옵션의 최초 공정가치가 매우 작다면 이 항목을 선택하세요."),
            ("clause_fail",      "❌ 원리금 지급과 일치하지 않는 현금흐름을 만드는 계약조건 존재",
             "만약 주가지수 도달 시 이자율이 갑자기 뛰거나, 자산 성과에 따라 상환금이 달라지는 조건이 있다면 이 항목을 선택하세요."),
        ],
    },

    # ── STEP 2-④: 트랑슈 ─────────────────────────────────────────────────────
    "s_sppi4": {
        "tag": "🔵 SPPI 테스트 ④",
        "title": "STEP 2-④ — 이 자산이 ABS·CLO처럼 다른 자산 묶음에 연결된 구조입니까?",
        "ref": "§B4.1.20~26",
        "ref_key": "§B4.1.21",
        "desc": (
            "🏗️ **이 단계는 'ABS·CLO·MBS처럼 풀(Pool) 구조 안의 한 조각인지' 확인하는 단계입니다.** "
            "트랑슈는 기초자산 집합에서 나오는 현금흐름을 조각내어 선순위·후순위로 나눈 구조입니다. "
            "'내 조각(트랑슈)뿐 아니라 전체 풀도 SPPI를 충족하고, 내 조각이 풀보다 더 위험하지 않아야' SPPI를 통과할 수 있습니다."
        ),
        "helper": {
            "title": "💡 트랑슈 구조 실무 상품 예시",
            "body": (
                "**트랑슈 구조에 해당하는 대표 상품**\n\n"
                "| 상품 유형 | 설명 | Look-through 필요 |\n"
                "|---|---|---|\n"
                "| ABS (자산유동화증권) | 대출채권·매출채권을 유동화한 증권 | ✅ 필요 |\n"
                "| MBS (주택저당증권) | 주택담보대출을 기초로 발행 | ✅ 필요 |\n"
                "| CLO (대출채권담보부증권) | 기업대출 Pool을 선·후순위 분리 | ✅ 필요 |\n"
                "| CDO/CBO | 채권·대출 혼합 구조 | ✅ 필요 |\n"
                "| 일반 회사채 | 단일 발행자의 직접 채무 | ❌ 해당 없음 |\n\n"
                "**Look-through 3조건 §B4.1.21**\n"
                "1️⃣ 이 트랑슈 자체 계약조건이 SPPI 충족\n"
                "2️⃣ 기초 금융상품 집합(Pool)이 SPPI 특성 충족\n"
                "3️⃣ 이 트랑슈의 신용위험 노출이 기초집합 신용위험 이하\n\n"
                "💡 최초 인식 시점에 기초집합을 평가할 수 없다면 → 즉시 **FVPL** (§B4.1.26)"
            ),
        },
        "options": [
            ("tranche_no",   "✅ 트랑슈 구조 아님 — 단일 발행자의 일반 채무상품",
             "만약 일반 회사채·국채·대여금처럼 특정 발행자에게 직접 빌려주는 구조라면 이 항목을 선택하세요. → SPPI 충족 확인"),
            ("tranche_pass", "⚠️ 트랑슈 구조이지만 Look-through 3조건 모두 충족",
             "만약 ABS·CLO 등이지만 기초집합 분석 결과 3가지 조건이 모두 확인되었다면 이 항목을 선택하세요."),
            ("tranche_fail", "❌ 트랑슈 구조이며 조건 불충족 또는 최초 인식시점에 평가 자체가 불가",
             "만약 ABS·CLO 등인데 기초집합이 불투명하거나 3조건 중 하나라도 충족 안 된다면 이 항목을 선택하세요. → FVPL"),
        ],
    },

    # ── STEP 3: 사업모형 ─────────────────────────────────────────────────────
    "s_bm": {
        "tag": "🟢 사업모형 테스트",
        "title": "STEP 3 — 이 금융자산을 '어떤 목적으로 운용'하고 있나요?",
        "ref": "§4.1.1⑴ / §B4.1.2 / §B4.1.2B",
        "ref_key": "§B4.1.2B",
        "desc": (
            "🎯 **이 단계는 '투자 목적이 이자 수취인지, 시세차익인지, 아니면 둘 다인지' 구분하는 단계입니다.** "
            "같은 국채라도 '만기까지 보유해서 이자 받는 회사'는 AC, '필요할 때 팔아서 유동성 확보하는 은행'은 FVOCI, "
            "'매일 사고파는 트레이딩 데스크'는 FVPL이 됩니다.\n\n"
            "**중요**: 이 판단은 개별 상품이 아니라 **포트폴리오(집합) 수준**에서, **실제 관리 방식(사실)**에 근거해야 합니다."
        ),
        "helper": {
            "title": "💡 사업모형 판단 체크리스트 — 내부증거 확인",
            "body": (
                "**사업모형 판단을 위한 4가지 내부 증거 (§B4.1.2B)**\n\n"
                "| 확인 항목 | AC 신호 | FVOCI 신호 | FVPL 신호 |\n"
                "|---|---|---|---|\n"
                "| 내부 성과 보고 기준 | 이자수익·ECL | 총수익(이자+매도익) | 공정가치 손익 |\n"
                "| 경영진 보상 기준 | 이자수익 달성 | 총수익률 | 공정가치 수익률 |\n"
                "| 매도 빈도·이유 | 신용위험 증가 시만 | 유동성·만기 관리 | 적극적·빈번한 매도 |\n"
                "| 위험관리 목적 | 만기까지 ECL 관리 | ALM(자산부채 매칭) | FV 변동성 관리 |\n\n"
                "**대표 포트폴리오 예시**\n"
                "- 🏦 **AC**: 은행 기업대출 포트폴리오, 보험사 만기보유 채권\n"
                "- ⚖️ **FVOCI**: 은행 유동성 포트폴리오(LCR 대응), ALM 채권 포트폴리오\n"
                "- 📊 **FVPL**: IB 트레이딩 북, 헤지펀드 채권 포지션"
            ),
        },
        "options": [
            ("hold",      "🏦 계약상 현금흐름 수취가 주된 목적 → AC 모형",
             "만약 '이 채권을 만기까지 보유하면서 이자와 원금을 받는 것'이 핵심 목적이고, 매도는 신용위험 증가 시에만 한다면 이 항목을 선택하세요."),
            ("both",      "⚖️ 현금흐름 수취 AND 매도 둘 다 필수 → FVOCI 모형",
             "만약 이자를 받으면서도 유동성 확보·만기 조절·이자수익 유지를 위해 정기적으로 매도가 반드시 필요하다면 이 항목을 선택하세요."),
            ("trading",   "📊 공정가치 실현·단기매매가 주된 목적 → FVPL 잔여범주",
             "만약 매도를 통한 시세차익이 주된 수익원이거나, 경영진에게 공정가치 기준으로 성과를 보고한다면 이 항목을 선택하세요."),
            ("ambiguous", "❓ 위 중 명확하게 해당하는 것이 없음 → 추가 검토 필요",
             "만약 내부 보고 방식이나 운용 목적이 명확하지 않아 어느 모형인지 확신하기 어렵다면 이 항목을 선택하세요. → 잠정 FVPL 분류"),
        ],
    },

    # ── STEP 4: FVO ──────────────────────────────────────────────────────────
    "s_fvo": {
        "tag": "🟡 FVO 최종 확인",
        "title": "STEP 4 — 회계 장부 불일치 해소를 위해 FVPL로 직접 지정하시겠습니까?",
        "ref": "§4.1.5 / §B4.1.29~32",
        "ref_key": "§4.1.5",
        "desc": (
            "🔧 **이 단계는 '장부를 통일시키기 위한 마지막 선택지'입니다.** "
            "예를 들어 관련 부채는 공정가치로 측정하는데 이 자산은 AC로 측정한다면 금리가 변할 때마다 "
            "손익이 들쭉날쭉 보이는 '회계불일치'가 생깁니다. "
            "이를 해소하기 위해 이 자산도 FVPL로 지정할 수 있습니다.\n\n"
            "⚠️ **한 번 지정하면 영구적으로 취소 불가(irrevocable)합니다. 신중하게 결정하세요.**"
        ),
        "helper": None,
        "options": [
            ("fvo_yes", "📌 예 — 회계불일치 해소를 위해 FVPL로 지정 (취소불가)",
             "만약 관련 금융부채·파생상품이 이미 FVPL로 측정되어 이 자산도 맞춰야 한다면 이 항목을 선택하세요. 취소 불가이므로 법무·회계 검토 후 결정하세요."),
            ("fvo_no",  "✅ 아니오 — 회계불일치 없음, 원래 분류(AC/FVOCI)를 확정",
             "만약 회계불일치가 없거나 FVO 지정이 필요하지 않다면 이 항목을 선택하세요. → 앞서 결정한 AC 또는 FVOCI로 최종 확정"),
        ],
    },

    # ── STEP A-1: 지분상품 단기매매 ──────────────────────────────────────────
    "s_eq_trade": {
        "tag": "🟠 지분상품",
        "title": "STEP A-1 — 이 주식·지분을 '곧 팔 목적'으로 샀나요?",
        "ref": "§4.1.4",
        "ref_key": "§4.1.4",
        "desc": (
            "⚡ **이 단계는 '단기 시세차익용인지, 장기 전략 보유인지' 구분하는 단계입니다.** "
            "트레이딩 목적 주식은 FVPL이 강제되며, FVOCI를 선택할 기회 자체가 없습니다."
        ),
        "helper": None,
        "options": [
            ("trade_yes", "📊 예 — 단기간 내 매도를 목적으로 취득한 단기매매 주식",
             "만약 트레이딩 북에 편입된 주식이거나 단기 시세차익을 노리고 취득했다면 이 항목을 선택하세요. → FVPL 강제, FVOCI 선택 불가"),
            ("trade_no",  "📌 아니오 — 전략적 지분투자, 관계사 출자, 장기 보유 목적",
             "만약 자회사 출자금·관계사 지분·장기 전략 투자처럼 매도가 주목적이 아니라면 이 항목을 선택하세요. → FVOCI 선택권 검토"),
        ],
    },

    # ── STEP A-2: 지분상품 FVOCI 선택권 ─────────────────────────────────────
    "s_eq_fvoci": {
        "tag": "🟠 지분상품",
        "title": "STEP A-2 — OCI(기타포괄손익)에 평가 손익을 넣는 선택을 하시겠습니까?",
        "ref": "§4.1.4 / §5.7.5~5.7.6",
        "ref_key": "§4.1.4",
        "desc": (
            "📌 **이 단계는 '주식 평가 손익을 P&L에 바로 반영할지, OCI(기타포괄손익)에 쌓을지' 선택하는 단계입니다.**\n\n"
            "FVOCI를 선택하면 주가 변동이 당기손익에 영향을 주지 않아 **P&L 변동성을 낮출 수 있습니다.**\n\n"
            "⚠️ **단, 세 가지 중요한 제약이 있습니다:**\n"
            "1. 이 선택은 **지금 이 순간(최초 인식)에만 가능하며 나중에 취소할 수 없습니다(irrevocable).**\n"
            "2. 나중에 이 주식을 팔아도 OCI에 쌓인 손익이 **P&L로 옮겨지지 않습니다(Recycling 금지).**\n"
            "3. **ECL 손상을 인식하지 않습니다** — 주가가 폭락해도 손상차손을 P&L에 계상하지 않음."
        ),
        "helper": None,
        "options": [
            ("fvoci_yes", "✅ 예 — FVOCI 지정 선택 (취소불가 / Recycling 없음 / ECL 미적용)",
             "만약 P&L 변동성을 낮추고 싶고 위 3가지 제약을 모두 감수할 수 있다면 이 항목을 선택하세요. 취소 불가이므로 신중히 결정하세요."),
            ("fvoci_no",  "📊 아니오 — FVPL 유지 (기본값, 모든 변동 P&L 반영)",
             "만약 FVOCI 선택을 하지 않거나 요건을 재검토해야 한다면 이 항목을 선택하세요. → 모든 공정가치 변동을 당기손익으로 인식"),
        ],
    },
}


# ══════════════════════════════════════════════════════════════════════════════
# 5. Streamlit UI
# ══════════════════════════════════════════════════════════════════════════════

def _sidebar_glossary():
    """사이드바 — 실무 용어 사전"""
    with st.sidebar:
        st.markdown("## 📖 실무 용어 사전")
        st.caption("모르는 용어를 클릭해서 확인하세요")
        st.divider()
        terms = [
            ("SPPI", "Solely Payments of Principal and Interest. '원금과 이자만의 지급'. 이자가 오직 대여에 대한 대가(시간가치+신용위험+기본원가+이윤)로만 구성되어 있어야 AC·FVOCI가 가능합니다."),
            ("사업모형 (Business Model)", "금융자산을 어떻게 관리하는지에 대한 경영진의 의사결정 방식. 개별 자산이 아닌 포트폴리오 수준에서 판단하며, '주장'이 아닌 내부 증거(보고체계·보상방식·매도이력)로 확인합니다."),
            ("AC (상각후원가)", "Amortised Cost. 원금+이자를 만기까지 받는 것이 목적인 채무상품에 적용. 유효이자율법으로 측정하며, 공정가치 변동은 장부에 반영하지 않습니다. ECL 손상을 인식합니다."),
            ("FVOCI", "Fair Value through Other Comprehensive Income. 공정가치로 측정하되, 평가손익을 당기손익(P&L)이 아닌 기타포괄손익(OCI)에 반영. 채무상품은 처분 시 Recycling 발생, 지분상품은 Recycling 금지."),
            ("FVPL", "Fair Value through Profit or Loss. 공정가치로 측정하고 모든 변동을 당기손익(P&L)에 반영. 파생상품·단기매매 자산의 기본 측정 방법입니다."),
            ("ECL (기대신용손실)", "Expected Credit Loss. 채무자가 채무를 이행하지 못할 가능성을 고려한 손실 추정치. AC·채무 FVOCI 자산에만 적용되며, FVPL·지분 FVOCI에는 적용하지 않습니다."),
            ("Recycling (재분류)", "OCI에 누적된 손익을 처분 시 당기손익(P&L)으로 옮기는 것. 채무상품 FVOCI는 처분 시 Recycling이 발생하지만, 지분상품 FVOCI는 Recycling이 영구적으로 금지됩니다."),
            ("TVM (화폐의 시간가치)", "Time Value of Money. '지금의 100만원이 1년 후의 100만원보다 가치 있다'는 개념. IFRS 9는 이자가 TVM을 적절히 반영해야 SPPI를 충족한다고 봅니다."),
            ("내재파생상품", "주계약(채권·리스 등) 안에 숨어있는 파생상품. 주계약이 금융자산이면 IFRS 9는 분리를 금지하고 전체를 하나로 SPPI 테스트합니다(§4.3.2)."),
            ("FVO (공정가치 지정선택권)", "Fair Value Option. 회계불일치 해소를 위해 AC/FVOCI 대신 FVPL로 지정하는 취소불가 선택권(§4.1.5)."),
            ("트랑슈 / ABS·CLO", "여러 자산을 묶어 선순위·후순위로 나눈 구조화 금융상품. SPPI 판단 시 '속을 들여다보는(Look-through)' 분석이 필요합니다."),
        ]
        for term, explanation in terms:
            with st.expander(f"**{term}**"):
                st.markdown(explanation)
        st.divider()
        st.caption("기준: K-IFRS 1109호 4장·부록B\nPwC 실무 가이드라인")


def _render_std_expander(ref_key: str, ref_label: str):
    """기준서 조항 expander — 핵심 문구 표시"""
    text = STD_TEXTS.get(ref_key)
    if text:
        with st.expander(f"📘 기준서 핵심 문구 보기 — `{ref_label}`"):
            st.info(text)
    else:
        st.caption(f"📌 기준서 참조: `{ref_label}`")


def _progress_bar(ans: dict):
    """단계 진행 상태 시각화"""
    seq = get_step_sequence(ans)
    step_num = len(seq)

    # 경로별 예상 최대 단계
    at = ans.get("s_asset")
    if at == "deriv":
        total = 1
    elif at == "equity":
        total = 3
    elif at == "hybrid":
        host = ans.get("s_host")
        total = 4 if host == "other_host" else 8
    else:
        total = 8  # 채무상품 최대경로 (SPPI4단계+BM+FVO)

    pct = min(step_num / max(total, 1), 0.97)
    st.progress(pct, text=f"**{step_num}단계** 진행 중 (예상 최대 {total}단계)")


def main():
    st.set_page_config(
        page_title="IFRS 9 금융자산 분류 마법사",
        page_icon="📊",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    # 세션 상태 초기화
    for key, default in [("answers", {}), ("history", []), ("show_result", False)]:
        if key not in st.session_state:
            st.session_state[key] = default

    # 전역 스타일
    st.markdown("""
    <style>
    .stButton > button {
        border-radius: 10px;
        border: 1.5px solid #D0D5DD;
        background: #FAFAFA;
        width: 100%;
        text-align: left;
        padding: 0.65rem 1rem;
        font-size: 0.93rem;
        line-height: 1.55;
        transition: all 0.15s;
        white-space: normal;
    }
    .stButton > button:hover { border-color: #1D9E75; background: #E9FBF4; }
    [data-testid="stSidebar"] { background: #F8F9FA; }

    /* ── 파일 업로더 드롭존 영역 ── */
    [data-testid="stFileUploader"] {
        background: #FFFFFF !important;
        border-radius: 10px !important;
    }
    [data-testid="stFileUploaderDropzone"] {
        background: #FFFFFF !important;
        border: 2px dashed #94A3B8 !important;
        border-radius: 10px !important;
        padding: 1rem !important;
        transition: border-color 0.2s ease !important;
    }
    [data-testid="stFileUploaderDropzone"]:hover {
        border-color: #1E3A8A !important;
        background: #EFF6FF !important;
    }
    [data-testid="stFileUploaderDropzoneInstructions"] {
        color: #475569 !important;
    }
    [data-testid="stFileUploaderDropzoneInstructions"] span,
    [data-testid="stFileUploaderDropzoneInstructions"] small {
        color: #64748B !important;
    }

    /* ── Browse files 버튼 ── */
    [data-testid="stFileUploaderDropzone"] button,
    [data-testid="stFileUploadButton"],
    [data-testid="stFileUploaderDropzone"] > div > button,
    [data-testid="stFileUploaderDropzone"] span > button,
    [data-testid="stFileUploaderDropzone"] label > div > button {
        background-color: #1E3A8A !important;
        color: #FFFFFF !important;
        border: none !important;
        border-radius: 8px !important;
        padding: 0.4rem 1rem !important;
        font-size: 0.85rem !important;
        font-weight: 600 !important;
        cursor: pointer !important;
        transition: background-color 0.2s ease, box-shadow 0.2s ease !important;
        text-align: center !important;
        width: auto !important;
    }
    [data-testid="stFileUploaderDropzone"] button:hover,
    [data-testid="stFileUploadButton"]:hover,
    [data-testid="stFileUploaderDropzone"] > div > button:hover {
        background-color: #1E40AF !important;
        box-shadow: 0 4px 12px rgba(30,58,138,0.35) !important;
    }

    /* ── 업로드된 파일명 표시 ── */
    [data-testid="stFileUploaderFile"],
    [data-testid="stFileUploaderFile"] span,
    [data-testid="stFileUploaderFileName"],
    [data-testid="uploadedFileData"],
    [data-testid="uploadedFileData"] span {
        color: #1E293B !important;
        font-size: 0.85rem !important;
        font-weight: 500 !important;
        background: #F8FAFC !important;
    }
    [data-testid="stFileUploaderFile"] {
        background: #F8FAFC !important;
        border: 1px solid #E2E8F0 !important;
        border-radius: 8px !important;
        padding: 0.4rem 0.75rem !important;
        margin-top: 0.5rem !important;
    }

    /* ── 파일 삭제(X) 버튼 ── */
    [data-testid="stFileUploaderFile"] button,
    [data-testid="stFileUploaderDeleteBtn"] {
        color: #64748B !important;
        background: transparent !important;
        border: none !important;
        width: auto !important;
        padding: 0.2rem !important;
    }
    [data-testid="stFileUploaderFile"] button:hover,
    [data-testid="stFileUploaderDeleteBtn"]:hover {
        color: #DC2626 !important;
        background: #FEF2F2 !important;
    }
    </style>
    """, unsafe_allow_html=True)

    # 사이드바
    _sidebar_glossary()

    # 메인 헤더
    st.title("📊 IFRS 9 금융자산 분류 마법사")
    st.markdown(
        "> 기준서 K-IFRS 1109호 4장 · 부록B · PwC 실무 가이드라인 기반  "
        "| FVPL · AC · FVOCI | 모든 결과에 **§ 조항 번호** 포함"
    )
    st.divider()

    ans = st.session_state.answers

    # 결과 화면
    if st.session_state.show_result:
        _render_result(ans)
        return

    # ── 진행 중 단계 ──────────────────────────────────────────────────────────
    seq = get_step_sequence(ans)
    current_step_id = seq[-1]

    if is_terminal(ans):
        st.session_state.show_result = True
        st.rerun()

    # 진행 상태 바
    _progress_bar(ans)
    st.write("")

    # 현재 스텝
    step = STEP_DEFS.get(current_step_id)
    if not step:
        st.error("알 수 없는 단계입니다. 처음부터 다시 시작하세요.")
        _reset()
        return

    # 태그 뱃지
    if step["tag"]:
        st.markdown(
            f'<span style="background:#EEF2FF;color:#3730A3;padding:4px 12px;'
            f'border-radius:6px;font-size:0.8rem;font-weight:700">{step["tag"]}</span>',
            unsafe_allow_html=True,
        )
        st.write("")

    # 제목
    st.subheader(step["title"])

    # 기준서 expander
    _render_std_expander(step.get("ref_key", ""), step.get("ref", ""))
    st.write("")

    # 설명
    st.markdown(step["desc"])
    st.write("")

    # Helper (도우미 박스)
    if step["helper"]:
        with st.expander(step["helper"]["title"], expanded=True):
            st.markdown(step["helper"]["body"])
        st.write("")

    # 선택지 버튼
    chosen = ans.get(current_step_id)
    for val, label, sub in step["options"]:
        is_sel = chosen == val
        full_label = f"{'✔ ' if is_sel else ''}{label}\n\n*{sub}*"
        if st.button(full_label, key=f"btn_{current_step_id}_{val}",
                     type="primary" if is_sel else "secondary"):
            _pick(current_step_id, val)

    st.divider()

    # 네비게이션
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
            st.button("다음 →", disabled=True, use_container_width=True,
                      help="먼저 위의 선택지 중 하나를 클릭하세요")
    with col_reset:
        if st.button("🔄 처음부터", use_container_width=True):
            _reset()

    # 입력 경로 미리보기
    if ans:
        with st.expander("🗺️ 지금까지 입력한 경로 확인", expanded=False):
            for k, v in ans.items():
                st.code(f"{k}  →  {v}", language=None)


# ══════════════════════════════════════════════════════════════════════════════
# 6. 결과 화면 렌더링
# ══════════════════════════════════════════════════════════════════════════════

def _render_result(ans: dict):
    r = compute_result(ans)

    st.progress(1.0, text="✅ 분류 완료!")
    st.write("")

    # ── 분류 결과 배너 ────────────────────────────────────────────────────────
    color_cfg = {
        "green":  ("#E1F5EE", "#085041", "#0F6E56", "✅"),
        "blue":   ("#E6F1FB", "#0C447C", "#185FA5", "🔵"),
        "orange": ("#FAEEDA", "#633806", "#854F0B", "🟡"),
        "red":    ("#FCEBEB", "#791F1F", "#A32D2D", "🔴"),
    }
    bg, fg, border, icon = color_cfg.get(r["color"], ("#F5F5F5", "#333", "#999", "📋"))

    st.markdown(
        f'<div style="background:{bg};border:2px solid {border};border-radius:14px;'
        f'padding:1.4rem 1.8rem;margin-bottom:1.2rem">'
        f'<div style="font-size:1.6rem;font-weight:700;color:{fg};margin-bottom:.4rem">'
        f'{icon} {r["label"]}</div>'
        f'<div style="font-size:0.93rem;color:{fg};line-height:1.7">{r["reason"]}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )

    # ── 적용 기준서 조항 ──────────────────────────────────────────────────────
    st.markdown("### 📚 적용 기준서 조항")
    ref_cols = st.columns(min(len(r["refs"]), 5))
    for i, ref in enumerate(r["refs"]):
        ref_cols[i % 5].code(ref, language=None)

    st.divider()

    # ── 회계처리 요약표 ───────────────────────────────────────────────────────
    st.markdown("### 📋 회계처리 요약표")
    cls = r["classification"]
    table_data = _build_accounting_table(cls, r)
    st.markdown(table_data, unsafe_allow_html=False)

    st.divider()

    # ── ECL · Recycling 알림 ─────────────────────────────────────────────────
    st.markdown("### ⚙️ 추가 처리 사항")

    if r["ecl"]:
        st.success(
            "**✅ ECL(기대신용손실) 손상 모형 적용 대상**\n\n"
            "매 보고기간 말에 기대신용손실(ECL)을 산정하고 손실충당금을 인식해야 합니다.  \n"
            "신용위험이 유의적으로 증가한 경우 전체기간 ECL, 그렇지 않으면 12개월 ECL을 적용합니다. [§5.5]",
        )
    else:
        st.info("**ℹ️ ECL(손상) 적용 없음** — 이 분류에는 손상 인식 규정이 적용되지 않습니다.")

    if r["recycling"]:
        st.warning(
            "**⚠️ Recycling(재분류) 발생 — 채무상품 FVOCI**\n\n"
            "처분·제거 시 OCI에 누적된 평가손익이 당기손익(P&L)으로 재분류됩니다. [§5.7.2]  \n"
            "지분상품 FVOCI(Recycling 금지)와의 핵심 차이입니다. 처분 시 세금 효과도 함께 검토하세요.",
        )
    elif r.get("recycling_note"):
        st.warning(f"**⚠️ Recycling 관련 주의사항**\n\n{r['recycling_note']}")
    else:
        st.info("**ℹ️ Recycling 없음** — OCI 잔액은 처분 후에도 당기손익으로 이전되지 않습니다.")

    if r["warning"]:
        st.warning(f"⚠️ **주의사항**\n\n{r['warning']}")

    st.divider()

    # ── SPPI 사례 JSON ────────────────────────────────────────────────────────
    case_key = r.get("case_key")
    if case_key and case_key in SPPI_CASES_DICT:
        case = SPPI_CASES_DICT[case_key]
        st.markdown("### 🗂️ 유사 사례 참고 (SPPI_CASES_DICT)")
        col_a, col_b = st.columns([1, 1])
        with col_a:
            st.markdown(f"**상품**: {case['label']}")
            st.markdown(f"**유형**: `{case['category']}`")
            st.markdown(f"**SPPI 실패**: `{case['sppi_fail']}`")
            st.markdown(f"**기준서**: {', '.join(case['standard_ref'])}")
        with col_b:
            st.markdown(f"**불충족 이유**: {case['reason']}")
            st.markdown(f"**판단 기준**: {case['judgment_criteria']}")
        with st.expander("📄 JSON 원본 보기 (DB 확장용)", expanded=False):
            st.json(case)
        st.divider()

    # ── 입력 경로 요약 ────────────────────────────────────────────────────────
    st.markdown("### 🗺️ 입력 경로 요약")
    with st.expander("전체 답변 이력 보기", expanded=False):
        for k, v in ans.items():
            st.code(f"{k:20s}  →  {v}", language=None)

    # ── 버튼 ──────────────────────────────────────────────────────────────────
    st.write("")
    c1, c2, c3 = st.columns(3)
    with c1:
        if st.button("← 이전 단계로", use_container_width=True):
            st.session_state.show_result = False
            seq = get_step_sequence(ans)
            if seq:
                ans.pop(seq[-1], None)
            st.rerun()
    with c2:
        if st.button("🔄 처음부터 다시", type="primary", use_container_width=True):
            _reset()
    with c3:
        if st.button("📋 텍스트 리포트 생성", use_container_width=True):
            _show_text_report(r, ans)


def _build_accounting_table(cls: str, r: dict) -> str:
    """분류별 회계처리 요약 마크다운 표 생성"""

    rows_by_cls = {
        "AC": [
            ("최초 인식", "공정가치 + 거래원가"),
            ("후속 측정", "유효이자율법 상각후원가"),
            ("이자수익 반영", "당기손익 (P&L) — 유효이자율법"),
            ("평가손익 반영", "해당 없음 (공정가치 변동 미반영)"),
            ("ECL 손상 인식", "✅ 적용 — 12개월 또는 전체기간 ECL [§5.5]"),
            ("처분 손익", "당기손익 (P&L)"),
            ("OCI Recycling", "해당 없음"),
        ],
        "FVOCI_DEBT": [
            ("최초 인식", "공정가치"),
            ("후속 측정", "공정가치"),
            ("이자수익 반영", "당기손익 (P&L) — 유효이자율법"),
            ("평가손익 반영", "기타포괄손익 (OCI)"),
            ("ECL 손상 인식", "✅ 적용 — P&L에 반영 (OCI 조정 포함) [§5.5]"),
            ("처분 시 OCI 재분류", "✅ P&L로 Recycling 발생 [§5.7.2]"),
            ("OCI Recycling", "✅ 처분 시 발생"),
        ],
        "FVOCI_EQ": [
            ("최초 인식", "공정가치"),
            ("후속 측정", "공정가치"),
            ("배당 반영", "당기손익 (P&L) [§B5.7.1]"),
            ("평가손익 반영", "기타포괄손익 (OCI)"),
            ("ECL 손상 인식", "❌ 미적용"),
            ("처분 시 OCI 재분류", "❌ P&L 재분류 금지 — 자본 내 이전만 허용 [§5.7.5]"),
            ("OCI Recycling", "❌ 금지 (지분상품 FVOCI)"),
        ],
        "FVPL": [
            ("최초 인식", "공정가치"),
            ("후속 측정", "공정가치"),
            ("이자/배당 반영", "당기손익 (P&L)"),
            ("평가손익 반영", "당기손익 (P&L) — 전액"),
            ("ECL 손상 인식", "❌ 미적용"),
            ("처분 손익", "당기손익 (P&L)"),
            ("OCI Recycling", "해당 없음"),
        ],
    }

    if cls == "AC":
        rows = rows_by_cls["AC"]
    elif cls == "FVOCI":
        # 지분인지 채무인지 구분
        if "지분" in r["label"]:
            rows = rows_by_cls["FVOCI_EQ"]
        else:
            rows = rows_by_cls["FVOCI_DEBT"]
    else:
        rows = rows_by_cls["FVPL"]

    lines = ["| 항목 | 내용 |", "|---|---|"]
    for item, content in rows:
        lines.append(f"| {item} | {content} |")

    return "\n".join(lines)


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
        lines.append(f"  {k}: {v}")
    lines += ["", "=" * 65]
    st.code("\n".join(lines), language=None)


# ══════════════════════════════════════════════════════════════════════════════
# 헬퍼 함수
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
    for sid in seq[seq.index(prev_id):]:
        st.session_state.answers.pop(sid, None)
    st.session_state.show_result = False
    st.rerun()


def _reset():
    st.session_state.answers = {}
    st.session_state.history = []
    st.session_state.show_result = False
    st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    main()
