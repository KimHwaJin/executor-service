import pytest

from executor.exceptions.execution import CodeExecutionError
from executor.runtime.collector import JupyterMessageCollector


def message(
    msg_type: str,
    content: dict,
    *,
    parent_id: str = "request-1",
) -> dict:
    return {
        "header": {"msg_type": msg_type},
        "parent_header": {"msg_id": parent_id},
        "metadata": {},
        "content": content,
    }


def test_collector_waits_for_reply_and_idle() -> None:
    collector = JupyterMessageCollector(
        request_msg_id="request-1",
        step_id="step-1",
    )
    collector.collect(
        message("stream", {"name": "stdout", "text": "hello\n"})
    )
    collector.collect(
        message(
            "execute_reply",
            {"status": "ok", "execution_count": 7, "payload": []},
        )
    )
    assert not collector.is_complete
    collector.collect(message("status", {"execution_state": "idle"}))

    result = collector.build_result()
    assert result.execution_count == 7
    assert result.outputs[0].text == "hello\n"


def test_collector_ignores_unrelated_messages() -> None:
    collector = JupyterMessageCollector(
        request_msg_id="request-1",
        step_id="step-1",
    )
    collector.collect(
        message(
            "status",
            {"execution_state": "idle"},
            parent_id="another-request",
        )
    )
    assert not collector.is_complete


def test_collector_converts_kernel_error() -> None:
    collector = JupyterMessageCollector(
        request_msg_id="request-1",
        step_id="step-1",
    )
    collector.collect(
        message(
            "error",
            {
                "ename": "ValueError",
                "evalue": "bad value",
                "traceback": ["line one", "line two"],
            },
        )
    )
    collector.collect(
        message(
            "execute_reply",
            {
                "status": "error",
                "ename": "ValueError",
                "evalue": "bad value",
                "traceback": ["line one", "line two"],
            },
        )
    )
    collector.collect(message("status", {"execution_state": "idle"}))

    with pytest.raises(CodeExecutionError) as raised:
        collector.build_result()
    assert raised.value.step_id == "step-1"
    assert raised.value.error_type == "ValueError"
    assert raised.value.traceback == "line one\nline two"

