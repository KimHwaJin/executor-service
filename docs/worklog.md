# Executor Service 작업 기록

이 문서는 회사와 집 사이에서 현재 작업을 인계하기 위한 기록이다. 작업 상태는
Git commit과 함께 갱신하며, 자세한 개선 범위와 완료 조건은
`docs/improvements.md`를 기준으로 한다.

## 현재 작업

### IMP-012 — 저장소 정리 및 최초 GitHub 이전

- 상태: `IN_PROGRESS`
- 작업 branch: `main`
- 마지막 구현 commit: 아직 없음
- 마지막 작업 위치: 기존 환경
- 마지막 갱신일: `2026-07-26`
- 현재까지 완료:
  - 업로드 대상 파일과 민감 파일을 점검했다.
  - GitHub 원격 저장소가 비어 있음을 확인했다.
  - 로컬 전용 파일과 빌드 산출물의 ignore 규칙을 보강했다.
- 검증 결과:
  - 민감 파일 이름 점검: 실제 비밀 파일 없음
  - `git ls-remote`: 원격 reference 없음
- 다음 할 일:
  1. 로컬 Git 저장소를 초기화한다.
  2. 최초 commit을 생성하고 GitHub에 push한다.
  3. push 결과를 검증하고 IMP-012를 완료 목록으로 이동한다.
- 주의사항 또는 결정:
  - 최초 repository 구성 작업이므로 `main`에서 초기 commit을 생성한다.

작업을 시작하면 위 문장을 다음 형식으로 교체한다.

```markdown
### IMP-NNN — 제목

- 상태: `IN_PROGRESS`
- 작업 branch: `work/imp-NNN-short-description`
- 마지막 구현 commit: `<commit SHA 또는 아직 없음>`
- 마지막 작업 위치: `회사 | 집`
- 마지막 갱신일: `YYYY-MM-DD`
- 현재까지 완료:
  -
- 검증 결과:
  - 실행한 명령: 결과
  - 실행하지 못한 검증과 이유
- 다음 할 일:
  1.
- 주의사항 또는 결정:
  -
```

## 작업 기록

아직 기록된 작업이 없다.

작업을 다른 환경으로 인계하거나 완료할 때 다음 형식으로 최신 기록을 위에
추가한다.

```markdown
### YYYY-MM-DD — IMP-NNN — 작업 요약

- 작업 위치: `회사 | 집`
- branch: `work/imp-NNN-short-description`
- 마지막 구현 commit: `<commit SHA>`
- 변경 내용:
  -
- 검증:
  -
- 다음 작업:
  -
```

## 기록 규칙

1. 작업 위치를 옮기기 전에 현재 작업과 작업 기록을 갱신한다.
2. 마지막 구현 commit에는 코드 또는 설정 변경을 담은 commit SHA를 기록한다.
   인계 문서만 변경한 commit SHA는 원격 branch 이력에서 확인한다.
3. 실행하지 않은 테스트는 `미실행`과 사유를 적는다.
4. 중요한 설계 결정은 작업 기록에만 두지 않고 적절한 장기 문서에도 반영한다.
5. 완료된 작업은 현재 작업에서 제거하고 작업 기록에는 남긴다.
6. 민감 정보, token, password, 내부 주소는 기록하지 않는다.
