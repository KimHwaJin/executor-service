# Executor Service 개선사항

이 문서는 Executor Service의 개선 작업을 지속적으로 관리하기 위한
작업 목록이다. 현재 필요한 개선사항과 완료된 개선사항을 한곳에서 추적하며,
구현 과정에서 새롭게 확인된 사항도 이 문서에 추가한다.

## 문서 운영 규칙

1. 코드 작업을 시작하기 전에 이 문서를 먼저 확인한다.
2. 작업하려는 항목의 현재 상태와 완료 조건을 확인한 뒤 구현한다.
3. 구현과 검증이 끝난 항목은 삭제하지 않고 `완료 목록`으로 옮긴다.
4. 완료 목록에는 완료일, 변경 내용, 검증 방법을 기록한다.
5. 작업 중 새로 발견한 문제나 후속 작업은 `개선 필요 목록`에 추가한다.
6. 하나의 변경으로 일부만 해결된 경우 항목을 완료 처리하지 않고 남은 범위를
   갱신한다.
7. 현재 진행 중인 작업의 인계 정보는 `docs/worklog.md`에 기록한다.
8. 구현 절차와 Git 동기화 방법은 `docs/workflow.md`를 따른다.
9. 우선순위는 다음 기준을 사용한다.
   - `P0`: 보안 사고, 데이터 손상, 원격 코드 실행 등 운영 전 필수 해결
   - `P1`: 실행 정확성, 복구 불능, Worker 중단 등 주요 장애 가능성
   - `P2`: 성능, 운영 편의성, 관측성, 자원 관리 문제
   - `P3`: 유지보수성, 개발 경험, 문서 및 정리 작업

## 상태 값

- `OPEN`: 아직 작업하지 않은 항목
- `IN_PROGRESS`: 현재 구현 또는 검증 중인 항목
- `BLOCKED`: 외부 결정이나 의존 작업이 필요한 항목

## 개선 필요 목록

### IMP-001 — 실행 API와 Jupyter 실행 환경 보안 강화

- 우선순위: `P0`
- 상태: `OPEN`
- 관련 위치:
  - `src/executor/api/executions.py`
  - `src/executor/schemas/command.py`
  - `src/executor/clients/agent.py`
- 문제:
  - 실행 제출 API에 인증과 인가가 없다.
  - 사용자 입력 `callback_url`로 서버가 직접 요청하므로 SSRF가 가능하다.
  - 생성된 코드를 실행하는 Jupyter kernel이 운영체제 수준으로 격리되지 않는다.
  - Callback 요청의 발신자를 검증할 서명이 없다.
- 개선 방향:
  - 제출 API에 인증, 인가, rate limit을 적용한다.
  - Callback 목적지를 allowlist 또는 서버 측 tenant 설정으로 제한한다.
  - Callback에 HMAC 서명, timestamp, event ID를 포함한다.
  - 실행별 컨테이너 또는 Pod 격리와 CPU, 메모리, 파일시스템, 네트워크 제한을
    적용한다.
  - Jupyter 인증 토큰을 필수 설정으로 전환한다.
- 완료 조건:
  - 인증되지 않은 실행 제출이 거부된다.
  - 사설망이나 허용되지 않은 Callback 목적지로 요청할 수 없다.
  - 서로 다른 실행이 파일시스템과 프로세스 자원을 공유하지 않는다.
  - Callback 수신 측에서 서명과 재전송 여부를 검증할 수 있다.

### IMP-002 — `stop_on_error=False` 상태 전이 수정

- 우선순위: `P1`
- 상태: `OPEN`
- 관련 위치:
  - `src/executor/services/execution.py`
  - `src/executor/repositories/redis_execution.py`
- 문제:
  - Step 실패 시 실행 전체를 즉시 `FAILED`로 확정하지만
    `stop_on_error=False`이면 다음 Step을 계속 실행한다.
  - 실행 중인 상태가 외부에는 완료 상태로 노출될 수 있다.
  - 실패 Callback이 실제 실행 종료 전에 전달될 수 있다.
  - `completed_at`과 `current_step_id`가 실제 종료 상태와 달라질 수 있다.
- 개선 방향:
  - Step 실패 기록과 실행 전체의 실패 확정을 분리한다.
  - 후속 Step 실행 중에는 실행 상태를 `RUNNING`으로 유지한다.
  - 모든 Step 처리 후 실패 여부를 집계해 한 번만 최종 상태를 기록한다.
- 완료 조건:
  - `stop_on_error=False` 실행은 마지막 Step이 끝날 때까지 terminal 상태가
    되지 않는다.
  - 최종 `completed_at`, `current_step_id`, Step 상태가 실제 실행 순서와
    일치한다.
  - 조기 Callback이 발생하지 않는 테스트가 추가된다.

### IMP-003 — Jupyter 세션 생성과 Redis binding 사이의 복구 공백 제거

- 우선순위: `P1`
- 상태: `OPEN`
- 관련 위치:
  - `src/executor/runtime/runner.py`
  - `src/executor/services/execution.py`
  - `src/executor/services/processor.py`
- 문제:
  - Jupyter 세션 생성 후 WebSocket 연결에 실패하면 Redis에
    `session_id`와 `kernel_id`가 기록되지 않는다.
  - 원격 세션은 보존될 수 있지만 실행은 `RUNNING` 상태로 남아 자동 복구할 수
    없다.
- 개선 방향:
  - 세션 생성 직후 Redis binding을 먼저 저장한다.
  - 코드가 전송되기 전의 연결 실패와 전송 후 연결 단절을 구분한다.
  - 코드 전송 전 실패는 세션을 정리하고 안전하게 재시도할 수 있게 한다.
  - 필요하면 `STARTING` 상태를 추가해 실행 시작 단계를 명시한다.
- 완료 조건:
  - 세션 생성 이후 모든 실패 경로에서 원격 세션 식별자가 Redis에 남거나
    세션이 안전하게 삭제된다.
  - 코드 전송 전 실패는 중복 실행 없이 자동 재시도할 수 있다.
  - 복구 불가능한 `RUNNING` 상태가 생성되지 않는 테스트가 추가된다.

### IMP-004 — 잘못된 Redis 메시지 격리와 Worker 생존 감시

- 우선순위: `P1`
- 상태: `OPEN`
- 관련 위치:
  - `src/executor/clients/redis.py`
  - `src/executor/workers/execution.py`
  - `src/executor/main.py`
  - `src/executor/api/health.py`
- 문제:
  - 잘못된 JSON 또는 schema validation 오류가 Worker 최상위 루프까지
    전파되어 Worker를 종료시킬 수 있다.
  - readiness는 Redis ping만 검사하므로 Worker가 종료되어도 정상으로 보일 수
    있다.
  - 처리할 수 없는 메시지를 격리하는 DLQ가 없다.
- 개선 방향:
  - 메시지 단위 parsing과 validation 오류를 분리해 처리한다.
  - 잘못된 메시지는 원본 payload와 오류를 DLQ에 저장하고 ACK한다.
  - Worker task 종료를 감시하고 readiness 및 metric에 반영한다.
  - 예상하지 못한 Worker 종료에 대한 재시작 정책을 정의한다.
- 완료 조건:
  - poison message 이후에도 정상 메시지가 계속 처리된다.
  - 잘못된 메시지를 DLQ에서 조회할 수 있다.
  - Worker가 종료되면 readiness가 실패한다.

### IMP-005 — 장시간 실행을 위한 heartbeat와 Pending 복구 개선

- 우선순위: `P1`
- 상태: `OPEN`
- 관련 위치:
  - `src/executor/services/recovery.py`
  - `src/executor/workers/execution.py`
  - `src/executor/repositories/redis_execution.py`
  - `src/executor/config/settings.py`
- 문제:
  - Step 기본 timeout은 최대 이틀이지만 Pending idle 기준은 기본 60초다.
  - 실행 중 Redis PEL idle time과 상태의 `heartbeat_at`이 주기적으로
    갱신되지 않는다.
  - 정상 실행 메시지도 stale message로 claim되어 Consumer 소유권이 반복해서
    이동할 수 있다.
  - Pending 항목을 한 batch 처리할 때마다 claim interval을 기다려 대량 복구가
    느리다.
- 개선 방향:
  - 실행 중 heartbeat 또는 lease를 주기적으로 갱신한다.
  - PEL idle time뿐 아니라 실행 heartbeat 만료를 함께 확인한다.
  - claim cursor가 끝에 도달할 때까지 Pending page를 연속 처리한다.
  - heartbeat 간격, lease 만료, claim idle 설정의 관계를 검증한다.
- 완료 조건:
  - 정상적인 장시간 실행은 다른 Worker가 복구 대상으로 처리하지 않는다.
  - Worker 장애 후 lease가 만료되면 다른 Worker가 실행을 인계한다.
  - 여러 batch의 Pending 메시지를 interval마다 하나씩이 아니라 연속 복구한다.

### IMP-006 — 실행 출력과 Redis 상태 크기 제한

- 우선순위: `P1`
- 상태: `OPEN`
- 관련 위치:
  - `src/executor/clients/jupyter.py`
  - `src/executor/runtime/collector.py`
  - `src/executor/repositories/redis_execution.py`
- 문제:
  - WebSocket frame과 실행 출력의 크기 및 개수 제한이 없다.
  - 모든 출력이 Worker 메모리에 누적되고 Redis 상태에 포함된다.
  - 대량 출력으로 Worker 메모리, Redis, 상태 API, Callback이 동시에 영향을
    받을 수 있다.
- 개선 방향:
  - WebSocket frame, Step 출력 byte, output 개수의 상한을 설정한다.
  - 한도 초과 출력은 잘라내고 `truncated` 정보를 저장한다.
  - 이미지, 모델, 대형 로그는 object storage에 저장하고 Redis에는 참조만
    기록한다.
- 완료 조건:
  - 설정된 출력 한도를 초과해도 Worker 메모리와 Redis 상태 크기가 제한된다.
  - 결과 사용자가 출력 생략 또는 잘림 여부를 확인할 수 있다.

### IMP-007 — Redis 제출의 실패 원자성과 orphan 상태 복구

- 우선순위: `P2`
- 상태: `OPEN`
- 관련 위치:
  - `src/executor/clients/redis.py`
  - `src/executor/services/submission.py`
- 문제:
  - Lua script가 다른 명령의 개입은 막지만 실행 중 오류에 대한 rollback은
    제공하지 않는다.
  - `SET` 이후 `XADD`가 실패하면 상태만 존재하고 Stream command가 없는
    orphan 실행이 생길 수 있다.
- 개선 방향:
  - Stream key type 등 실패 가능한 조건을 쓰기 전에 검증한다.
  - `QUEUED` 상태와 Stream command의 불일치를 탐지하는 reconciliation을
    추가한다.
  - Redis Cluster를 사용할 경우 두 key의 hash slot 전략도 정의한다.
- 완료 조건:
  - 제출 도중 실패한 실행이 자동으로 재등록되거나 명시적인 실패 상태가 된다.
  - 상태만 남아 이후 제출이 계속 `409`로 거부되는 경우가 없다.

### IMP-008 — Redis timeout 설정 분리

- 우선순위: `P2`
- 상태: `OPEN`
- 관련 위치:
  - `src/executor/clients/redis.py`
  - `src/executor/config/settings.py`
- 문제:
  - Redis connect timeout과 socket read timeout이 같은 값으로 사용된다.
  - 기본 socket timeout 5초와 Stream block 5초가 같아 정상적인 빈 poll도
    timeout 경계에 걸릴 수 있다.
- 개선 방향:
  - connect, command, blocking read timeout을 각각 설정한다.
  - blocking read timeout은 `block_ms`보다 충분히 크게 설정한다.
- 완료 조건:
  - 메시지가 없는 정상 poll에서 timeout 오류 로그가 발생하지 않는다.
  - Redis 연결 장애는 설정된 시간 안에 감지된다.

### IMP-009 — Redis 데이터 보관과 정리 정책

- 우선순위: `P2`
- 상태: `OPEN`
- 관련 위치:
  - `src/executor/clients/redis.py`
  - `src/executor/repositories/redis_execution.py`
- 문제:
  - Stream과 실행 상태 key에 명시적인 보관 기한이나 최대 크기가 없다.
  - 장기 운영 시 Redis 사용량이 계속 증가한다.
- 개선 방향:
  - Stream `MAXLEN` 또는 완료 메시지 정리 정책을 도입한다.
  - terminal 상태 key에 업무 요구사항에 맞는 TTL을 설정한다.
  - 감사 및 장기 보관이 필요한 결과는 별도 저장소로 이동한다.
- 완료 조건:
  - 예상 처리량을 기준으로 Redis 최대 사용량을 계산할 수 있다.
  - 보관 기간이 지난 실행과 Stream 메시지가 자동으로 정리된다.

### IMP-010 — 실행 결과 집계 계약 정의

- 우선순위: `P2`
- 상태: `OPEN`
- 관련 위치:
  - `src/executor/services/execution.py`
  - `src/executor/schemas/state.py`
  - `src/executor/schemas/callback.py`
- 문제:
  - 각 Step 결과는 저장하지만 성공한 실행의 최상위 `result`는 비어 있다.
  - 상태 조회와 Callback 사용자가 어떤 값을 최종 결과로 사용해야 하는지
    명확하지 않다.
- 개선 방향:
  - 마지막 Step 결과, 전체 Step 결과, 명시적 사용자 표현식 중 최종 결과
    계약을 선택한다.
  - 상태 API와 Callback이 같은 결과 계약을 사용하도록 한다.
- 완료 조건:
  - 성공 Callback과 상태 조회에서 문서화된 최종 결과를 확인할 수 있다.
  - 여러 Step과 결과가 없는 Step에 대한 테스트가 추가된다.

### IMP-011 — 빌드 재현성과 자동 검증 환경 구성

- 우선순위: `P3`
- 상태: `OPEN`
- 관련 위치:
  - `pyproject.toml`
  - `Dockerfile`
  - `tests/`
- 문제:
  - dependency lockfile과 고정된 base image digest가 없다.
  - 현재 테스트는 핵심 단위 흐름 위주이며 Redis와 Jupyter 장애 경계에 대한
    통합 검증이 부족하다.
- 개선 방향:
  - dependency lockfile과 재현 가능한 설치 절차를 추가한다.
  - CI에서 `pytest`, `ruff`, `mypy`를 필수 실행한다.
  - Redis와 Jupyter를 포함한 통합 테스트를 추가한다.
  - 상태 전이, Pending 복구, poison message, Callback 재시도, 종료 처리를
    집중적으로 검증한다.
- 완료 조건:
  - 동일한 revision에서 동일한 dependency 버전으로 빌드된다.
  - CI가 테스트, lint, type check 실패를 차단한다.
  - 주요 장애와 복구 경로가 자동 테스트로 재현된다.

### IMP-012 — 저장소 정리

- 우선순위: `P3`
- 상태: `IN_PROGRESS`
- 관련 위치:
  - `.gitignore`
- 문제:
  - macOS의 `.DS_Store`가 작업 디렉터리에 존재하지만 ignore 규칙이 없다.
- 개선 방향:
  - `.DS_Store`를 `.gitignore`에 추가하고 저장소에서 제외한다.
- 완료 조건:
  - `.DS_Store`가 변경 파일이나 배포 산출물에 포함되지 않는다.

## 완료 목록

아직 완료 처리된 개선사항이 없다.

완료된 항목은 다음 형식으로 이곳에 옮긴다.

```markdown
### IMP-NNN — 제목

- 우선순위: `P1`
- 완료일: `YYYY-MM-DD`
- 변경 내용:
  - 구현된 핵심 변경
- 검증:
  - 실행한 테스트와 확인 결과
- 후속 작업:
  - 없으면 `없음`
```
