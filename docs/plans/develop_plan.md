# 개발 계획 — 대립형 코드 리뷰 서비스

설계 근거: `docs/plans/plan.md` (상세 스펙 이력은 `docs/superpowers/specs/2026-09-07-adversarial-code-review-design.md`)

## M1 — 단심 재판 (검사→변호→판사, 법전 20개 조항, 증거 라인 검증, 스키마 강제) [완료 — 백엔드 기준]

**백엔드**

- DB 스키마 마이그레이션: `users`, `cases`, `charges`, `pleas`, `judgments`, `verdicts`, `sentences`(재심/GitHub 관련 컬럼은 포함하되 이 단계에선 미사용)
- `cases(user_id, code_hash, language)`에 대해 `status NOT IN ('SENTENCED','DISMISSED','FAILED')` 조건의 부분 유니크 인덱스(진행 중 사건 중복 생성 방지)
- `rules.yaml` 20개 조항 작성 + 부팅 시 검증(중복/필수필드/enum 유효성, 실패 시 기동 중단)
- 인증: 회원가입/로그인/토큰 재발급(JWT, bcrypt), 토큰은 httpOnly+Secure+SameSite=Lax 쿠키, CSRF 대응(커스텀 헤더 검증 또는 Double Submit Cookie 중 택일)
- `POST /cases`(붙여넣기 모드만): 언어 고정 목록 검증, 라인≤500/문자≤20000 검증, 텍스트/시크릿 휴리스틱 경고, 24시간 슬라이딩 윈도우 기반 일일 20건 제한
- 워커: DB 폴링(`SELECT FOR UPDATE SKIP LOCKED`), 스테이지 단위 처리, 하트비트(`locked_at` 주기 갱신) + 조건부 완료 커밋(`WHERE locked_by=... AND status=...`), 타임아웃 15분
- 검사/변호/판사 프롬프트 및 스키마 검증: 서버의 `charge_index` 부여, 사건당 기소 12건 상한(severity순 절단), severity ±1 검증, evidence 라인 검증, plea 백필, effort 클램프, verdict 누락 시 인덱스 명시 재시도
- 스테이지 총 시도 횟수(`stage_attempts`) 상한 3회 초과 시 FAILED 처리(완료 스테이지 산출물 보존). LLM provider의 429는 `stage_attempts`와 분리된 별도 카운터로 지수 백오프 재시도(일일 제출 카운트나 FAILED 처리에 영향 없음)
- `GET /cases/{id}/progress`, `GET /cases/{id}`

**프론트**

- 로그인/회원가입 화면(비밀번호 찾기 링크 없음)
- 코드 제출 화면(붙여넣기 모드)
- 사건 진행 화면(2초 폴링)
- 판결문 화면

**선행 의존성**

- `rules.yaml` + 부팅 검증이 워커보다 먼저
- DB 스키마(부분 유니크 인덱스 포함)가 인증/사건 API보다 먼저
- 인증이 `POST /cases`보다 먼저(소유자 검증 전제)
- 워커 내부는 검사→변호→판사 순서 의존

**완료 기준**

- 인증된 사용자 1인이 코드 제출부터 판결문 열람까지 fixture provider로 전 과정이 동작. 실제 LLM 연동은 provider 교체만 남음(§12 provider 추상화)
- 스키마 검증 실패를 인위로 유도했을 때 재시도 후 `FAILED`로 종결되고 API가 사유(`failed_stage`/`failure_reason`)를 반환함
- 워커 프로세스를 강제 종료해도 15분 후 다른 워커가 이어받아 완료됨(완료된 스테이지는 재실행 안 됨)
- 동일 코드를 짧은 간격으로 두 번 연속 요청해도 사건이 하나만 생성됨(부분 유니크 인덱스 동작 확인)
- 기소 12건을 초과하는 코드를 넣었을 때 상위 12건만 채택되고 `charges_truncated=true`가 기록됨

화면 표시(사유 노출 등)에 대한 검증은 프론트엔드 구현 시점으로 미룬다 — 위 기준은 모두 API/DB 레벨에서 확인된 것이다.

## M2 — 형량 체크리스트 + 전과 기록 + 반복 조항 통계 [완료 — 백엔드 기준]

**백엔드**

- `PATCH /sentences/{sentence_id}`: `completed_at` 토글, 소유자 검증, 응답에 사건 이행률 포함
- `GET /cases` 목록 API(페이지네이션)
- 사용자별 `rule_id` 반복 집계 쿼리/엔드포인트
- `GET /rules`

**프론트**

- 판결문 화면에 형량 체크리스트 UI(체크박스 + 이행률 바) 적용
- 마이페이지 / 전과 기록 화면
- 법전 열람 화면

**선행 의존성**

- M1에서 쌓인 `charges`/`sentences` 데이터가 있어야 체크리스트·통계가 의미를 가짐
- M1의 판결문 화면 골격 위에 체크리스트를 얹는 구조

**완료 기준**

- 사용자가 여러 건 제출한 뒤 `GET /cases/rule-frequency`가 반복 조항 통계를 실제 집계값으로 반환함
- 형량 체크박스 토글 상태가 새로고침 후에도 유지됨(`PATCH /sentences` 서버 저장 확인)

마이페이지 화면에서의 표시 검증은 프론트엔드 구현 시점으로 미룬다 — 위 기준은 모두 API/DB 레벨에서 확인된 것이다.

## M3 — 항소·재심 + 판례 조회·주입 + 동일 코드 캐시 [완료 — 백엔드 기준]

**백엔드**

- `appeals` 테이블 + `POST /cases/{id}/appeal`, `revision`/`appeal_used` 상태머신 확장
- `REJUDGING` 처리(재시도 상한 초과 시 원심 보존, `revision=0` 유지 + `appeal_used=true` 소진)
- 판례 조회 쿼리(`rule_id`+`language`, 기소당 3/전체 10건 상한, `is_overturned` 배제) 및 판사 프롬프트 주입, `judgments.precedent_verdict_ids` 기록
- 재심 성공 시 원심 `judgments.is_overturned=true` 전환
- `POST /cases`에 완료된 사건(`SENTENCED`/`DISMISSED`) 캐시 조회 + `force_retrial` 분기 추가

**프론트**

- 항소 입력 모달
- 재심 결과 화면(원심 유지 배너 포함)
- 코드 제출 화면에 캐시 히트 안내 모달(출처 표시 포함) + 재판 강행 옵션 추가

**선행 의존성**

- M1의 판사 스테이지 로직이 재사용 가능한 형태여야 재심에 그대로 연결 가능
- 판례 조회 검증을 위해 M1/M2에서 쌓인 `SENTENCED` 사건이 최소 1건 이상 필요
- 캐시 기능은 M1 스키마의 `code_hash` 컬럼과 부분 유니크 인덱스를 그대로 사용(추가 마이그레이션 불필요)

**완료 기준**

- 항소 1회 접수 후 재항소 시도 시 `409` 반환 확인
- 재심을 인위로 실패시켰을 때 원심 판결이 그대로 조회되고 항소 버튼이 다시 노출되지 않음
- 동일 코드 재제출 시 캐시 히트로 `200` 응답, `force_retrial=true` 시 새 사건 생성 확인
- 판례가 존재하는 `rule_id`로 새 사건을 판결했을 때 `judgments.precedent_verdict_ids`가 채워짐

## M4 — GitHub 링크 제출 [미착수]

M1~M3의 핵심 재판 파이프라인과 독립적으로 붙일 수 있는 추가 제출 경로라 별도 마일스톤으로 분리했다(코어 로직 변경 없이 입력 소스만 추가하는 구조).

**백엔드**

- `cases`에 `repo_url`/`commit_sha`/`file_path` 컬럼 활용, blob URL 파싱(호스트가 `github.com`인지, `owner/repo/ref/path` 추출), 리다이렉트 미추종
- GitHub public API fetch: 타임아웃 10초, 응답 크기 스트리밍 중 500줄/20000자 컷, 실패 시 `REPO_FILE_UNAVAILABLE`/`GITHUB_UNAVAILABLE`
- 사용자당 24시간 60회 fetch 시도 제한(`FETCH_RATE_LIMITED`, 사건 생성 카운터와 별개)
- fetch 성공 시 커밋 SHA 고정 저장, 이후 M1의 `POST /cases` 파이프라인(캐시 조회 포함, `code_hash` 기준)에 그대로 합류

**프론트**

- 코드 제출 화면에 GitHub 링크 입력 모드 추가(언어 확장자 추론 + 사용자 확인/변경)
- 판결문 화면에 저장소/커밋/경로/원본 링크 표시(붙여넣기 사건은 미표시)

**선행 의존성**

- M1의 `POST /cases` 처리 파이프라인과 캐시 로직이 먼저 완성되어 있어야 함(fetch는 그 앞단에 붙는 전처리 단계)

**완료 기준**

- public 저장소의 파일 blob URL 제출 시 M1과 동일한 절차로 재판이 진행되고 판결문에 출처가 표시됨
- 디렉터리 링크/비공개 저장소/존재하지 않는 파일 제출 시 각각 올바른 에러 코드로 거부됨
- 60회를 초과하는 fetch 시도 시 `FETCH_RATE_LIMITED`가 반환되고, 이 시도들이 일일 사건 생성 카운트에는 영향을 주지 않음
