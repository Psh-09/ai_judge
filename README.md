# Code Court

코드를 제출하면 AI 세 역할(검사·변호인·판사)이 재판을 열어, 걸러진 지적과 실행 가능한 리팩토링 할 일 목록을 내려주는 대립형 코드 리뷰 서비스입니다.

## 라이브 데모

- 프론트엔드: https://codecourt-client.onrender.com
- API 문서(Swagger UI): https://codecourt-api.onrender.com/docs

**데모 계정**

| 이메일             | 비밀번호             |
| ------------------ | -------------------- |
| `demo@example.com` | `CodeCourtDemo2026!` |

배포 환경은 `LLM_PROVIDER=fixture` 모드로 운영됩니다. 실제 LLM을 호출하지 않고, 미리 등록된 샘플 코드 한 건에 대해서만 저장된 판결을 돌려줍니다 — 화면 상단 데모 배너의 **[샘플 코드 보기]** 버튼을 누르면 제출 폼에 그 샘플이 자동으로 채워지니, 임의의 코드를 붙여넣지 말고 이 버튼을 사용하세요(임의 코드는 검사 단계에서 재시도 후 `FAILED`로 종결됩니다 — 오류가 아니라 fixture 모드의 의도된 동작입니다).

두 서비스 모두 Render 무료 플랜이라 일정 시간 요청이 없으면 슬립 상태가 되며, 첫 접속 시 콜드 스타트로 최대 30초 정도 응답이 걸릴 수 있습니다.

## 3단계 흐름

1. **검사** — 법전(사전 정의된 조항 목록)과 코드를 대조해 위반을 찾아 기소한다.
2. **변호인** — 각 기소에 대해 반박한다. 맥락상 과한 지적을 걸러내는 단계다.
3. **판사** — 기소와 변론을 함께 보고 채택·감형·기각을 결정하고, 할 일(형량)을 정한다.

## 핵심 설계

- **법전 제약** — 죄목은 코드가 임의로 지어내지 않고, 사전 정의된 조항 목록(`rules.yaml`)의 `rule_id`에서만 고를 수 있다.
- **증거 라인 검증** — 모든 기소는 코드 라인 범위를 증거로 지목해야 하며, 서버가 실제 라인 수와 대조해 검증한다. 범위를 벗어난 기소는 폐기된다.

## 문서

| 문서                                                       | 내용                                                                 |
| ---------------------------------------------------------- | -------------------------------------------------------------------- |
| [`docs/plans/plan.md`](docs/plans/plan.md)                 | 시스템 설계 — 상태머신, 스키마, 법전/판례 규칙, ERD, 비용 예산, 배포 |
| [`docs/plans/develop_plan.md`](docs/plans/develop_plan.md) | M1~M4 개발 마일스톤별 작업 목록                                      |
| [`docs/design.md`](docs/design.md)                         | UI 디자인 브리프 — 톤, 원칙, 토큰, 화면 목록                         |
| [`openapi.yaml`](openapi.yaml)                             | API 상세 스키마(OpenAPI 3.0)                                         |
| [`docs/api.md`](docs/api.md)                               | API 요약 — 엔드포인트 표, 사건 생명주기                              |
| [`rules.yaml`](rules.yaml)                                 | 법전(조항 목록) 원본                                                 |

## 화면 목업 (설계 단계 산출물)

아래 4개는 프론트엔드 구현 전, 설계 단계에서 톤·레이아웃을 검증하려고 만든 정적 목업이다. **지금은 실제 Next.js 구현체가 있으므로 실물을 보려면 위 [라이브 데모](#라이브-데모)를 사용할 것** — 이 이미지들은 디자인 근거 기록으로만 남겨둔다.

| 판결문                               | 형량 체크리스트                                           |
| ------------------------------------ | --------------------------------------------------------- |
| ![판결문](docs/mockups/judgment.png) | ![형량 체크리스트](docs/mockups/sentencing-checklist.png) |

| 법정 진행                                         | 법전 열람                                   |
| ------------------------------------------------- | ------------------------------------------- |
| ![법정 진행](docs/mockups/courtroom-progress.png) | ![법전 열람](docs/mockups/rule-catalog.png) |

`design.md` §5는 화면을 9개로 나누지만, 실제 구현은 5개 라우트다 — 3개는 별도 화면이 아니라 다른 화면에 흡수됐다:

| `design.md` §5 화면 | 실제 구현                                   |
| ------------------- | ------------------------------------------- |
| 5.1 로그인/회원가입 | `/login`                                    |
| 5.2 코드 제출       | `/submit`                                   |
| 5.3 법정(사건 진행) | `/cases/[id]` (진행 중일 때)                |
| 5.4 판결문          | `/cases/[id]` (판결 확정 후, 같은 라우트)   |
| 5.5 형량 체크리스트 | 별도 화면 아님 — 판결문 화면 안에 인라인    |
| 5.6 항소 입력       | 별도 화면 아님 — 판결문 화면의 모달         |
| 5.7 재심 결과       | 별도 화면 아님 — 판결문 화면 상단 상태 배너 |
| 5.8 전과 기록       | `/cases`                                    |
| 5.9 법전 열람       | `/rules`                                    |

## 기술 스택

- 클라이언트: Next.js
- 서버: FastAPI
- DB: PostgreSQL
- 큐: 별도 브로커 없이 PostgreSQL 폴링(스테이지 단위 워커) — 자세한 근거는 `docs/plans/plan.md` §3 참고

## 구현 현황

백엔드(FastAPI + PostgreSQL)와 프론트엔드(Next.js) 모두 구현되어 있습니다.

| 영역                 | 상태   | 비고                                                                                                                           |
| -------------------- | ------ | ------------------------------------------------------------------------------------------------------------------------------ |
| 법전 로더            | 구현됨 | `rules.yaml` 부팅 시 검증(중복/필수필드/enum), 조회 헬퍼                                                                       |
| 검증 파이프라인      | 구현됨 | 코드 정규화·해시, 검사/변호/판사 출력 서버 검증(순수 함수)                                                                     |
| 인증                 | 구현됨 | 회원가입/로그인/토큰 재발급, JWT httpOnly 쿠키, CSRF 커스텀 헤더                                                               |
| 사건 제출/조회       | 구현됨 | 캐시 히트/진행중 판정, 소유자 검증(404), 24시간 슬라이딩 윈도우 한도                                                           |
| 워커                 | 구현됨 | DB 폴링(FOR UPDATE SKIP LOCKED), 하트비트, 재시도 상한, 재심 스테이지                                                          |
| 형량 체크리스트 토글 | 구현됨 | `PATCH /sentences/{id}`, 사건 상태와 무관하게 토글                                                                             |
| 전과 기록            | 구현됨 | `GET /cases` 목록, `GET /cases/rule-frequency` 반복 조항 랭킹                                                                  |
| 항소·재심            | 구현됨 | 항소 접수, 재심(판사만 재실행), 판례 뒤집힘(`is_overturned`) 처리                                                              |
| 판례 조회·주입       | 구현됨 | `(rule_id, language)` 조회, 판사/재심 프롬프트에 주입, `judgments.precedent_verdict_ids` 기록                                  |
| GitHub 링크 제출     | 구현됨 | blob URL 파싱, 커밋 SHA 고정, 24시간 60회 fetch 제한(사건 생성 카운트와 별개)                                                  |
| 실제 LLM provider    | 미구현 | fixture 모드만 동작(`app/fixtures/data.py`). `RealLLMProvider`는 `NotImplementedError` 스텁                                    |
| 프론트엔드           | 구현됨 | Next.js(App Router) — 로그인/제출/사건 진행/판결문/전과 기록/법전 화면, 헤더 내비게이션, `docs/design.md` 6장 온보딩·안내 배너 |

## 로컬 실행 방법

Docker와 Docker Compose만 있으면 됩니다.

```bash
git clone https://github.com/Psh-09/ai_judge.git
cd ai_judge
docker compose up --build
```

postgres(볼륨으로 데이터 유지) → api(기동 전 `alembic upgrade head` 자동 실행) → worker(같은 이미지, `python -m app.worker_main`) → client 순서로 뜹니다. api는 postgres의 헬스체크가 통과한 뒤에, worker는 api의 헬스체크(마이그레이션이 이미 끝난 상태)가 통과한 뒤에 시작됩니다 — api와 worker가 동시에 `alembic upgrade head`를 돌리면 `alembic_version` 테이블 생성 경합으로 한쪽이 죽는 문제가 실제로 있어 이렇게 순서를 강제합니다.

기동 완료 후:

- 프론트엔드: http://localhost:3000
- API: http://localhost:8000 (`/health`가 `{"status":"ok"}`)

`CORS_ALLOWED_ORIGINS=http://localhost:3000`, `ENVIRONMENT=development`(운영 전용 `JWT_SECRET` 가드에 걸리지 않음), `NEXT_PUBLIC_API_URL=http://localhost:8000/api/v1`이 `docker-compose.yml`에 기본값으로 들어 있어 별도 설정 없이 바로 회원가입 → 코드 제출까지 됩니다. DB를 초기화하려면 `docker compose down -v`.

### 수동 실행

Docker Compose 없이, 각 구성 요소를 직접 띄우고 싶을 때의 방법입니다.

Python 3.11+, Node 20+, Docker(로컬 PostgreSQL용)가 필요합니다.

```bash
# 1. 저장소 클론 후 server/ 로 이동
git clone https://github.com/Psh-09/ai_judge.git
cd ai_judge/server

# 2. 가상환경 + 의존성
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 3. 환경변수 (기본값이 아래 4번 docker 명령과 그대로 맞음 — 수정 없이 써도 됨)
cp .env.example .env

# 4. 로컬 PostgreSQL (docker)
docker run -d --name codecourt-pg \
  -e POSTGRES_USER=user -e POSTGRES_PASSWORD=password -e POSTGRES_DB=codecourt \
  -p 5432:5432 postgres:16-alpine

# 5. 스키마 마이그레이션
alembic upgrade head

# 6. API 서버
uvicorn app.main:app --reload

# 7. 워커 (별도 터미널, 같은 venv)
source .venv/bin/activate
python -m app.worker_main

# 8. 프론트엔드 (별도 터미널)
cd ../client
cp .env.example .env.local        # NEXT_PUBLIC_API_URL=http://localhost:8000/api/v1 로 수정
npm install
npm run dev
```

`http://127.0.0.1:8000/health` 가 `{"status":"ok"}`를 반환하면 서버가 정상 기동한 것입니다. 법전(`rules.yaml`)은 저장소 루트에 있고, 서버가 `server/app/config.py`의 경로 계산을 통해 자동으로 찾으므로 별도 설정이 필요 없습니다.

### fixture 모드로 데모 돌려보기

`LLM_PROVIDER=fixture`(기본값)에서는 실제 LLM을 호출하지 않고, 미리 등록된 **딱 한 개의 샘플 코드**에 대해서만 저장된 판결을 돌려줍니다. 등록된 코드는 `server/app/fixtures/sample_user_handler.py`(187줄)이며, 이 파일 내용을 그대로 `POST /cases`에 제출해야 검사→변호→판사 3단계가 실제 판결로 이어집니다. 그 외의 임의 코드를 제출하면 검사 단계에서 "fixture 미등록" 사유로 3회 재시도 후 `FAILED`로 종결됩니다(의도된 동작입니다 — 실제 오류가 아닙니다).

간단한 확인 절차:

```bash
# 회원가입 + 로그인 (쿠키 저장)
curl -c cookies.txt -X POST http://127.0.0.1:8000/api/v1/auth/register \
  -H "Content-Type: application/json" -d '{"email":"demo@example.com","password":"password123"}'
curl -b cookies.txt -c cookies.txt -X POST http://127.0.0.1:8000/api/v1/auth/login \
  -H "Content-Type: application/json" -d '{"email":"demo@example.com","password":"password123"}'

# 샘플 코드 제출 (server/ 디렉터리에서 실행)
python3 -c "
import json
from app.fixtures.data import SAMPLE_CODE, SAMPLE_LANGUAGE
print(json.dumps({'code': SAMPLE_CODE, 'language': SAMPLE_LANGUAGE}))
" > /tmp/payload.json
curl -b cookies.txt -X POST http://127.0.0.1:8000/api/v1/cases \
  -H "Content-Type: application/json" -H "X-CSRF-Protection: 1" --data @/tmp/payload.json
# 응답의 case_id로 폴링 (워커가 몇 초 안에 SENTENCED까지 처리한다)
curl -b cookies.txt http://127.0.0.1:8000/api/v1/cases/<case_id>/progress
curl -b cookies.txt http://127.0.0.1:8000/api/v1/cases/<case_id>
```

이 모드에서도 상태머신·큐/워커 처리·서버 측 스키마/라인/법전 검증·항소/재심 흐름은 모두 실제로 동작한다(§12, §13). 대체되는 것은 LLM 호출 지점 하나뿐이고, 실제 키가 확보되면 설정 변경만으로 전환된다(`docs/plans/plan.md` §12 참고).

### 테스트 실행

```bash
cd server
source .venv/bin/activate
pytest        # 209 passed
```
