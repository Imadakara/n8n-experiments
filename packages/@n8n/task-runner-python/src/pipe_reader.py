import json
import threading
from typing import Protocol, cast

from src.errors import (
    InvalidPipeMsgContentError,
    InvalidPipeMsgLengthError,
)
from src.message_types.pipe import PipeMessage
from src.constants import PIPE_MSG_PREFIX_LENGTH


class PipeConnection(Protocol):
    def send_bytes(
        self, buf: bytes, offset: int = 0, size: int | None = None
    ) -> None: ...

    def recv_bytes(self, maxlength: int | None = None) -> bytes: ...

    def close(self) -> None: ...


class PipeReader(threading.Thread):
    """Background thread that reads result from pipe."""

    def __init__(self, read_conn: PipeConnection):
        super().__init__()
        self.read_conn = read_conn
        self.pipe_message: PipeMessage | None = None
        self.message_size: int | None = None  # bytes
        self.error: Exception | None = None

    def run(self):
        try:
            data, self.message_size = PipeReader._read_pipe_message(self.read_conn)
            parsed_msg = json.loads(data.decode("utf-8"))
            self.pipe_message = self._validate_pipe_message(parsed_msg)
        except Exception as e:
            self.error = e
        finally:
            self.read_conn.close()

    @staticmethod
    def _read_pipe_message(read_conn: PipeConnection) -> tuple[bytes, int]:
        """Read a length-prefixed JSON message from a multiprocessing connection."""

        framed_data = read_conn.recv_bytes()

        if len(framed_data) < PIPE_MSG_PREFIX_LENGTH:
            raise InvalidPipeMsgLengthError(len(framed_data))

        length_bytes = framed_data[:PIPE_MSG_PREFIX_LENGTH]
        message_size = int.from_bytes(length_bytes, "big")

        if message_size <= 0:
            raise InvalidPipeMsgLengthError(message_size)

        data = framed_data[PIPE_MSG_PREFIX_LENGTH:]

        if len(data) != message_size:
            raise InvalidPipeMsgLengthError(len(data))

        return data, message_size

    def _validate_pipe_message(self, msg) -> PipeMessage:
        if not isinstance(msg, dict):
            raise InvalidPipeMsgContentError(f"Expected dict, got {type(msg).__name__}")

        if "print_args" not in msg:
            raise InvalidPipeMsgContentError("Message missing 'print_args' key")

        if not isinstance(msg["print_args"], list):
            raise InvalidPipeMsgContentError("'print_args' must be a list")

        has_result = "result" in msg
        has_error = "error" in msg

        if not has_result and not has_error:
            raise InvalidPipeMsgContentError("Msg is missing 'result' or 'error' key")

        if has_result and has_error:
            raise InvalidPipeMsgContentError("Msg has both 'result' and 'error' keys")

        if has_error and not isinstance(msg["error"], dict):
            raise InvalidPipeMsgContentError("'error' must be a dict")

        return cast(PipeMessage, msg)
