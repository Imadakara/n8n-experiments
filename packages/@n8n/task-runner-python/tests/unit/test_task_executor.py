import pytest
import json
from unittest.mock import MagicMock

from src.task_executor import MULTIPROCESSING_CONTEXT, TaskExecutor
from src.pipe_reader import PipeReader
from src.errors import (
    InvalidPipeMsgLengthError,
    TaskCancelledError,
    TaskKilledError,
    TaskSubprocessFailedError,
)
from src.constants import SIGTERM_EXIT_CODE, SIGKILL_EXIT_CODE, PIPE_MSG_PREFIX_LENGTH
from src.message_types.pipe import (
    PipeResultMessage,
    PipeErrorMessage,
    TaskErrorInfo,
)


def framed_message(message: dict) -> bytes:
    message_json = json.dumps(message).encode("utf-8")
    return len(message_json).to_bytes(PIPE_MSG_PREFIX_LENGTH, "big") + message_json


class TestTaskExecutorProcessExitHandling:
    def test_sigterm_raises_task_cancelled_error(self):
        process = MagicMock()
        process.is_alive.return_value = False
        process.exitcode = SIGTERM_EXIT_CODE

        read_conn = MagicMock()
        write_conn = MagicMock()
        read_conn.recv_bytes.side_effect = EOFError()

        with pytest.raises(TaskCancelledError):
            TaskExecutor.execute_process(
                process=process,
                read_conn=read_conn,
                write_conn=write_conn,
                task_timeout=60,
                continue_on_fail=False,
            )

    def test_sigkill_raises_task_killed_error(self):
        process = MagicMock()
        process.is_alive.return_value = False
        process.exitcode = SIGKILL_EXIT_CODE

        read_conn = MagicMock()
        write_conn = MagicMock()
        read_conn.recv_bytes.side_effect = EOFError()

        with pytest.raises(TaskKilledError):
            TaskExecutor.execute_process(
                process=process,
                read_conn=read_conn,
                write_conn=write_conn,
                task_timeout=60,
                continue_on_fail=False,
            )

    def test_other_non_zero_exit_code_raises_task_subprocess_failed_error(self):
        process = MagicMock()
        process.is_alive.return_value = False
        process.exitcode = -1  # Some other error code

        read_conn = MagicMock()
        write_conn = MagicMock()
        read_conn.recv_bytes.side_effect = EOFError()

        with pytest.raises(TaskSubprocessFailedError) as exc_info:
            TaskExecutor.execute_process(
                process=process,
                read_conn=read_conn,
                write_conn=write_conn,
                task_timeout=60,
                continue_on_fail=False,
            )

        assert exc_info.value.exit_code == -1

    def test_zero_exit_code_with_empty_pipe_raises_task_result_read_error(self):
        from src.errors import TaskResultReadError

        process = MagicMock()
        process.is_alive.return_value = False
        process.exitcode = 0

        read_conn = MagicMock()
        write_conn = MagicMock()
        read_conn.recv_bytes.side_effect = EOFError()

        with pytest.raises(TaskResultReadError):
            TaskExecutor.execute_process(
                process=process,
                read_conn=read_conn,
                write_conn=write_conn,
                task_timeout=60,
                continue_on_fail=False,
            )


class TestTaskExecutorPipeCommunication:
    def test_successful_result_communication(self):
        result_data: PipeResultMessage = {
            "result": [{"json": {"foo": "bar"}}],
            "print_args": [],
        }
        result_json = json.dumps(result_data).encode("utf-8")

        process = MagicMock()
        process.is_alive.return_value = False
        process.exitcode = 0

        read_conn = MagicMock()
        write_conn = MagicMock()
        read_conn.recv_bytes.return_value = (
            len(result_json).to_bytes(PIPE_MSG_PREFIX_LENGTH, "big") + result_json
        )

        result, print_args, size = TaskExecutor.execute_process(
            process=process,
            read_conn=read_conn,
            write_conn=write_conn,
            task_timeout=60,
            continue_on_fail=False,
        )

        assert result == [{"json": {"foo": "bar"}}]
        assert print_args == []
        assert size == len(result_json)

    def test_successful_error_communication(self):
        from src.errors import TaskRuntimeError

        error_info: TaskErrorInfo = {
            "message": "Test error",
            "description": "",
            "stack": "traceback...",
            "stderr": "",
        }
        error_data: PipeErrorMessage = {
            "error": error_info,
            "print_args": [],
        }
        error_json = json.dumps(error_data).encode("utf-8")

        process = MagicMock()
        process.is_alive.return_value = False
        process.exitcode = 0

        read_conn = MagicMock()
        write_conn = MagicMock()
        read_conn.recv_bytes.return_value = (
            len(error_json).to_bytes(PIPE_MSG_PREFIX_LENGTH, "big") + error_json
        )

        with pytest.raises(TaskRuntimeError) as exc_info:
            TaskExecutor.execute_process(
                process=process,
                read_conn=read_conn,
                write_conn=write_conn,
                task_timeout=60,
                continue_on_fail=False,
            )

        assert str(exc_info.value) == "Test error"
        assert exc_info.value.stack_trace == "traceback..."


class TestTaskExecutorLowLevelIO:
    def test_read_pipe_message(self):
        message = {"result": [{"json": {"foo": "bar"}}], "print_args": []}
        message_json = json.dumps(message).encode("utf-8")
        read_conn = MagicMock()
        read_conn.recv_bytes.return_value = framed_message(message)

        result, size = PipeReader._read_pipe_message(read_conn)

        assert result == message_json
        assert size == len(message_json)

    def test_read_pipe_message_rejects_short_payload(self):
        read_conn = MagicMock()
        read_conn.recv_bytes.return_value = b"bad"

        with pytest.raises(InvalidPipeMsgLengthError):
            PipeReader._read_pipe_message(read_conn)

    def test_read_pipe_message_rejects_invalid_declared_length(self):
        read_conn = MagicMock()
        read_conn.recv_bytes.return_value = (0).to_bytes(PIPE_MSG_PREFIX_LENGTH, "big")

        with pytest.raises(InvalidPipeMsgLengthError):
            PipeReader._read_pipe_message(read_conn)

    def test_read_pipe_message_rejects_length_mismatch(self):
        read_conn = MagicMock()
        read_conn.recv_bytes.return_value = (10).to_bytes(
            PIPE_MSG_PREFIX_LENGTH, "big"
        ) + b"short"

        with pytest.raises(InvalidPipeMsgLengthError):
            PipeReader._read_pipe_message(read_conn)

    def test_send_pipe_message(self):
        write_conn = MagicMock()

        TaskExecutor._send_pipe_message(write_conn, b"test data")

        write_conn.send_bytes.assert_called_once_with(
            len(b"test data").to_bytes(PIPE_MSG_PREFIX_LENGTH, "big") + b"test data"
        )

    def test_send_pipe_message_propagates_send_failure(self):
        write_conn = MagicMock()
        write_conn.send_bytes.side_effect = OSError("Write failed")

        with pytest.raises(OSError, match="Write failed"):
            TaskExecutor._send_pipe_message(write_conn, b"test data")

    def test_live_multiprocessing_pipe_round_trip(self):
        try:
            read_conn, write_conn = MULTIPROCESSING_CONTEXT.Pipe(duplex=False)
        except PermissionError as e:
            pytest.skip(f"multiprocessing pipe creation is blocked: {e}")

        try:
            TaskExecutor._send_pipe_message(
                write_conn, b'{"print_args":[],"result":[]}'
            )
            data, size = PipeReader._read_pipe_message(read_conn)
        finally:
            read_conn.close()
            write_conn.close()

        assert data == b'{"print_args":[],"result":[]}'
        assert size == len(data)
