import type { CaseStatus } from "@/lib/types";

type StageState = "PENDING" | "IN_PROGRESS" | "DONE" | "FAILED";

const STAGES = [
  {
    key: "PROSECUTION",
    label: "검사",
    description:
      "법전의 조항과 코드를 대조해 위반을 찾습니다. 조항에 없는 지적은 만들 수 없습니다.",
  },
  {
    key: "DEFENSE",
    label: "변호인",
    description:
      "각 기소에 대해 반박합니다. 맥락상 과한 지적을 걸러내는 단계입니다.",
  },
  {
    key: "JUDGMENT",
    label: "판사",
    description:
      "기소와 변론을 함께 보고 채택·감형·기각을 결정하고, 할 일을 정합니다.",
  },
] as const;

function stageStateFor(
  stageKey: (typeof STAGES)[number]["key"],
  status: CaseStatus,
  failedStage: string | null,
): StageState {
  const order: CaseStatus[] = [
    "QUEUED_PROSECUTION",
    "PROSECUTING",
    "QUEUED_DEFENSE",
    "DEFENDING",
    "QUEUED_JUDGMENT",
    "JUDGING",
  ];
  const stageIndex = { PROSECUTION: 0, DEFENSE: 1, JUDGMENT: 2 }[stageKey];
  const currentIndex = order.indexOf(status);

  if (status === "FAILED") {
    if (failedStage === stageKey) return "FAILED";
    const failedIndex = { PROSECUTION: 0, DEFENSE: 1, JUDGMENT: 2 }[
      failedStage as "PROSECUTION" | "DEFENSE" | "JUDGMENT"
    ];
    return failedIndex !== undefined && stageIndex < failedIndex
      ? "DONE"
      : "PENDING";
  }

  if (
    status === "SENTENCED" ||
    status === "DISMISSED" ||
    status === "REJUDGING" ||
    status === "QUEUED_REJUDGMENT"
  ) {
    return "DONE";
  }

  if (currentIndex === -1) return "PENDING";

  const stageQueuedIndex = stageIndex * 2;
  const stageActiveIndex = stageIndex * 2 + 1;

  if (currentIndex > stageActiveIndex) return "DONE";
  if (currentIndex === stageActiveIndex) return "IN_PROGRESS";
  if (currentIndex === stageQueuedIndex) return "PENDING";
  return "PENDING";
}

const ICON: Record<StageState, string> = {
  PENDING: "○",
  IN_PROGRESS: "◐",
  DONE: "✓",
  FAILED: "✕",
};

const ICON_STYLE: Record<StageState, string> = {
  PENDING: "border-border text-text-faint",
  IN_PROGRESS: "border-accent bg-accent/20 text-accent animate-pulse",
  DONE: "border-complete bg-complete/20 text-complete",
  FAILED: "border-danger bg-danger/20 text-danger",
};

const LABEL: Record<StageState, string> = {
  PENDING: "대기",
  IN_PROGRESS: "진행 중",
  DONE: "완료",
  FAILED: "실패",
};

export function ProgressStages({
  status,
  failedStage,
}: {
  status: CaseStatus;
  failedStage: string | null;
}) {
  return (
    <div>
      <div className="flex items-center">
        {STAGES.map((stage, idx) => {
          const state = stageStateFor(stage.key, status, failedStage);
          return (
            <div
              key={stage.key}
              className="flex flex-1 items-center last:flex-none"
            >
              <div className="flex flex-col items-center gap-2 text-center">
                <div
                  className={`flex h-12 w-12 items-center justify-center rounded border text-xl ${ICON_STYLE[state]}`}
                >
                  {ICON[state]}
                </div>
                <div className="font-semibold text-text">{stage.label}</div>
                <div
                  className={`text-xs ${
                    state === "IN_PROGRESS"
                      ? "text-accent"
                      : state === "FAILED"
                        ? "text-danger"
                        : "text-text-muted"
                  }`}
                >
                  {LABEL[state]}
                </div>
              </div>
              {idx < STAGES.length - 1 && (
                <div
                  className={`mx-2 h-px flex-1 ${
                    state === "DONE" ? "bg-complete" : "bg-border"
                  }`}
                />
              )}
            </div>
          );
        })}
      </div>

      <div className="mt-6 grid grid-cols-3 gap-4 text-center text-xs leading-relaxed text-text-muted">
        {STAGES.map((stage) => (
          <p key={stage.key}>{stage.description}</p>
        ))}
      </div>
    </div>
  );
}
