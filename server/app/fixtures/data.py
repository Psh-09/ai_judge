from pathlib import Path

from app.services.code import compute_code_hash

_FIXTURE_DIR = Path(__file__).resolve().parent
SAMPLE_LANGUAGE = "python"
SAMPLE_CODE = (_FIXTURE_DIR / "sample_user_handler.py").read_text(encoding="utf-8")
SAMPLE_CODE_HASH = compute_code_hash(SAMPLE_CODE, SAMPLE_LANGUAGE)

_PROSECUTION_RESPONSE = {
    "charges": [
        {
            "rule_id": "SEC-003",
            "evidence_lines": [42, 42],
            "charged_severity": "HIGH",
            "severity_adjusted": False,
            "severity_reason": None,
            "description": "사용자 입력이 문자열 결합으로 SQL 쿼리에 직접 삽입된다.",
        },
        {
            "rule_id": "STRUCT-001",
            "evidence_lines": [88, 140],
            "charged_severity": "MEDIUM",
            "severity_adjusted": False,
            "severity_reason": None,
            "description": "parse_and_save 함수가 파싱·검증·저장을 함께 처리한다.",
        },
        {
            "rule_id": "ERR-002",
            "evidence_lines": [155, 158],
            "charged_severity": "HIGH",
            "severity_adjusted": True,
            "severity_reason": "최상위 예외로 다수 사용자 처리 실패가 조용히 은폐될 위험이 커서 상향함",
            "description": "최상위 예외 타입을 통째로 잡아 예상하지 못한 오류까지 삼킨다.",
        },
        {
            "rule_id": "NAMING-002",
            "evidence_lines": [17, 17],
            "charged_severity": "LOW",
            "severity_adjusted": False,
            "severity_reason": None,
            "description": "한두 글자로 축약되어 역할을 알 수 없는 변수명이다.",
        },
        {
            "rule_id": "STYLE-001",
            "evidence_lines": [63, 63],
            "charged_severity": "LOW",
            "severity_adjusted": False,
            "severity_reason": None,
            "description": "의미를 알 수 없는 숫자 리터럴이 로직에 직접 등장한다.",
        },
        # 아래 2건은 서버 검증이 실제로 폐기하는 것을 보여주기 위한 표본이다 (데모용).
        {
            "rule_id": "FAKE-999",  # 법전에 없는 rule_id -> 폐기
            "evidence_lines": [10, 10],
            "charged_severity": "MEDIUM",
            "severity_adjusted": False,
            "severity_reason": None,
            "description": "존재하지 않는 조항으로 기소한 표본(서버가 폐기해야 함).",
        },
        {
            "rule_id": "PERF-001",  # 라인 범위가 total_lines(187)를 벗어남 -> 폐기
            "evidence_lines": [500, 510],
            "charged_severity": "MEDIUM",
            "severity_adjusted": False,
            "severity_reason": None,
            "description": "존재하지 않는 라인을 지목한 표본(서버가 폐기해야 함).",
        },
    ]
}

_DEFENSE_RESPONSE = {
    "pleas": [
        {
            "charge_index": 0,
            "plea": "DENY",
            "argument": "이 호출은 내부 관리자 스크립트에서만 실행되므로 외부 공격 표면이 아니다.",
        },
        {
            "charge_index": 1,
            "plea": "DENY",
            "argument": "레거시 호환을 위해 하나의 트랜잭션으로 묶어야 했다.",
        },
        {
            "charge_index": 2,
            "plea": "DENY",
            "argument": "해당 구간에 실패를 기록하는 로깅이 포함되어 있다.",
        },
        {
            "charge_index": 3,
            "plea": "DENY",
            "argument": "이 변수는 선언 후 3줄 내에서만 사용되는 지역 변수다.",
        },
        {
            "charge_index": 4,
            "plea": "DENY",
            "argument": "상수 바로 위 주석에 의미가 설명되어 있다.",
        },
    ]
}

_JUDGMENT_RESPONSE = {
    "opinion": (
        "전반적으로 동작하는 코드이나, 입력 검증과 함수 단위 책임 분리가 미흡하다. "
        "보안 관련 지적 1건은 즉시 수정이 필요하다."
    ),
    "rebuttal_accepted": None,
    "verdicts": [
        {
            "charge_index": 0,
            "verdict": "SUSTAINED",
            "final_severity": "HIGH",
            "reasoning": (
                "사용자 입력이 검증 없이 쿼리에 결합된다. 변론의 '내부 스크립트' 주장은 "
                "입력 경로가 외부에 열려 있어 성립하지 않는다."
            ),
        },
        {
            "charge_index": 1,
            "verdict": "SUSTAINED",
            "final_severity": "MEDIUM",
            "reasoning": "단일 함수가 파싱·검증·저장을 함께 처리한다.",
        },
        {
            "charge_index": 2,
            "verdict": "REDUCED",
            "final_severity": "MEDIUM",
            "reasoning": "except 범위가 넓은 것은 사실이나, 로깅이 포함되어 실패가 은폐되지는 않는다.",
        },
        {
            "charge_index": 3,
            "verdict": "DISMISSED",
            "final_severity": None,
            "reasoning": "변론 인정. 스코프가 3줄이라 조항 적용이 과하다.",
        },
        {
            "charge_index": 4,
            "verdict": "DISMISSED",
            "final_severity": None,
            "reasoning": "상수의 의미가 인접 주석으로 설명되어 있어 가독성 저해가 없다.",
        },
    ],
    "sentences": [
        {
            "charge_index": 0,
            "task": "42번 줄 쿼리를 파라미터 바인딩으로 교체",
            "target_lines": [42, 42],
            "effort": "SMALL",
            "effort_adjusted": False,
            "effort_reason": None,
            "rationale": "파라미터 바인딩으로 교체하면 SQL 인젝션 경로가 닫힌다.",
        },
        {
            "charge_index": 1,
            "task": "parse_and_save()를 파싱·검증·저장 세 함수로 분리",
            "target_lines": [88, 140],
            "effort": "LARGE",
            "effort_adjusted": False,
            "effort_reason": None,
            "rationale": "책임을 분리하면 각 단계를 독립적으로 테스트할 수 있다.",
        },
        {
            "charge_index": 2,
            "task": "except 절을 예상 예외 타입으로 좁힘",
            "target_lines": [155, 158],
            "effort": "MEDIUM",
            "effort_adjusted": False,
            "effort_reason": None,
            "rationale": "예상 가능한 예외만 잡으면 나머지 오류가 은폐되지 않는다.",
        },
    ],
}

# 항소 데모용: 원심에서 기각됐던 NAMING-002(charge_index 3)가 재심에서 채택된다.
# 나머지 charge는 원심과 동일한 판정을 유지해, "일부만 뒤집힌" 현실적인 재심을 보여준다.
_REJUDGMENT_RESPONSE = {
    "opinion": (
        "항소 사유를 검토한 결과, 축약 변수명 지적은 재심에서 다시 인정한다. "
        "나머지 지적에 대한 판단은 원심과 동일하게 유지한다."
    ),
    "rebuttal_accepted": True,
    "verdicts": [
        {
            "charge_index": 0,
            "verdict": "SUSTAINED",
            "final_severity": "HIGH",
            "reasoning": (
                "사용자 입력이 검증 없이 쿼리에 결합된다. 변론의 '내부 스크립트' 주장은 "
                "입력 경로가 외부에 열려 있어 성립하지 않는다."
            ),
        },
        {
            "charge_index": 1,
            "verdict": "SUSTAINED",
            "final_severity": "MEDIUM",
            "reasoning": "단일 함수가 파싱·검증·저장을 함께 처리한다.",
        },
        {
            "charge_index": 2,
            "verdict": "REDUCED",
            "final_severity": "MEDIUM",
            "reasoning": "except 범위가 넓은 것은 사실이나, 로깅이 포함되어 실패가 은폐되지는 않는다.",
        },
        {
            "charge_index": 3,
            "verdict": "SUSTAINED",
            "final_severity": "LOW",
            "reasoning": (
                "항소인은 스코프가 짧다고 주장하나, 같은 축약명이 여러 함수에서 재사용되며 "
                "역할을 알 수 없게 만든다. 원심 기각을 재심에서 채택으로 변경한다."
            ),
        },
        {
            "charge_index": 4,
            "verdict": "DISMISSED",
            "final_severity": None,
            "reasoning": "상수의 의미가 인접 주석으로 설명되어 있어 가독성 저해가 없다.",
        },
    ],
    "sentences": [
        {
            "charge_index": 0,
            "task": "42번 줄 쿼리를 파라미터 바인딩으로 교체",
            "target_lines": [42, 42],
            "effort": "SMALL",
            "effort_adjusted": False,
            "effort_reason": None,
            "rationale": "파라미터 바인딩으로 교체하면 SQL 인젝션 경로가 닫힌다.",
        },
        {
            "charge_index": 1,
            "task": "parse_and_save()를 파싱·검증·저장 세 함수로 분리",
            "target_lines": [88, 140],
            "effort": "LARGE",
            "effort_adjusted": False,
            "effort_reason": None,
            "rationale": "책임을 분리하면 각 단계를 독립적으로 테스트할 수 있다.",
        },
        {
            "charge_index": 2,
            "task": "except 절을 예상 예외 타입으로 좁힘",
            "target_lines": [155, 158],
            "effort": "MEDIUM",
            "effort_adjusted": False,
            "effort_reason": None,
            "rationale": "예상 가능한 예외만 잡으면 나머지 오류가 은폐되지 않는다.",
        },
        {
            "charge_index": 3,
            "task": "nm 변수명을 user_display_name 등 의미 있는 이름으로 변경",
            "target_lines": [17, 17],
            "effort": "SMALL",
            "effort_adjusted": False,
            "effort_reason": None,
            "rationale": "의미 있는 이름으로 바꾸면 재사용 시 역할을 다시 추적할 필요가 없다.",
        },
    ],
}

FIXTURES: dict[str, dict[str, dict]] = {
    SAMPLE_CODE_HASH: {
        "prosecution": _PROSECUTION_RESPONSE,
        "defense": _DEFENSE_RESPONSE,
        "judgment": _JUDGMENT_RESPONSE,
        "rejudgment": _REJUDGMENT_RESPONSE,
    }
}
