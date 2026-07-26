# Repository working instructions

모든 코드 및 설정 작업을 시작하기 전에 다음 문서를 순서대로 확인한다.

1. `docs/improvements.md`
2. `docs/worklog.md`
3. `docs/workflow.md`

- 구현하려는 개선 항목의 상태와 완료 조건을 먼저 확인한다.
- 작업을 시작하면 해당 항목을 `IN_PROGRESS`로 갱신한다.
- 현재 작업의 branch, 마지막 commit, 검증 결과, 다음 할 일을
  `docs/worklog.md`에 기록한다.
- 회사와 집 사이에서 작업 위치를 옮기기 전에는 모든 필요한 파일을 commit하고
  push한다. `git stash`와 commit되지 않은 파일은 인계 수단으로 사용하지 않는다.
- 구현과 검증이 끝나면 항목을 삭제하지 말고 `완료 목록`으로 옮긴다.
- 완료한 작업은 `docs/worklog.md`의 현재 작업에서 제거하고 작업 기록에 남긴다.
- 작업 중 발견한 새로운 문제와 후속 작업은 `개선 필요 목록`에 새 항목으로
  추가한다.
- 일부만 해결한 항목은 완료 처리하지 않고 남은 범위와 완료 조건을 갱신한다.
- 작업 상태와 결정은 Git commit 또는 `docs/` 문서에 기록한다. GitHub Issue와
  Pull Request는 사용자가 명시적으로 요청하지 않는 한 작업 기록의 전제로
  사용하지 않는다.
- 공개된 branch를 force push하거나 공유 이력을 rewrite하지 않는다.
- `docs/architecture.md`의 기존 설계 내용은 별도 요청 없이 변경하지 않는다.
