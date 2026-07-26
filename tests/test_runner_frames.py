import json
import struct

from executor.runtime.runner import (
    decode_message_frame,
    encode_v1_message,
)


def sample_message() -> dict:
    return {
        "channel": "iopub",
        "header": {"msg_id": "message-1", "msg_type": "stream"},
        "parent_header": {"msg_id": "request-1"},
        "metadata": {},
        "content": {"name": "stdout", "text": "안녕"},
        "buffers": [b"\x00\x01"],
    }


def test_v1_binary_round_trip() -> None:
    decoded = decode_message_frame(encode_v1_message(sample_message()))
    assert decoded["channel"] == "iopub"
    assert decoded["content"]["text"] == "안녕"
    assert decoded["buffers"] == [b"\x00\x01"]


def test_text_frame() -> None:
    payload = sample_message()
    payload["buffers"] = []
    decoded = decode_message_frame(json.dumps(payload))
    assert decoded["header"]["msg_type"] == "stream"


def test_legacy_binary_frame() -> None:
    payload = sample_message()
    payload.pop("buffers")
    parts = [json.dumps(payload).encode(), b"binary"]
    header_size = 4 * (len(parts) + 1)
    offsets = [header_size]
    for part in parts[:-1]:
        offsets.append(offsets[-1] + len(part))
    frame = (
        struct.pack("!I", len(parts))
        + struct.pack(f"!{len(parts)}I", *offsets)
        + b"".join(parts)
    )
    decoded = decode_message_frame(frame)
    assert decoded["content"]["name"] == "stdout"
    assert decoded["buffers"] == [b"binary"]

