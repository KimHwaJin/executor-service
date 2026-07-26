# Executor Service 아키텍처

## 흐름

```text
LangGraph Agent
  → Executor API (즉시 202)
  → Redis Stream / Consumer Group
  → Executor Worker
  → 실행별 Jupyter Session + Kernel
  → 같은 Kernel에서 Step 순차 실행
  → Redis 최종 상태
  → Agent Callback
```

## 상태와 ACK

```text
QUEUED → RUNNING → SUCCEEDED | FAILED
```

- 성공과 사용자 코드 실패는 최종 상태 및 callback 상태를 기록한 뒤 ACK한다.
- Redis/Jupyter 연결 장애처럼 처리를 완결하지 못한 오류는 ACK하지 않는다.
- Callback 전달 실패는 실행 실패와 분리한다. 실패 정보를 저장한 뒤 실행
  Stream은 ACK하므로 사용자 코드를 다시 실행하지 않는다.

## Redis

- Stream: `execution:commands`
- Consumer Group: `execution-workers`
- 상태: `execution:{execution_id}`
- `SET NX`와 `XADD`는 Lua script 하나로 실행해 제출을 원자화한다.
- 운영에서는 AOF, `appendfsync everysec`, `maxmemory-policy noeviction`을
  권장한다.

## Jupyter

- 논리 환경 `ANALYSIS`, `MODELING`은 미리 설치한 kernelspec에 매핑한다.
- 실행마다 새 세션과 커널을 만든다.
- `execute_reply`와 동일 요청의 `status: idle`을 모두 받은 때 Step이 끝난다.
- WebSocket은 legacy JSON과 Jupyter v1 binary frame을 처리한다.
- WebSocket이 끊어지면 커널이 계속 계산 중일 수 있어 메시지를 Pending에
  남긴다. 자동 재전송은 금지한다.
- 여러 Jupyter replica를 단일 무작위 Service 뒤에 두면 세션 생성과
  WebSocket이 다른 Pod로 갈 수 있다. replica 1을 사용하거나 실행별
  `jupyter_target` 고정 라우팅이 필요하다.

## 운영상 남은 한계

- Redis의 실행 상태는 JSON 전체 덮어쓰기 방식이다. 동일 실행의 단일 Worker
  소유권을 전제로 하며, 다중 writer가 필요하면 CAS/Lua/Hash로 바꿔야 한다.
- 연결이 끊어진 기존 WebSocket 메시지는 재생되지 않는다. 커널 생존 여부는
  확인할 수 있지만 완료 결과를 완전히 복원하려면 Notebook/로그/결과를 외부
  저장소에 지속적으로 기록해야 한다.
- 하루짜리 함수의 내부 진행률 복구에는 사용자 코드 자체의 checkpoint가
  필요하다.
- 이미지, 모델, 대용량 로그는 Redis가 아니라 NFS/NAS/MinIO 등에 저장해야
  한다.
- Agent API 인증, callback 서명, 사용자별 커널 격리와 생성 코드 sandbox는
  배포 환경에서 추가해야 한다.

