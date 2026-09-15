import { ApiError } from "./api";

/** docs/design.md 6.7 — 에러 화면의 해결 행동. 코드별 사용자 문구를 하나로 모아둔다. */
export function describeError(error: unknown): string {
  if (!(error instanceof ApiError)) {
    return "알 수 없는 오류가 발생했습니다. 다시 시도해 주세요.";
  }

  switch (error.code) {
    case "INVALID_REPO_URL":
      return "GitHub 파일 링크 형식이 아닙니다. 저장소의 파일 페이지에서 주소를 복사해 주세요. 예: https://github.com/owner/repo/blob/main/src/app.py";
    case "REPO_FILE_UNAVAILABLE":
      return "파일을 불러올 수 없습니다. 공개 저장소의 파일인지 확인해 주세요. 비공개 저장소는 지원하지 않습니다.";
    case "FETCH_RATE_LIMITED":
      return "링크 불러오기 횟수를 초과했습니다. 잠시 후 다시 시도하거나 코드를 직접 붙여넣어 주세요.";
    case "RATE_LIMITED": {
      const retryAfter = error.details?.retry_after_seconds;
      const hours =
        typeof retryAfter === "number" ? Math.ceil(retryAfter / 3600) : null;
      return hours
        ? `24시간 내 20건을 모두 사용했습니다. 약 ${hours}시간 후 다시 시도할 수 있습니다.`
        : "24시간 내 20건을 모두 사용했습니다.";
    }
    case "CODE_TOO_LONG":
      return "500줄 / 20,000자를 초과했습니다. 심사할 부분만 잘라 제출해 주세요.";
    case "EMPTY_CODE":
      return "코드가 비어 있습니다.";
    case "INVALID_LANGUAGE":
      return "언어를 선택해 주세요.";
    case "RETRIAL_BLOCKED":
      return "진행 중인 사건이 있어 재판을 새로 시작할 수 없습니다.";
    case "GITHUB_UNAVAILABLE":
      return "GitHub에서 파일을 가져오지 못했습니다. 잠시 후 다시 시도해 주세요.";
    case "REBUTTAL_TOO_SHORT":
      return "항소 사유는 20자 이상 입력해야 합니다.";
    case "APPEAL_ALREADY_USED":
      return "이미 항소를 사용한 사건입니다.";
    case "CASE_NOT_FOUND":
      return "사건을 찾을 수 없습니다.";
    case "INVALID_CREDENTIALS":
      return "이메일 또는 비밀번호가 올바르지 않습니다.";
    case "EMAIL_ALREADY_REGISTERED":
      return "이미 가입된 이메일입니다.";
    case "CSRF_CHECK_FAILED":
      return "요청 검증에 실패했습니다. 새로고침 후 다시 시도해 주세요.";
    case "NETWORK_ERROR":
      return error.message;
    default:
      return error.message || "심사에 실패했습니다. 다시 제출해 주세요.";
  }
}
