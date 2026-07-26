# Executor Service 작업 절차

이 프로젝트는 회사와 집의 개발 환경을 번갈아 사용한다. GitHub는 Git
repository의 원격 저장소로만 사용하며, 작업 상태와 결정은 Git commit과
`docs/` 문서에 기록한다. GitHub Issue와 Pull Request는 기본 작업 절차에
포함하지 않는다.

## 기록의 기준

| 대상 | 기록 위치 |
| --- | --- |
| 앞으로 해결할 문제와 완료 조건 | `docs/improvements.md` |
| 현재 작업 위치와 다음 할 일 | `docs/worklog.md` |
| 설계와 운영 원칙 | `docs/architecture.md` |
| 실제 코드 및 문서 변경 | Git commit |
| 원격 동기화와 백업 | GitHub repository |

문서와 commit에 없는 작업 상태는 다른 환경으로 인계되지 않은 것으로 본다.
`git stash`, commit되지 않은 파일, IDE의 로컬 메모는 인계 수단으로 사용하지
않는다.

## Branch 원칙

- `main`은 완료되고 검증된 상태를 유지한다.
- 개선 작업은 개선사항 ID를 포함한 branch에서 진행한다.
- branch 이름은 `work/imp-NNN-short-description` 형식을 사용한다.
- 작업 도중 장소를 옮길 때도 같은 branch를 push하고 다른 환경에서 이어받는다.
- Pull Request 없이 완료할 때는 로컬에서 `main`에 merge한 뒤 push한다.
- 공개된 branch는 force push하거나 rebase로 공유 이력을 변경하지 않는다.

예시:

```text
main
└── work/imp-002-stop-on-error
```

문서 정리처럼 개선사항 ID가 없는 작업은 `work/docs-short-description` 형식을
사용한다.

## 작업 시작 절차

1. 로컬 변경이 남아 있는지 확인한다.
2. 원격 정보를 갱신한다.
3. 작업할 branch로 이동하고 fast-forward로 동기화한다.
4. `docs/improvements.md`, `docs/worklog.md`를 확인한다.
5. 개선 항목을 `IN_PROGRESS`로 변경하고 현재 작업 정보를 갱신한다.

```bash
git status
git fetch --prune origin
git switch work/imp-002-stop-on-error
git pull --ff-only origin work/imp-002-stop-on-error
```

`git status`가 깨끗하지 않으면 pull을 진행하기 전에 변경의 출처를 확인한다.
어느 환경의 변경인지 확실하지 않은 상태에서 reset, checkout, stash pop을
실행하지 않는다.

새 작업을 시작하는 경우:

```bash
git switch main
git pull --ff-only origin main
git switch -c work/imp-002-stop-on-error
```

## 작업 중 Commit 원칙

- commit 하나에는 설명 가능한 한 단위의 변경만 포함한다.
- commit 제목에 관련 개선사항 ID를 넣는다.
- 코드 변경과 그 변경으로 인해 갱신된 문서는 같은 commit에 포함할 수 있다.
- 실행되지 않은 검증을 실행한 것처럼 기록하지 않는다.
- 미완료 상태를 인계해야 하면 동작하지 않는 부분과 다음 할 일을
  `docs/worklog.md`에 명확히 기록한다.

예시:

```text
fix(IMP-002): Step 실패와 실행 실패 상태 전이를 분리
test(IMP-002): 계속 실행 모드의 조기 callback 회귀 테스트 추가
docs(IMP-002): 상태 전이 개선사항을 완료 목록으로 이동
```

## 작업 위치를 옮기기 전

회사에서 퇴근하거나 집에서 작업을 마칠 때 다음 절차를 수행한다.

1. 가능한 검증을 실행한다.
2. 코드와 관련 문서 변경을 먼저 commit한다.
3. 생성된 구현 commit ID를 확인한다.
4. `docs/worklog.md`에 구현 commit, 현재 상태, 다음 할 일을 기록한다.
5. 개선사항 상태와 남은 완료 조건을 갱신한다.
6. 인계 문서 변경을 commit하고 현재 branch를 push한다.
7. 작업 디렉터리와 원격 branch 상태를 확인한다.

```bash
git status
git add <변경한 파일>
git commit -m "fix(IMP-002): 실행 실패 상태 전이 수정"
git log -1 --oneline
git add docs/improvements.md docs/worklog.md
git commit -m "docs(IMP-002): 다음 작업 인계 기록"
git push -u origin work/imp-002-stop-on-error
git status
git log -1 --oneline
```

`docs/worklog.md`에는 첫 번째 구현 commit ID를 기록한다. 두 번째 인계 문서
commit은 자기 자신의 ID를 문서에 기록하지 않으며, 원격 branch의 최신 commit으로
확인한다. 작업 디렉터리가 깨끗하고 두 commit이 원격에 push된 것을 확인해야
인계가 끝난 것으로 본다.

## 개선 작업 완료 절차

1. 완료 조건과 관련 테스트를 확인한다.
2. `pytest`, `ruff check .`, `mypy` 등 가능한 검증을 실행한다.
3. `docs/improvements.md`의 항목을 `완료 목록`으로 옮긴다.
4. 완료일, 변경 내용, 검증 결과, 후속 작업을 기록한다.
5. `docs/worklog.md`의 현재 작업을 정리하고 작업 기록에 완료 내용을 추가한다.
6. 변경을 commit하고 작업 branch를 push한다.
7. 최신 `main`을 확인한 뒤 작업 branch를 merge하고 `main`을 push한다.

```bash
git switch main
git pull --ff-only origin main
git merge --no-ff work/imp-002-stop-on-error
git push origin main
```

merge가 fast-forward되지 않거나 충돌이 발생하면 자동으로 해결하려 하지 말고
두 branch의 변경 내용을 먼저 비교한다. merge 후 작업 branch 삭제 여부는
필요한 기록이 원격 `main`에 반영된 것을 확인한 뒤 결정한다.

## 비밀 정보와 환경별 설정

- `.env`, token, password, 인증서와 개인 경로는 commit하지 않는다.
- 공유해야 하는 설정 항목은 값 없이 `.env.example`에 추가한다.
- Python과 dependency 버전은 두 환경에서 동일하게 재현할 수 있도록
  version 파일과 lockfile로 관리한다.
- 대형 실행 결과와 로컬 캐시는 Git으로 동기화하지 않는다.
