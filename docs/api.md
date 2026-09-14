# API 개요

상세 request/response 스키마는 [`openapi.yaml`](../openapi.yaml)이 단일 출처다. 이 문서는 사람이 빠르게 훑어보기 위한 요약이며, 스키마를 중복 정의하지 않는다.

## 엔드포인트 한눈에 보기

| Method | Path                        | 설명                                       |
| ------ | --------------------------- | ------------------------------------------ |
| GET    | `/health`                   | 헬스체크(인증 불필요)                      |
| POST   | `/auth/register`            | 회원가입                                   |
| POST   | `/auth/login`               | 로그인, httpOnly 쿠키 발급                 |
| POST   | `/auth/refresh`             | 액세스 토큰 재발급                         |
| GET    | `/rules`                    | 활성 법전 조항 목록                        |
| POST   | `/cases`                    | 사건 제출¹                                 |
| GET    | `/cases`                    | 본인 사건 목록(전과 기록)                  |
| GET    | `/cases/rule-frequency`     | 반복 조항 랭킹(자주 걸린 rule_id 상위 5개) |
| GET    | `/cases/{case_id}`          | 사건 상세(기소장·변론·판결·항소 전체)      |
| GET    | `/cases/{case_id}/progress` | 진행 상태 폴링용 경량 응답                 |
| POST   | `/cases/{case_id}/appeal`   | 항소 접수(1회 한정)                        |
| PATCH  | `/sentences/{sentence_id}`  | 형량 체크리스트 항목 완료 토글             |

¹ 현재 붙여넣기 모드만 구현됨. GitHub 링크 제출은 `docs/plans/develop_plan.md` M4 예정.

## 사건 라이프사이클 흐름

1. **제출** — `POST /cases`. 캐시 히트(완료된 동일 코드)면 200으로 기존 `case_id`를 바로 반환하고 새 사건을 만들지 않는다. 동일 코드가 이미 진행 중이면 200 + `in_progress:true`로 그 사건을 반환한다. 둘 다 아니면 202로 신규 사건을 큐에 넣는다(`status=QUEUED_PROSECUTION`).
2. **폴링** — `GET /cases/{case_id}/progress`를 2초 간격으로 호출한다. `status`가 검사→변호→판사 단계를 거치며 바뀌고, 종료 상태(`SENTENCED`/`DISMISSED`/`FAILED`)에 도달하면 폴링을 멈춘다.
3. **판결** — 종료 상태가 되면 `GET /cases/{case_id}`로 기소장·변론·판결(총평/개별 판정/형량)을 전부 받는다. `DISMISSED`/`FAILED`는 `judgment`가 없다.
4. **항소** — `status=SENTENCED`이고 `appeal_used=false`일 때만 `POST /cases/{case_id}/appeal` 가능. 접수 즉시 `appeal_used=true`로 확정되고(재심 성공/실패와 무관하게 소진), `status`가 `QUEUED_REJUDGMENT`로 바뀐다.
5. **재심** — 다시 `GET /cases/{case_id}/progress`로 폴링한다. 재심은 검사·변호 단계를 재실행하지 않고 판사 단계만 다시 돈다. 성공하면 `revision=1`로 확정, 실패하면 `revision=0`(원심)이 그대로 유지되고 `appeal_used=true`만 남는다(재항소 불가).
6. **형량 체크** — 판결 확정 후 언제든 `PATCH /sentences/{sentence_id}`로 형량 항목을 완료 처리한다. 사건 `status`와 무관하게 동작한다.

## 인증

- 모든 보호된 엔드포인트는 `access_token` 쿠키(httpOnly + Secure + SameSite=Lax)로 인증한다. 토큰을 응답 본문에 담아 반환하지 않는다.
- 로그인/재발급은 `Set-Cookie` 응답 헤더로 토큰을 내려준다.
- 상태 변경 요청(POST/PATCH/DELETE)은 커스텀 헤더 `X-CSRF-Protection: 1`을 함께 실어야 한다. 예외는 `/auth/register`, `/auth/login`(쿠키로 인증하는 요청이 아니라 위조할 기존 세션이 없음). Double Submit Cookie 대신 이 방식을 택한 근거는 `docs/plans/plan.md` §3(CSRF 대응 행) 참고.
- 남의 `case_id`/`sentence_id`를 조회하면 403이 아니라 404를 반환한다 — 리소스 존재 여부 자체를 노출하지 않기 위함이다.

## 에러 응답 표준 형태

모든 4xx/5xx 응답은 동일한 포맷을 따른다.

```json
{
  "error": {
    "code": "APPEAL_ALREADY_USED",
    "message": "이미 항소를 사용한 사건입니다.",
    "details": {}
  }
}
```

에러 코드 전체 목록과 각 코드가 어떤 상황·어떤 엔드포인트에서 나오는지는 `openapi.yaml`의 `ErrorCode` 스키마와 각 경로의 응답 예시에 정의되어 있다.

---

상세 스키마는 [`openapi.yaml`](../openapi.yaml) 참조.
