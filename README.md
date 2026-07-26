# Executor Service

AI Agent가 생성한 Python Step을 Redis Stream으로 접수하고, 실행별 전용
Jupyter 커널에서 순차 실행한 뒤 Agent callback으로 완료를 알리는 FastAPI
서비스다.

```text
Agent → POST /executions → Redis Stream → Worker
      → Jupyter REST/WebSocket → Redis state → Agent callback
```

## 핵심 보장

- 제출 API는 실행을 기다리지 않고 `202 Accepted`를 반환한다.
- 실행 하나의 모든 Step은 같은 Jupyter 세션/커널을 공유한다.
- 코드 오류는 `FAILED`로 기록하고 Stream 메시지를 ACK한다.
- 인프라 오류는 ACK하지 않아 Pending 복구 대상으로 남긴다.
- Callback 실패는 코드 재실행을 유발하지 않으며 별도 상태로 기록한다.
- WebSocket 단절 시 살아 있을 수 있는 커널에 코드를 즉시 재전송하지 않는다.

## 로컬 실행

Python 3.11 이상과 Redis, Jupyter Server가 필요하다.

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e '.[dev]'
cp .env.example .env
uvicorn executor.main:app --reload
```

검증:

```bash
pytest
ruff check .
mypy
```

API:

- `POST /executions`
- `GET /executions/{execution_id}`
- `GET /health`
- `GET /health/ready`

운영 설계와 제한사항은 [`docs/architecture.md`](docs/architecture.md)에 정리돼
있다.

