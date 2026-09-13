# 대립형 코드 리뷰 서비스 설계 문서

> 이 문서는 설계 브레인스토밍 시점의 기록이며, 이후 변경된 결정은 반영되어 있지 않다. 최종 설계는 `docs/plans/plan.md`, API 스키마는 `openapi.yaml`을 본다. 대표적으로 인증 방식(응답 바디 토큰 → httpOnly 쿠키)과 법전 조항 구성이 이후 변경되었다.

- 작성일: 2026-09-07
- 범위: 학교 과제 규모 개인 프로젝트
- 스택: Next.js(클라이언트) / FastAPI(서버) / PostgreSQL

## 1. 목표 / 비목표

### 목표

- 사용자가 코드를 붙여넣으면 검사(기소) → 변호인(반박) → 판사(판결+형량) 3단계를 순차 실행하는 대립형 코드 리뷰 서비스를 만든다.
- 기소는 사전 정의된 법전(rule catalog)의 rule_id로만 가능하고, 모든 기소는 코드 라인 범위 증거를 지목하며 서버가 실제 라인 수와 대조해 검증한다.
- 각 단계 출력은 JSON 스키마로 강제하고 서버가 검증하며, 실패 시 재시도 상한을 둔다.
- 형량은 실행 가능한 리팩토링 과제 체크리스트로 산출된다.
- 사용자는 확정 판결에 대해 1회 항소할 수 있고, 재심은 판사 단계만 재실행한다.
- 과거 판결은 판례로 축적되어 이후 판결에 참고된다.

### 비목표

- 코드 실행/테스트
- 자동 PR 생성
- 레포지토리 전체 분석(다중 파일, 파일 간 의존성 분석)은 비목표다. GitHub 링크 제출(§8.1)은 저장소 내 단일 파일을 지정하는 방식이며, 여전히 한 번에 한 파일만 심사한다. 링크 제출과 레포 전체 분석은 다른 것이다
- 실시간 협업
- 기소 단위 부분 항소(v1은 사건 전체 재심만)
- 소셜 로그인, 이메일 인증 메일 발송
- 비밀번호 재설정/계정 복구 — 이메일 발송이 비목표이므로 링크 기반 재설정도 함께 제외한다. 보안 질문 방식은 답변이 추측·조사로 획득 가능해 비밀번호보다 약한 인증 수단이 되므로 대안으로 채택하지 않는다. 이메일 발송이 가능해지는 시점에 링크 기반 재설정으로 구현한다
- 비공개(private) GitHub 저장소 지원 — OAuth 범위 확대를 피하기 위해 public 저장소만 지원(§8.1)
- 법전 관리자 CRUD UI(법전은 배포 시 파일 수정으로 관리)

## 2. 아키텍처 개요

```
[Next.js Client] --REST(JWT)--> [FastAPI]
                                    |
                                    | INSERT case (status=QUEUED_PROSECUTION)
                                    v
                              [PostgreSQL]  <---- SELECT ... FOR UPDATE SKIP LOCKED (2초 폴링)
                                    ^
                                    |
                            [Worker 프로세스 (N개, 동일 코드)]
                                    |
                                    v
                          [LLM API (단일 모델, 역할별 프롬프트)]

Client: GET /cases/{id}/progress 를 2초 간격 폴링, 종료 상태(SENTENCED/DISMISSED/FAILED)면 중단
```

- 별도 메시지 브로커(Redis/Celery 등) 없이 PostgreSQL 자체를 큐로 사용한다. 학교 과제 규모에 인프라를 늘리지 않기 위함.
- 워커는 FastAPI 앱과 코드베이스를 공유하는 별도 프로세스로 실행된다.
- **작업 단위는 "사건"이 아니라 "스테이지" 하나**다. 워커는 한 번 픽업하면 검사/변호/판사/재심 중 한 스테이지만 처리하고 상태를 커밋한 뒤 놓아준다. 3단계를 한 트랜잭션으로 묶으면 수십 초 락이 걸리고, 중간에 죽으면 복구 지점을 알 수 없기 때문이다.
- **워커 하트비트 + 조건부 커밋**: 워커는 LLM 호출 전후로 자신이 잠근 행의 `locked_at`을 갱신한다(별도 하트비트 인프라 없이 UPDATE 두 번). 스테이지 완료 커밋은 `UPDATE ... WHERE locked_by = :worker_id AND status = :expected_status`처럼 조건부로 실행해, 이미 다른 워커가 먼저 끝내 `status`가 바뀐 뒤라면 0행 적용되어 조용히 버려진다(에러 아님, 이중 커밋만 방지). `locked_at` 타임아웃은 5분이 아니라 **15분**으로 잡는다(정상 LLM 호출은 수십 초지만, 5분은 "죽었다"고 단정하기엔 짧아 정상 처리 중에 재획득이 발생할 위험이 있었음). 0행 적용 발생률은 `stale_commit_rate` 지표로 집계(§11).
- LLM 구성: 검사/변호인/판사 3역할 모두 **동일 모델 + 역할별 프롬프트**로 처리한다(비용 예측 용이, 구현 단순).
- 인증 토큰은 **httpOnly + Secure + SameSite=Lax 쿠키**로 저장한다(JS에서 접근 불가). localStorage 등 JS 접근 가능한 저장소는 XSS로 세션이 탈취될 경우의 파급 범위(예: 향후 GitHub 등 외부 저장소 연동을 지원하게 되면 사용자의 저장소 접근권까지 위협받음, §8.1)를 고려해 배제한다. 상태 변경 요청(POST/PATCH)은 CSRF 대응으로 커스텀 헤더 검증 또는 Double Submit Cookie 패턴 중 하나를 구현 단계에서 택일한다.

## 3. 사건 상태머신

`status` 컬럼 하나로 "다음에 할 일"과 "지금 진행 중인 일"을 함께 표현한다(`QUEUED_*` = 픽업 대기, 동사형 = 워커가 잠금 보유 중).

| 상태                 | 의미                                                                      | 잠금 컬럼            |
| -------------------- | ------------------------------------------------------------------------- | -------------------- |
| `QUEUED_PROSECUTION` | 제출 직후, 검사 대기                                                      | -                    |
| `PROSECUTING`        | 워커가 검사 단계 처리 중                                                  | locked_at, locked_by |
| `QUEUED_DEFENSE`     | 검사 완료, 변호인 대기                                                    | -                    |
| `DEFENDING`          | 워커가 변호 단계 처리 중                                                  | locked_at, locked_by |
| `QUEUED_JUDGMENT`    | 변호 완료, 판사 대기                                                      | -                    |
| `JUDGING`            | 워커가 판결 처리 중                                                       | locked_at, locked_by |
| `SENTENCED`          | 판결 확정 (revision 0 또는 1)                                             | -                    |
| `DISMISSED`          | 검사 유효 기소 0건으로 무혐의 종결(변호/판사 스테이지 자체를 거치지 않음) | -                    |
| `QUEUED_REJUDGMENT`  | 항소 접수, 재심 대기                                                      | -                    |
| `REJUDGING`          | 워커가 재심(판사만) 처리 중                                               | locked_at, locked_by |
| `FAILED`             | 재시도 상한 초과로 종결                                                   | -                    |

`DISMISSED`는 `SENTENCED`와 별개의 종료 상태다. 판결(`judgments`) 자체가 존재하지 않으므로 항소 대상이 아니고(`appeal_used`/`revision`은 의미 없음, 기본값 그대로 방치), 판례로도 적재되지 않는다.

### 전이표

| From                                | 트리거                                    | To                                          | 비고                                                                                                                         |
| ----------------------------------- | ----------------------------------------- | ------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------- |
| QUEUED_PROSECUTION                  | 워커 폴링 픽업                            | PROSECUTING                                 | `SELECT ... FOR UPDATE SKIP LOCKED`, locked_at/locked_by 기록                                                                |
| PROSECUTING                         | 검증 통과, 살아남은 charge 0건            | **DISMISSED**                               | 변호/판사 스테이지를 거치지 않고 즉시 종결(불필요한 LLM 호출 절약). 무혐의 통지만 표시                                       |
| PROSECUTING                         | 검증 통과, 살아남은 charge 1건 이상       | QUEUED_DEFENSE                              |                                                                                                                              |
| PROSECUTING                         | 검증 실패, `prosecution_attempts` < 상한  | QUEUED_PROSECUTION                          | attempts+1                                                                                                                   |
| PROSECUTING                         | attempts == 상한                          | FAILED                                      | `failed_stage=PROSECUTION`                                                                                                   |
| PROSECUTING                         | `locked_at` 15분 초과(워커 크래시)        | QUEUED_PROSECUTION                          | 다른 워커가 재수거, attempts는 유지, 완료된 스테이지는 재실행하지 않음                                                       |
| QUEUED_DEFENSE                      | 워커 픽업                                 | DEFENDING                                   |                                                                                                                              |
| DEFENDING                           | 검증 통과 / 실패·재시도 / 상한초과        | QUEUED_JUDGMENT / QUEUED_DEFENSE / FAILED   | 위와 동일 패턴(`defense_attempts`)                                                                                           |
| QUEUED_JUDGMENT                     | 워커 픽업                                 | JUDGING                                     |                                                                                                                              |
| JUDGING                             | 검증 통과 / 실패·재시도 / 상한초과        | SENTENCED(rev=0) / QUEUED_JUDGMENT / FAILED | 위와 동일 패턴(`judgment_attempts`)                                                                                          |
| SENTENCED(rev=0, appeal_used=false) | 사용자 항소 (rebuttal≥20자)               | QUEUED_REJUDGMENT                           | `appeal_used=true` 즉시 확정(성공/실패 무관, 소진)                                                                           |
| SENTENCED(appeal_used=true)         | 재항소 시도                               | -                                           | `409` (전이 없음)                                                                                                            |
| QUEUED_REJUDGMENT                   | 워커 픽업                                 | REJUDGING                                   | 검사/변호 결과는 재사용, 판례만 새로 조회                                                                                    |
| REJUDGING                           | 검증 통과                                 | SENTENCED(revision=1)                       | 원심(rev=0) `judgments.is_overturned=true` 전환, 신규 판례로 revision=1 적재                                                 |
| REJUDGING                           | 실패·재시도, `rejudgment_attempts` < 상한 | QUEUED_REJUDGMENT                           | attempts+1                                                                                                                   |
| REJUDGING                           | attempts == 상한                          | **SENTENCED(revision=0 유지)**              | `rejudgment_failed_reason`/`rejudgment_failed_at` 기록, 원심 유효 유지, `appeal_used`는 이미 true(소진), 판례/캐시 대상 아님 |
| FAILED                              | (전이 없음, 종결)                         | -                                           | 사용자는 `POST /cases`로 재제출(새 사건 생성)                                                                                |

### 화면 표시 매핑 (`revision` × `appeal_used`)

| revision | appeal_used | 표시                  |
| -------- | ----------- | --------------------- |
| 0        | false       | 판결 확정 (항소 가능) |
| 0        | true        | 원심 확정 (재심 실패) |
| 1        | true        | 재심 확정 (최종)      |

## 4. 단계별 JSON 스키마 & 서버 검증

### 4.1 검사(Prosecution) 출력

```json
{
  "charges": [
    {
      "rule_id": "SECURITY-001",
      "evidence_lines": [42, 58],
      "charged_severity": "HIGH",
      "severity_adjusted": true,
      "severity_reason": "사용자 입력이 검증 없이 쿼리에 직접 들어감",
      "description": "..."
    }
  ]
}
```

`charge_index`는 출력에 없다. 서버가 검증 후 부여한다.

서버 처리 순서(각 charge 단위):

1. `rule_id`가 활성 법전에 존재하고 `language` 일치(또는 언어무관 공통 조항) → 아니면 **charge 완전 폐기**
2. `evidence_lines`가 `[1, 실제라인수]` 범위 내, start ≤ end → 아니면 **charge 완전 폐기**
3. `charged_severity`가 `default_severity` ±1단계를 벗어남 → **charge 완전 폐기** (죄목을 잘못 고른 것과 구별 불가능하고, 다른 기소가 남아 결과가 비지 않으므로 폐기)
4. `severity_adjusted=true`인데 `severity_reason`이 없거나 부실(10자 미만) → **charge는 유지**, `severity_adjusted=false`로 되돌리고 `charged_severity=default_severity`로 리셋(조정만 무효화)
5. **사건당 기소 건수 상한(12건)**: 1~4단계를 통과해 살아남은 charge가 12건을 초과하면 `charged_severity` 높은 순으로 상위 12건만 채택하고 나머지는 폐기한다. 이 절단은 라인/법전 검증 **이후**에 수행한다(무효 기소가 상한 자리를 차지하지 않게). 절단이 발생하면 `cases.charges_truncated=true`를 기록한다 — 지표(§11)로만 관찰하지 않고 상한 자체를 두는 이유는, 상한이 없으면 검사가 수십 건을 기소하는 사건이 실제로 생겨 판사 프롬프트가 부풀고 verdict 누락(§4.3)과 재시도 비용이 함께 폭증하기 때문이다. 지표는 사후 관측일 뿐 예방책이 아니다
6. 살아남은(그리고 상한 내로 절단된) charge에 `charge_index`를 0부터 연속 재부여(원본 순서는 내부 `raw_index`로만 보관)
7. JSON 형태 자체가 스키마를 안 갖춘 경우에만 스테이지 재시도(`prosecution_attempts`)
8. 살아남은 charge가 0건이면 변호/판사 스테이지로 넘기지 않고 사건을 즉시 `DISMISSED`로 종결한다(§3 전이표 참고)

### 4.2 변호인(Defense) 출력

```json
{ "pleas": [{ "charge_index": 0, "plea": "DENY", "argument": "..." }] }
```

- `plea` ∈ `ADMIT / DENY / NO_RESPONSE`
- 존재하지 않는 `charge_index` 참조 → 해당 항목 폐기 / 중복 참조 → 첫 항목만 인정
- 서버가 부여한 `charge_index` 중 응답에 없는 게 있으면 → 서버가 `plea=NO_RESPONSE, argument=""`로 자동 채움
- 채운 뒤 **모든 charge가 NO_RESPONSE**면 대립 구조 붕괴로 간주, 스테이지 재시도(`defense_attempts` 재사용, 별도 카운터 없음)

### 4.3 판사(Judgment, 재심 공통) 출력

```json
{
  "opinion": "총평...",
  "verdicts": [
    {
      "charge_index": 0,
      "verdict": "REDUCED",
      "final_severity": "MEDIUM",
      "reasoning": "..."
    }
  ],
  "sentences": [
    {
      "charge_index": 0,
      "task": "...",
      "target_lines": [42, 60],
      "effort": "MEDIUM",
      "effort_adjusted": true,
      "effort_reason": "호출부 40곳에 영향",
      "effort_clamped": false,
      "advisory": false,
      "rationale": "..."
    }
  ],
  "rebuttal_accepted": true
}
```

`rebuttal_accepted`는 **재심에서만 필수**(최초 판결엔 없음/무시).

검증 규칙:

- `verdict`/`sentence`의 `charge_index`가 유효한 재부여 인덱스를 가리켜야 함 → 아니면 해당 항목 폐기
- `verdicts`/`sentences` 배열 안에 동일 `charge_index`가 중복되면 첫 항목만 인정하고 나머지는 폐기(`pleas`와 동일 규칙)
- `final_severity ≤ charged_severity`(상승 불가)
- `REDUCED` 분기: `charged_severity ∈ {HIGH, MEDIUM}` → `final = charged - 1` 정확히 일치 / `charged_severity = LOW` → `final = LOW` 허용, 서버가 `advisory=true` 강제
- `sentences`는 `SUSTAINED`/`REDUCED` charge에만 존재(`DISMISSED`에 있으면 폐기). sentence 폐기는 **`charge_index`/`target_lines` 검증 실패 때만** 발생
- **severity와 effort는 독립**이다(severity=심각도, effort=수정 비용). 감형(`REDUCED`)은 severity 1단계 하락만 의미하며 effort 변경을 수반하지 않는다.
- `effort`는 법전의 `typical_effort`를 기본값으로, ±1단계까지 조정 가능
  - `effort_adjusted=true`인데 `effort_reason`이 부실(10자 미만) → 조정 무효화, `effort=typical_effort`로 리셋(severity_reason과 대칭 처리)
  - `effort_reason`이 충실해도 `typical_effort` ±1 범위를 벗어나면 → **sentence를 폐기하지 않고** 경계값으로 클램프 + `effort_clamped=true` 기록. (severity 범위 초과는 charge 폐기가 맞지만, sentence 폐기는 채택된 죄목에 형량이 없는 판결문을 만들어 결과가 불완전해지므로 severity=폐기, effort=보정으로 비대칭 처리한다.)
  - effort 일관성은 하드 매핑이 아니라 **판례 주입**으로 수렴시킨다(비슷한 rule_id의 과거 typical_effort 사례가 판사 프롬프트에 포함됨)
- 재심에서 `rebuttal_accepted` 누락 → 스키마 무효로 스테이지 재시도(`rejudgment_attempts`)
- **살아있는 charge 중 일부에 `verdict`가 통째로 빠짐** → 불완전한 판결로 간주해 스테이지 재시도(`judgment_attempts`/`rejudgment_attempts`). 서버가 누락분을 대신 채워 판결을 억지로 완성하지 않는다(부분 판결 금지 원칙). 재시도 프롬프트에는 "charge_index 3, 7에 대한 verdict가 누락되었다. 살아있는 모든 기소에 판정을 내려라"처럼 **누락된 인덱스를 구체적으로 명시**해 같은 실수가 반복되지 않게 한다. 재시도 상한 소진 시 일반 스키마 실패와 동일하게 처리(JUDGING이면 사건 `FAILED`, REJUDGING이면 §3대로 원심 유지)

### 4.4 재심 판사 입력

코드 + 확정 기소장 + 변호인 반박 + 신규 판례 조회 결과 + `appeal.rebuttal`(사용자 항소 사유, **필수**). 검사/변호 단계는 재실행하지 않고 그대로 재사용한다.

프롬프트 지침: "사용자 반박은 주장일 뿐 그 자체가 근거는 아니다. 코드와 조항에 비추어 판단하고, 반박을 수용/기각한 이유를 `reasoning`에 남겨라."

### 4.5 스키마 검증 재시도 상한 초과 시(FAILED)

- 완료된 스테이지의 산출물은 보존되어 열람 가능(예: 판사 단계에서 실패했으면 기소장·변론까지는 열람 가능 + "선고 불가" 표시)
- `failed_stage`(PROSECUTION/DEFENSE/JUDGMENT), `failure_reason`(SCHEMA_INVALID/TIMEOUT/API_ERROR)을 사건에 기록
- FAILED 사건은 판례로 적재하지 않음
- FAILED 사건은 코드 해시 캐시 대상에서 제외(그렇지 않으면 실패한 사건이 캐시로 잡혀 영원히 재판이 안 열림)
- 화면에는 "다시 제출" 버튼만 제공. 자동 재시도는 서버가 이미 소진했으므로 추가로 하지 않음

## 5. 법전(Rule Catalog) 구조

- `rules.yaml` 파일로 관리(코드에 하드코딩하지 않음). 조항 추가는 코드 수정이 아니라 데이터 수정.
- 서버 부팅 시 전체 로드 + 스키마 검증. **검증 실패 시 서버 기동 중단**(깨진 법전으로 서버가 뜨면 안 됨):
  - `rule_id` 중복 없음
  - 필수 필드 존재(`rule_id`, `category`, `title`, `description`, `default_severity`, `typical_effort`, `languages`, `active`)
  - `default_severity`/`typical_effort` 값이 유효 enum(HIGH/MEDIUM/LOW, SMALL/MEDIUM/LARGE)
- 조항 삭제는 하지 않는다. 판결 이력이 `rule_id`를 참조하므로 삭제하면 과거 판결의 죄목이 깨진다. 대신 `active: false`로 비활성화한다.
  - 검사 프롬프트에는 `active=true`인 조항만 주입
  - `GET /rules`는 `active=true`인 조항만 반환(법전 열람 화면용)
  - 비활성 조항도 파일/메모리 카탈로그에는 남아있으므로, 과거 판결 조회 시 이름·설명을 조회할 수 있다(DB에 FK로 저장하지 않고 문자열 `rule_id`만 저장하기 때문)

필드 형식:

```yaml
rules:
  - rule_id: SECURITY-001
    category: security # naming | structure | error | performance | security | style
    title: "SQL 인젝션 취약점"
    description: "검사 프롬프트에 주입될 설명. 이 조항이 코드에서 어떻게 식별되는지."
    default_severity: HIGH
    typical_effort: LARGE
    languages: [python, javascript] # 언어무관 공통 조항은 ["*"]
    active: true
```

### 5.1 M1 초안 — 21개 조항 (6개 카테고리, 공통 14 / 언어종속 7)

"코드를 깔끔하게 쓸 것" 류의 판정 불가능한 조항은 제외하고, 코드만 보고 기계적으로 판정 가능한 조항만 담았다.

`languages: ["*"]`는 특정 언어 문법·API에 의존하지 않고 코드 구조만으로 판정 가능한 **공통 조항**이다. 그렇지 않은(예외 처리 구문, 특정 함수명·라이브러리 API에 의존하는) 조항만 `[python, javascript]`로 남긴다. "기타" 언어로 제출된 사건에는 공통 조항만 적용된다(§9, §10).

```yaml
rules:
  # ── NAMING (전부 공통) ────────────────────────────────
  - rule_id: NAMING-001
    category: naming
    title: "의미 없는 변수명"
    description: "루프 카운터(i, j, k)를 제외하고, x/y/tmp/data/val처럼 의미를 알 수 없는 이름이 10줄 이상의 넓은 스코프(함수 전체, 모듈 전역)에서 쓰이는가."
    default_severity: LOW
    typical_effort: SMALL
    languages: ["*"]
    active: true
  - rule_id: NAMING-002
    category: naming
    title: "불리언 이름 불명확"
    description: "불리언 값을 담는 변수나 그런 값을 반환하는 함수가 is_/has_/can_ 같은 접두사 없이 의미가 모호한 이름(flag, status, check 등)을 쓰는가."
    default_severity: LOW
    typical_effort: SMALL
    languages: ["*"]
    active: true
  - rule_id: NAMING-003
    category: naming
    title: "타입 접두사(헝가리안 표기) 잔재"
    description: "strName, iCount처럼 변수명에 타입을 인코딩하는 구식 표기가 쓰이는가."
    default_severity: LOW
    typical_effort: SMALL
    languages: ["*"]
    active: true

  # ── STRUCTURE (전부 공통) ─────────────────────────────
  - rule_id: STRUCTURE-001
    category: structure
    title: "단일 함수 과다 책임"
    description: "하나의 함수가 DB 접근, 외부 API 호출, 알림, 로깅 등 서로 다른 관심사를 3개 이상 동시에 처리하는가."
    default_severity: MEDIUM
    typical_effort: LARGE
    languages: ["*"]
    active: true
  - rule_id: STRUCTURE-002
    category: structure
    title: "과도한 중첩"
    description: "if/for/while이 4단계 이상 중첩되어 코드 흐름을 따라가기 어려운가."
    default_severity: MEDIUM
    typical_effort: MEDIUM
    languages: ["*"]
    active: true
  - rule_id: STRUCTURE-003
    category: structure
    title: "매직 넘버/매직 스트링"
    description: "의미를 알 수 없는 숫자나 문자열 리터럴이 조건문·계산식에 직접 하드코딩되어 있는가(0, 1, -1 같은 관용적 값은 제외)."
    default_severity: LOW
    typical_effort: SMALL
    languages: ["*"]
    active: true
  - rule_id: STRUCTURE-004
    category: structure
    title: "중복 코드 블록"
    description: "동일하거나 매우 유사한 로직 블록이 3회 이상 반복되는가."
    default_severity: MEDIUM
    typical_effort: MEDIUM
    languages: ["*"]
    active: true
  - rule_id: STRUCTURE-005
    category: structure
    title: "주석 없는 복잡한 로직"
    description: "여러 조건 분기나 계산이 얽힌 복잡한 로직 블록에 그 의도를 설명하는 주석이 전혀 없는가."
    default_severity: LOW
    typical_effort: SMALL
    languages: ["*"]
    active: true

  # ── ERROR (전부 언어종속: 예외 처리 구문이 언어마다 다름) ──
  - rule_id: ERROR-001
    category: error
    title: "광범위 예외 처리"
    description: "예외 타입을 명시하지 않고(bare except, catch(e))모든 예외를 한꺼번에 삼키는가."
    default_severity: HIGH
    typical_effort: MEDIUM
    languages: [python, javascript]
    active: true
  - rule_id: ERROR-002
    category: error
    title: "예외 무시"
    description: "예외를 잡고도 로깅이나 재발생 없이 pass/빈 catch 블록으로 조용히 넘어가는가."
    default_severity: MEDIUM
    typical_effort: SMALL
    languages: [python, javascript]
    active: true
  - rule_id: ERROR-003
    category: error
    title: "내부 오류 정보 노출"
    description: "예외 발생 시 스택 트레이스나 내부 오류 메시지를 그대로 사용자 응답에 노출하는가."
    default_severity: MEDIUM
    typical_effort: MEDIUM
    languages: [python, javascript]
    active: true

  # ── PERF (N+1과 전체로드는 공통, 문자열 누적은 언어종속) ──
  - rule_id: PERF-001
    category: performance
    title: "반복문 내 반복 DB/네트워크 호출(N+1)"
    description: "반복문 내부에서 매 반복마다 별도의 DB 쿼리나 네트워크 호출을 수행하는가(배치 처리가 가능한데 하지 않음)."
    default_severity: HIGH
    typical_effort: LARGE
    languages: ["*"]
    active: true
  - rule_id: PERF-002
    category: performance
    title: "반복문 내 비효율적 문자열 누적"
    description: "반복문 안에서 문자열을 += 로 반복 결합하는가(파이썬은 join 미사용, JS는 배열 대신 문자열 누적)."
    default_severity: LOW
    typical_effort: SMALL
    languages: [python, javascript]
    active: true
  - rule_id: PERF-003
    category: performance
    title: "불필요한 전체 데이터 로드 후 필터링"
    description: "쿼리나 API 단에서 조건을 걸어 가져올 수 있는데도 전체 데이터를 로드한 뒤 애플리케이션 코드에서 걸러내는가."
    default_severity: MEDIUM
    typical_effort: MEDIUM
    languages: ["*"]
    active: true

  # ── SECURITY (하드코딩된 비밀정보만 공통, 나머지는 특정 API 인식 필요) ──
  - rule_id: SECURITY-001
    category: security
    title: "SQL 인젝션"
    description: "문자열 결합이나 포매팅으로 SQL 쿼리를 생성해 사용자 입력이 파라미터 바인딩 없이 그대로 들어가는가."
    default_severity: HIGH
    typical_effort: LARGE
    languages: [python, javascript]
    active: true
  - rule_id: SECURITY-002
    category: security
    title: "하드코딩된 비밀정보"
    description: "API 키, 비밀번호, 토큰으로 보이는 값이 소스 코드에 문자열 리터럴로 직접 노출되어 있는가."
    default_severity: HIGH
    typical_effort: SMALL
    languages: ["*"]
    active: true
  - rule_id: SECURITY-003
    category: security
    title: "검증 없는 동적 실행"
    description: "eval/exec(파이썬) 또는 eval/new Function(JS)에 사용자 입력이 검증 없이 전달되는가."
    default_severity: HIGH
    typical_effort: MEDIUM
    languages: [python, javascript]
    active: true
  - rule_id: SECURITY-004
    category: security
    title: "안전하지 않은 역직렬화"
    description: "신뢰할 수 없는 입력을 pickle.loads(파이썬)나 동적 코드 생성 기반 파서(JS)로 역직렬화하는가."
    default_severity: HIGH
    typical_effort: MEDIUM
    languages: [python, javascript]
    active: true

  # ── STYLE (전부 공통) ─────────────────────────────────
  - rule_id: STYLE-001
    category: style
    title: "명명 규칙 혼용"
    description: "같은 파일/모듈 내에서 snake_case와 camelCase가 일관성 없이 섞여 쓰이는가."
    default_severity: LOW
    typical_effort: SMALL
    languages: ["*"]
    active: true
  - rule_id: STYLE-002
    category: style
    title: "축약 변수명"
    description: "의미 파악이 어려운 과도한 축약(d, r, s 등)이 넓은 스코프에서 쓰이는가."
    default_severity: LOW
    typical_effort: SMALL
    languages: ["*"]
    active: true
  - rule_id: STYLE-003
    category: style
    title: "미사용 변수/임포트"
    description: "선언되었지만 이후 한 번도 참조되지 않는 변수나 import 문이 남아있는가."
    default_severity: LOW
    typical_effort: SMALL
    languages: ["*"]
    active: true
```

## 6. 판례(Precedent) 조회

별도 `precedents` 테이블을 두지 않고, `judgments.is_overturned` 플래그 하나로 `charges`/`verdicts`/`judgments`/`cases`를 조인해 조회한다.

```sql
SELECT ... FROM charges
JOIN verdicts ON verdicts.charge_id = charges.id
JOIN judgments ON judgments.id = verdicts.judgment_id
JOIN cases ON cases.id = judgments.case_id
WHERE judgments.is_overturned = false
  AND cases.status = 'SENTENCED'
  AND cases.id != :current_case_id
  AND charges.rule_id = :rule_id
ORDER BY (cases.language = :language) DESC, cases.created_at DESC
```

- 조회 키는 `(rule_id, language)`. **동일 언어 판례를 우선**하고 부족하면 다른 언어로 채운다(같은 조항이라도 언어별로 판단이 갈릴 수 있으므로).
- 상한: **기소 1건당 최대 3건 / 사건 전체 최대 10건**. 초과 시 severity 높은 기소의 판례부터 우선 유지하고 나머지를 자른다(애플리케이션 레벨에서 처리).
- 판례 후보가 없으면(신규 조항 등) "판례 없음"을 판사에게 정직하게 전달한다.

### 판례 적재 기준

- **항소로 뒤집힌 원심 판결은 판례 조회에서 제외**하되, 데이터는 삭제하지 않고 `judgments.is_overturned` 플래그로 조회만 배제한다(통계/분석에는 사용 가능).
- `is_overturned=true` 전환은 **REJUDGING이 성공해서 새 판결(revision=1)이 실제로 생성된 시점**에만 발생한다. 재심이 실패하면(§3 전이표) 원심 판례는 그대로 유효하다(뒤집을 새 판결이 없으므로).
- 재심 판결(revision=1) 자체는 정상 판례로 적재된다(사용자 반박이 반영된 판단이라 원심보다 근거가 강함).
- FAILED 사건은 판례로 적재하지 않는다.
- `DISMISSED` 사건은 애초에 `judgments` 행이 생성되지 않으므로(§3) 위 조인 쿼리에 자연히 걸리지 않는다 — 별도 제외 조건이 필요 없다.
- `judgments.precedent_verdict_ids`(정수 배열)에 실제로 이 판결에 주입된 판례의 `verdict_id` 목록을 기록한다. 판결 재현과 판례 주입 검증(실제로 참고했는지 확인)을 위해 필요하다.

## 7. ERD

| 테이블      | 주요 컬럼                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        | 비고                                                                                                                                                                                                                                                                             |
| ----------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `users`     | id, email(unique), password_hash, created_at                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     | bcrypt 해시, 평문/단순 해시 금지                                                                                                                                                                                                                                                 |
| `cases`     | id, user_id(FK), code, language, code_hash, total_lines, repo_url(nullable), commit_sha(nullable), file_path(nullable), charges_truncated(bool, default false), status(§3: QUEUED_PROSECUTION/PROSECUTING/QUEUED_DEFENSE/DEFENDING/QUEUED_JUDGMENT/JUDGING/SENTENCED/DISMISSED/QUEUED_REJUDGMENT/REJUDGING/FAILED), revision(0/1), appeal_used(bool), prosecution_attempts, defense_attempts, judgment_attempts, rejudgment_attempts, locked_at, locked_by, failed_stage, failure_reason, rejudgment_failed_at, rejudgment_failed_reason, previous_case_id(FK, nullable), created_at, updated_at | 스테이지별 재시도 카운터는 컬럼 4개로 분리. `previous_case_id`는 `force_retrial` 재제출 시 이전 사건 링크. `repo_url`/`commit_sha`/`file_path`는 GitHub 링크 제출일 때만 값이 있음(§8.1) — 붙여넣기 제출은 NULL. `code`(스냅샷)와 `code_hash`는 제출 방식과 무관하게 항상 채워짐 |
| `charges`   | id, case_id(FK), charge_index(서버 부여, 0-based), raw_index(내부용), rule_id(varchar, 법전 파일 참조 — DB FK 아님), evidence_start, evidence_end, charged_severity, severity_adjusted, severity_reason, description                                                                                                                                                                                                                                                                                                                                                                             |                                                                                                                                                                                                                                                                                  |
| `pleas`     | id, charge_id(FK), plea(ADMIT/DENY/NO_RESPONSE), argument                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        |                                                                                                                                                                                                                                                                                  |
| `judgments` | id, case_id(FK), revision(0/1), opinion, rebuttal_accepted(nullable), is_overturned(bool, default false), precedent_verdict_ids(int[]), created_at                                                                                                                                                                                                                                                                                                                                                                                                                                               | 재심 성공 시에만 revision=1 행 생성, 원심(revision=0) 행의 `is_overturned`를 그때 true로 전환                                                                                                                                                                                    |
| `verdicts`  | id, judgment_id(FK), charge_id(FK), verdict, final_severity, reasoning                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                           |                                                                                                                                                                                                                                                                                  |
| `sentences` | id(UUID), judgment_id(FK), charge_id(FK), task, target_start, target_end, effort, effort_adjusted, effort_reason, effort_clamped, advisory, rationale, completed_at(timestamptz, nullable)                                                                                                                                                                                                                                                                                                                                                                                                       | `completed_at`이 NULL이면 미완료, 값이 있으면 완료 시각(체크 해제 시 다시 NULL). `id`는 전역 고유 UUID — `PATCH /sentences/{sentence_id}`가 케이스 경로 없이 단독으로 식별 가능해야 하므로                                                                                       |
| `appeals`   | id, case_id(FK, unique), rebuttal(≥20자), created_at                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                             |                                                                                                                                                                                                                                                                                  |

### 라인 번호 기준 (증거 검증의 단일 기준)

- 개행은 LF로 정규화한 뒤 분할, CRLF/CR 모두 LF로 취급
- 1-based, 빈 줄도 한 줄로 카운트
- 앞뒤 공백 줄은 트림하지 않음(트림하면 사용자가 보는 번호와 어긋남)
- 검사에게 주는 코드에도 이 기준으로 번호를 붙여서 제공

## 8. API 명세

### 표준 에러 응답

모든 4xx/5xx 응답은 아래 형태로 통일한다.

```json
{
  "error": {
    "code": "APPEAL_ALREADY_USED",
    "message": "이미 항소를 사용한 사건입니다.",
    "details": {}
  }
}
```

| code                       | HTTP | 상황                                                                                               |
| -------------------------- | ---- | -------------------------------------------------------------------------------------------------- |
| `VALIDATION_ERROR`         | 400  | 위 표에 없는 일반 요청 필드 검증 실패(공통 폴백)                                                   |
| `EMPTY_CODE`               | 400  | 코드가 비어있거나 공백뿐                                                                           |
| `CODE_TOO_LONG`            | 400  | 코드가 500줄 또는 20000자 초과                                                                     |
| `INVALID_LANGUAGE`         | 400  | `language` 필드가 누락되었거나 문자열이 아님(목록에 없는 값 자체는 에러 아님 — "기타"로 자동 접수) |
| `REBUTTAL_TOO_SHORT`       | 400  | 항소 `rebuttal`이 20자 미만                                                                        |
| `UNAUTHORIZED`             | 401  | 토큰 없음/만료/위조                                                                                |
| `INVALID_CREDENTIALS`      | 401  | 로그인 이메일/비밀번호 불일치                                                                      |
| `CASE_NOT_FOUND`           | 404  | 존재하지 않거나 요청자가 소유자가 아닌 `case_id`                                                   |
| `SENTENCE_NOT_FOUND`       | 404  | 존재하지 않거나 요청자가 소유자가 아닌 `sentence_id`                                               |
| `EMAIL_ALREADY_REGISTERED` | 409  | 회원가입 시 이메일 중복                                                                            |
| `APPEAL_ALREADY_USED`      | 409  | `appeal_used=true`인 사건에 재항소 시도                                                            |
| `RETRIAL_BLOCKED`          | 409  | 동일 코드로 진행 중인 사건이 있는 상태에서 `force_retrial=true` 요청                               |
| `RATE_LIMITED`             | 429  | 최근 24시간 내 생성된 사건 20건 초과. `details: {limit:20, window:"24h", retry_after_seconds:N}`   |
| `INVALID_REPO_URL`         | 400  | GitHub 링크가 아니거나(호스트가 github.com 아님) blob URL 형식이 아니거나 디렉터리를 가리킴(§8.1)  |
| `REPO_FILE_UNAVAILABLE`    | 400  | 대상 파일이 없거나, private 저장소이거나, 404(§8.1)                                                |
| `GITHUB_UNAVAILABLE`       | 503  | GitHub API 자체 오류/rate limit — 잠시 후 재시도 안내(§8.1)                                        |
| `FETCH_RATE_LIMITED`       | 429  | 사용자당 GitHub fetch 시도 24시간 60회 초과(§8.1) — 사건 생성 카운트와 별개                        |

### 인증

| Method/Path           | 설명                                                      |
| --------------------- | --------------------------------------------------------- |
| `POST /auth/register` | `{email, password}` → 201                                 |
| `POST /auth/login`    | `{email, password}` → 200 `{access_token, refresh_token}` |
| `POST /auth/refresh`  | `{refresh_token}` → 200 `{access_token}`                  |

### 법전

| Method/Path  | 설명                      |
| ------------ | ------------------------- |
| `GET /rules` | `active=true` 조항만 반환 |

### 사건

`POST /cases`는 `{code, language}`(붙여넣기) 또는 `{repo_url}`(GitHub 링크, §8.1) 중 정확히 하나를 받는다. 둘 다 없거나 둘 다 있으면 `VALIDATION_ERROR`(400). GitHub 링크 모드는 §8.1의 URL 검증·fetch를 먼저 수행해 `code`/`language`/`code_hash`/`repo_url`/`commit_sha`/`file_path`를 확보한 뒤 아래와 동일한 순서로 처리한다. 아래는 처리 순서다:

1. 요청 검증: `language` 누락/비문자열 → `INVALID_LANGUAGE`(목록에 없는 값 자체는 에러 아님, "기타"로 접수) / 코드 공백 → `EMPTY_CODE` / 500줄·20000자 초과 → `CODE_TOO_LONG`
2. 최근 24시간 내 생성된 사건 수(`created_at > now() - interval '24 hours' AND user_id = :id`) ≥ 20 → `RATE_LIMITED`. 별도 리셋 배치나 카운터 테이블 없이 슬라이딩 윈도우로 매 요청마다 계산한다. 캐시 히트(4번)·진행 중 응답(3번)은 새 사건을 만들지 않으므로 이 카운트에 포함되지 않는다. `FAILED`로 끝난 사건은 LLM 비용이 이미 발생했으므로 포함된다
3. **진행 중 사건 중복 생성 방지는 DB 제약으로 보장한다** — `cases(user_id, code_hash, language)`에 `status NOT IN ('SENTENCED','DISMISSED','FAILED')`(종료 상태가 아닌 행)를 조건으로 하는 부분 유니크 인덱스(partial unique index)를 둔다. 애플리케이션의 "조회 후 삽입"만으로는 동시 요청 두 개가 동시에 통과할 수 있어(레이스 컨디션) 이 제약이 실질적인 방어선이다
   - INSERT가 이 제약에 걸리면(이미 진행 중인 사건 존재) 그 시점에 기존 행을 재조회해 `force_retrial=false`면 **200** `{case_id, cached:false, in_progress:true}` / `force_retrial=true`면 **409** `RETRIAL_BLOCKED`
4. 진행 중 사건이 없으면 **완료된 사건** 캐시 조회: `(user_id, code_hash, language) AND status IN ('SENTENCED', 'DISMISSED')` — `repo_url`/`commit_sha`/`file_path`는 캐시 키에 포함하지 않는다(캐시의 목적은 동일 코드에 LLM을 중복 지출하지 않는 것이므로 출처가 달라도 내용이 같으면 재사용한다 — 포크 저장소나 붙여넣기 후 링크 재제출이 실제로 흔함)
   - 히트 + `force_retrial=false` → **200** `{case_id, cached:true, origin}`(신규 생성 안 함). `origin`은 원 사건의 출처 — GitHub 링크 제출이었다면 `"owner/repo@abc1234, path/to/file.py"`, 붙여넣기였다면 `"붙여넣기로 제출됨"`. 출처가 다른 캐시 히트를 숨기면 사용자가 다른 저장소의 판결문을 보고 혼란스러워지므로 항상 노출한다
   - 히트 + `force_retrial=true` → **202** `{case_id, cached:false, previous_case_id}`(신규 사건 생성, 이전 사건 링크만)
5. 둘 다 없으면 신규 사건 생성 → **202** `{case_id, cached:false}`

| Method/Path                | 설명                                                                                                                                                                                                                                            |
| -------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `POST /cases`              | `{code, language, force_retrial=false}` 또는 `{repo_url, force_retrial=false}`. 처리 순서는 바로 위 참고                                                                                                                                        |
| `GET /cases/{id}/progress` | `{status, revision, appeal_used}`. 소유자 아니면 **404** `CASE_NOT_FOUND`(403 아님 — 사건 존재 여부 자체를 노출하지 않음)                                                                                                                       |
| `GET /cases/{id}`          | 코드+기소장+변론+판결(opinion/verdicts/sentences)+항소 정보 전체(+GitHub 링크 제출이면 `repo_url`/`commit_sha`/`file_path`). 소유자 아니면 **404** `CASE_NOT_FOUND`                                                                             |
| `GET /cases`               | 본인 사건 목록(페이지네이션) — "전과 기록" 화면용                                                                                                                                                                                               |
| `POST /cases/{id}/appeal`  | `{rebuttal}`(≥20자, 미달 **400** `REBUTTAL_TOO_SHORT`). `status=SENTENCED AND appeal_used=false` 아니면 **409** `APPEAL_ALREADY_USED`. 통과 시 `appeal_used=true`, `status→QUEUED_REJUDGMENT` → **202**. 소유자 아니면 **404** `CASE_NOT_FOUND` |

재제출은 별도 엔드포인트 없이 동일 입력으로 `POST /cases`를 다시 호출한다.

### 8.1 GitHub 링크 제출

붙여넣기와 병존하는 두 번째 제출 방식. 사용자가 GitHub 파일의 blob URL(`https://github.com/{owner}/{repo}/blob/{ref}/{path}`)을 제출하면 서버가 해당 파일을 fetch해서 붙여넣기와 동일한 파이프라인(검사→변호→판사)에 태운다.

**URL 검증**

- 호스트가 `github.com`인 blob URL만 허용, URL에서 `owner`/`repo`/`ref`/`path`를 파싱. 다른 호스트/스킴이거나 파싱 실패(디렉터리 링크 포함) → `INVALID_REPO_URL`(400)
- 리다이렉트를 따라가지 않는다(따라가면 호스트 검증이 무의미해짐)

**fetch**

- public 저장소만 지원, 서버 자격증명 없이 GitHub public API로만 호출(private 저장소는 비목표, §1)
- 파일 없음/private/404 → `REPO_FILE_UNAVAILABLE`(400)
- GitHub API 자체 오류나 rate limit → `GITHUB_UNAVAILABLE`(503), 잠시 후 재시도 안내
- fetch 타임아웃 10초
- 응답 크기 상한(500줄/20000자)은 **다운로드 완료 후가 아니라 스트리밍 도중** 끊는다(그렇지 않으면 미니파이 코드 등으로 다운로드만 끝없이 이어질 수 있음) → 초과 시 `CODE_TOO_LONG`
- 언어는 파일 확장자로 추론하되, 화면에서 사용자가 확인·변경 가능
- fetch 성공 시 **커밋 SHA를 고정**해 `commit_sha`에 저장한다(브랜치명만 저장하면 저장소가 나중에 바뀌었을 때 증거 라인 검증의 기준이 흔들리므로). `code`(당시 파일 내용 스냅샷)는 붙여넣기와 동일하게 저장하고, 판결문은 항상 이 스냅샷을 기준으로 라인 번호를 매긴다

**fetch 자체의 남용 방지**

- fetch 실패(`REPO_FILE_UNAVAILABLE`/`GITHUB_UNAVAILABLE`)는 LLM 비용이 발생하지 않으므로 일일 20건(사건 생성) 카운트에는 포함하지 않는다
- 그러나 그렇게 두면 GitHub API 호출 자체를 무제한 시도할 수 있는 구멍이 생긴다 — **fetch 시도** 자체에 별도 rate limit을 둔다: 사용자당 24시간 60회(사건 생성 카운터와 완전히 별개). 초과 시 `FETCH_RATE_LIMITED`(429). 서버가 사용자 대신 외부 요청을 대행하는 구조이므로, LLM 비용과 무관하게 GitHub API 할당량 소모·요청 대행 오용 자체를 제한할 필요가 있다

**화면**

- 코드 제출 화면에 붙여넣기/링크 두 입력 모드를 제공
- 판결문 화면에 저장소·커밋(짧은 SHA)·파일 경로와 원본 GitHub 링크(해당 커밋 기준)를 표시(붙여넣기 제출 사건은 이 영역을 표시하지 않음)

### 형량 체크리스트

| Method/Path                      | 설명                                                                                                                                                                                                                                                                                                                  |
| -------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `PATCH /sentences/{sentence_id}` | `{completed: true\|false}`. `completed=true`면 `completed_at=now()`, `false`면 `completed_at=NULL`. 소유자 아니면 **404** `SENTENCE_NOT_FOUND`. 사건 `status`와 무관하게 언제든 토글 가능(판결 확정 후 할 일 처리이므로). 응답에 사건 전체 이행률을 함께 반환: `{sentence_id, completed_at, progress: {done, total}}` |

## 9. 화면 목록

1. 로그인 / 회원가입
2. 코드 제출 — 언어 선택(고정 목록), 코드 입력(라인/문자수 실시간 카운터), 캐시 히트 시 안내 모달("이미 판결된 코드") + 재판 강행(`force_retrial`) 옵션. "기타" 선택 시 "언어 종속 조항은 적용되지 않습니다. 공통 조항 N개만으로 심사합니다" 안내(N은 활성 공통 조항 수를 그때그때 계산, 하드코딩 안 함)
3. 사건 진행 — 2초 폴링, 현재 스테이지(검사중/변호중/판결중) 표시, `FAILED` 시 실패 사유 + 재제출 버튼
4. 판결문 — 기소장(조항/증거라인/severity) + 변론(plea별) + 판결(opinion/verdict/reasoning) + 형량 체크리스트(task/effort/advisory 표시) + 항소 버튼(`appeal_used=false`일 때만 노출)
5. 항소 입력 모달 — rebuttal 텍스트(≥20자)
6. 재심 결과 — `revision=1` 최종 판결 또는 "재심 실패, 원심 유지" 배너(`revision=0, appeal_used=true`)
7. 마이페이지 / 전과 기록 — 본인 사건 목록, rule_id별 반복 통계
8. 법전 열람 — `GET /rules` 표 형태

## 10. 엣지 케이스

**입력 검증**

- 코드가 아닌 일반 텍스트를 붙여넣음 → 접수 시 휴리스틱으로 경고 후 사용자 확인을 받고 진행
- 코드에 API 키/비밀번호로 보이는 패턴 포함 → 탐지해 마스킹 경고 표시
- 목록에 없는 언어 → "기타"로 접수, 언어무관 공통 조항만 적용
- 코드가 500줄 또는 20000자 초과 → `400`
- 일일 제출 20건 초과 → `429`

**검사/변호/판사 단계**

- 검사 유효 기소 0건 → 변호/판사 스테이지를 건너뛰고 즉시 `DISMISSED`(무혐의)로 종결, 판결문 대신 무혐의 통지 표시(§3)
- 전체 기소에 반박이 하나도 없음(모두 NO_RESPONSE) → 대립 구조 붕괴로 간주, 스테이지 재시도 1회(기존 재시도 카운터 재사용)
- `severity_reason`/`effort_reason`이 부실 → 조정 자체를 무효화하고 기본값(`default_severity`/`typical_effort`)으로 복귀, charge/sentence는 폐기하지 않음
- `effort`가 `typical_effort` ±1 범위를 벗어남(사유는 충실) → 경계값으로 클램프 + `effort_clamped=true` 기록(폐기 안 함)
- 판례 후보가 상한(기소당 3/사건 10)을 초과 → severity 높은 기소의 판례를 우선 유지하고 나머지는 자름
- 판례 후보 자체가 없음(신규 조항 등) → "판례 없음"으로 판사에게 정직하게 전달

**동시성 / 장애**

- 워커 크래시(스테이지 처리 도중 프로세스 종료) → `locked_at` 15분 타임아웃 후 다른 워커가 재픽업, **완료된 스테이지는 재실행하지 않음**(스테이지 단위 커밋이므로 재개 지점이 `status` 값으로 결정됨)
- 워커가 죽지 않고 LLM 응답이 오래 걸리는 중에 타임아웃이 지나 다른 워커가 재픽업 → 두 워커가 같은 스테이지를 동시에 끝낼 수 있음. 완료 커밋이 조건부 UPDATE(§2)라 늦게 도착하는 쪽은 0행 적용으로 조용히 버려짐(이중 커밋 방지, `stale_commit_rate` 지표로 관찰)
- 스키마 검증 재시도 상한 초과 → 사건 `FAILED`, 완료된 스테이지 산출물은 보존해 열람 가능, 판례/캐시 대상에서 제외

**항소 / 재심**

- 재심이 재시도 상한을 초과 → 원심(`revision=0`) 판결 유효 유지, `rejudgment_failed_reason` 기록, 항소 기회는 소진 처리(재항소 불가)
- `revision=1`인 사건에 재항소 시도 → `409`
- 재심 성공 → 원심 판례는 `is_overturned=true`로 조회에서 배제(데이터는 보존), 재심 판결은 정상 판례로 적재

**법전 / 캐시**

- 조항 비활성화(`active=false`) 후 과거 판결 조회 → 파일/메모리 카탈로그에 조항이 남아있어 이름·설명 조회 가능
- 정규화 후 해시가 같은 코드를 사소하게 수정(주석만 변경 등)해도 캐시가 히트됨 → `force_retrial=true`로 우회하면 새 사건 생성(이전 사건과 링크)
- 동일 코드(`user_id`+`code_hash`+`language`)를 판결이 나기 전에 연속 제출 → 새 사건을 만들지 않고 기존 진행 중 사건을 그대로 반환(`in_progress:true`). LLM 호출 중복 방지가 목적이며, 이 상태에서 `force_retrial=true`를 요청하면 `409 RETRIAL_BLOCKED`
- `DISMISSED`(무혐의)로 종결된 코드를 동일 조건으로 재제출 → `SENTENCED`와 동일하게 캐시 히트 처리(무혐의도 정상적인 재판 결과이므로). 단 `DISMISSED`는 `judgments` 행이 없어 판례 적재 대상은 아님

**접근 제어**

- 남의 `case_id`로 조회 시도 → `404`(사건 존재 여부 자체를 노출하지 않음, `403` 아님)

## 11. 검증 지표

시스템이 설계 의도대로 동작하는지 운영 중 확인할 지표. 학교 과제 규모라 아래 정상범위는 실제 데이터가 쌓이기 전의 초기 기준치이며, M1 운영 후 보정한다.

| 지표                   | 정의                                                                                                                                 | 정상범위(초기 기준) | 벗어났을 때 해석                                                                                                                                                                                                                                  |
| ---------------------- | ------------------------------------------------------------------------------------------------------------------------------------ | ------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 기소 폐기율            | (`rule_id` 무효 + `evidence_lines` 범위 밖 + `charged_severity` ±1 초과로 폐기된 charge 수) / 검사 출력 전체 charge 수(폐기 전, raw) | 5% 미만             | 15% 초과 시 검사가 법전을 준수하지 않거나 라인 번호 계산을 잘못하고 있다는 신호. 프롬프트에 법전 목록·라인 기준을 다시 강조해야 함                                                                                                                |
| 기각률                 | `verdict=DISMISSED`인 charge 수 / 재판이 실제로 진행된 사건(§3에서 `DISMISSED`로 단축되지 않은 사건)의 전체 charge 수                | 10~30%              | 5% 미만이면 판사가 지나치게 강경(변호인 반박을 거의 받아들이지 않음) → 변호인 프롬프트 보강 검토. 40% 초과면 검사가 기소를 남발하거나 판사가 지나치게 관대함 → 검사 프롬프트의 법전 적용 기준 재검토                                              |
| severity 조정률        | `severity_adjusted=true`인 charge 수 / 살아남은 전체 charge 수                                                                       | 10~25%              | 5% 미만이면 검사가 법전 기본값을 기계적으로만 사용, 코드 맥락을 반영하지 않음. 50% 초과면 기본값을 신뢰하지 않고 임의 조정을 남발 → `severity_reason` 폐기/리셋 비율과 함께 점검                                                                  |
| 항소 수용률            | `rebuttal_accepted=true`인 재심(REJUDGING 성공) 수 / 전체 재심 성공 수                                                               | 30~60%              | 90% 초과 시 판사가 사용자 주장에 과도하게 수긍하고 있다는 신호 — "사용자 주장은 그 자체로 근거가 아니다"라는 프롬프트 지침을 강화해야 함. 10% 미만이면 항소가 사실상 무의미(반박이 거의 반영되지 않음) → 재심 판사 프롬프트의 반박 검토 로직 점검 |
| verdict_missing_rate   | 살아있는 charge 중 `verdict`가 누락되어 스테이지 재시도가 발생한 판결 시도 수 / 전체 판결(JUDGING+REJUDGING) 시도 수                 | 5% 미만             | 높으면(15% 초과) 기소 건수 상한(12건, §4.1)만으로는 부족하다는 신호 — 판례 주입량(§6) 축소나 상한 자체를 더 낮추는 것을 검토해야 함                                                                                                               |
| charges_truncated 비율 | `charges_truncated=true`인 사건 수 / 전체 사건 수                                                                                    | 5% 미만             | 높으면 검사가 상한(12건)을 상시로 넘기고 있다는 신호 — 코드 길이 상한(500줄)이나 법전 조항 수 대비 상한이 너무 낮은 건 아닌지 재검토                                                                                                              |
| stale_commit_rate      | 워커의 조건부 완료 커밋(§2)이 0행 적용되어 버려진 횟수 / 전체 스테이지 완료 시도 수                                                  | 0%                  | 0보다 크면 `locked_at` 15분 타임아웃이 여전히 짧아 정상 처리 중인 워커가 재수거당하고 있다는 신호 — 타임아웃을 더 늘리거나 LLM 호출 자체의 지연 원인을 점검해야 함                                                                                |

## 12. 구현 단계

### M1 — 단심 재판

- 인증(JWT access/refresh, bcrypt), `users`/`cases`/`charges`/`pleas`/`judgments`/`verdicts`/`sentences` 스키마(재심 관련 컬럼은 존재하되 미사용)
- `rules.yaml` 20개 조항 작성 + 부팅 시 검증(실패 시 기동 중단)
- 코드 제출 API: 언어 고정 목록, 라인≤500/문자≤20000 검증, 텍스트/시크릿 휴리스틱 경고
- DB 폴링 워커(스테이지 단위, `SELECT ... FOR UPDATE SKIP LOCKED`, `locked_at`/`locked_by` 타임아웃 재픽업)
- 검사/변호/판사 3단계 스키마 강제 + 서버 검증(§4 전체: charge_index 서버 부여, severity ±1, evidence 라인 검증, plea NO_RESPONSE 백필, effort typical_effort±1 클램프 등)
- 재시도 상한 초과 시 FAILED 처리(완료 스테이지 보존)
- 화면: 로그인/회원가입, 코드 제출, 사건 진행(폴링), 판결문
- 판례 조회/항소/코드 해시 캐시는 이 단계에서 비활성(판사는 판례 없이 판단)

### M2 — 형량 체크리스트 + 전과 기록

- 판결문 화면에 형량 체크리스트 UI 강화(effort/advisory 뱃지 표시)
- `GET /cases` 목록 + 마이페이지 화면, `rule_id`별 반복 기소 통계 집계
- 법전 열람 화면(`GET /rules`)

### M3 — 항소·재심 + 판례 조회·주입 + 동일 코드 캐시

- `appeals` 테이블, `POST /cases/{id}/appeal`, `revision`/`appeal_used` 상태머신 확장(§3), REJUDGING 처리(재심 실패 시 원심 보존 로직 포함)
- 판례 조회 쿼리(§6: rule_id+language, 기소당 3/전체 10건 상한, `is_overturned` 배제) 및 판사 프롬프트 주입, `judgments.precedent_verdict_ids` 기록
- 재심 성공 시 원심 `judgments.is_overturned=true` 전환
- 코드 해시 캐시(`POST /cases`의 `force_retrial` 분기, `(user_id, code_hash, language)` 키)
- 화면: 항소 입력 모달, 재심 결과 화면
