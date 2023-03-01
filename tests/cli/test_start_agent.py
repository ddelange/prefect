import os
import signal
import sys
import tempfile

import anyio
import pytest

from prefect.settings import get_current_settings
from prefect.utilities.processutils import open_process

STARTUP_TIMEOUT = 20
SHUTDOWN_TIMEOUT = 20


@pytest.fixture(scope="function")
async def agent_process():
    """
    Runs an agent listening to all queues.
    Yields:
        The anyio.Process.
    """

    out = tempfile.TemporaryFile()  # capture output for test assertions

    # Will connect to the same database as normal test clients
    async with open_process(
        command=[
            "prefect",
            "agent",
            "start",
            "--match=",
        ],
        stdout=out,
        stderr=out,
        env={**os.environ, **get_current_settings().to_environment_variables()},
    ) as process:
        process.out = out

        for _ in range(20):
            await anyio.sleep(0.5)
            if out.tell() > 100:
                break

        assert out.tell() > 100, "The agent did not start up in time"

        # Yield to the consuming tests
        yield process

        # Then shutdown the process
        try:
            process.terminate()
        except ProcessLookupError:
            pass
        out.close()


class TestUvicornSignalForwarding:
    @pytest.mark.skipif(
        sys.platform == "win32",
        reason="SIGTERM is only used in non-Windows environments",
    )
    async def test_sigint_sends_sigint(self, agent_process):
        agent_process.send_signal(signal.SIGINT)
        with anyio.fail_after(SHUTDOWN_TIMEOUT):
            await agent_process.wait()
        agent_process.out.seek(0)
        out = agent_process.out.read().decode()

        assert "Sending SIGINT" in out, (
            "When sending a SIGINT, the main process should receive a SIGINT."
            f" Output:\n{out}"
        )
        assert "Agent stopped!" in out, (
            "When sending a SIGINT, the main process should shutdown gracefully."
            f" Output:\n{out}"
        )

    @pytest.mark.skipif(
        sys.platform == "win32",
        reason="SIGTERM is only used in non-Windows environments",
    )
    async def test_sigterm_sends_sigint(self, agent_process):
        agent_process.send_signal(signal.SIGTERM)
        with anyio.fail_after(SHUTDOWN_TIMEOUT):
            await agent_process.wait()
        agent_process.out.seek(0)
        out = agent_process.out.read().decode()

        assert "Sending SIGINT" in out, (
            "When sending a SIGTERM, the main process should receive a SIGINT."
            f" Output:\n{out}"
        )
        assert "Agent stopped!" in out, (
            "When sending a SIGTERM, the main process should shutdown gracefully."
            f" Output:\n{out}"
        )

    @pytest.mark.skipif(
        sys.platform == "win32",
        reason="SIGTERM is only used in non-Windows environments",
    )
    async def test_sigint_sends_sigint_then_sigkill(self, agent_process):
        agent_process.send_signal(signal.SIGINT)
        await anyio.sleep(0.002)  # some time needed for the recursive signal handler
        agent_process.send_signal(signal.SIGINT)
        with anyio.fail_after(SHUTDOWN_TIMEOUT):
            await agent_process.wait()
        agent_process.out.seek(0)
        out = agent_process.out.read().decode()

        assert (
            # either the main PID is still waiting for shutdown, so forwards the SIGKILL
            "Sending SIGKILL" in out
            # or SIGKILL came too late, and the main PID is already closing
            or "KeyboardInterrupt" in out
            or "Agent stopped!" in out
        ), (
            "When sending two SIGINT shortly after each other, the main process should"
            f" first receive a SIGINT and then a SIGKILL. Output:\n{out}"
        )

    @pytest.mark.skipif(
        sys.platform == "win32",
        reason="SIGTERM is only used in non-Windows environments",
    )
    async def test_sigterm_sends_sigint_then_sigkill(self, agent_process):
        agent_process.send_signal(signal.SIGTERM)
        await anyio.sleep(0.002)  # some time needed for the recursive signal handler
        agent_process.send_signal(signal.SIGTERM)
        with anyio.fail_after(SHUTDOWN_TIMEOUT):
            await agent_process.wait()
        agent_process.out.seek(0)
        out = agent_process.out.read().decode()

        assert (
            # either the main PID is still waiting for shutdown, so forwards the SIGKILL
            "Sending SIGKILL" in out
            # or SIGKILL came too late, and the main PID is already closing
            or "KeyboardInterrupt" in out
            or "Agent stopped!" in out
        ), (
            "When sending two SIGTERM shortly after each other, the main process should"
            f" first receive a SIGINT and then a SIGKILL. Output:\n{out}"
        )

    @pytest.mark.skipif(
        sys.platform != "win32",
        reason="CTRL_BREAK_EVENT is only defined in Windows",
    )
    async def test_sends_ctrl_break_win32(self, agent_process):
        agent_process.send_signal(signal.SIGINT)
        with anyio.fail_after(SHUTDOWN_TIMEOUT):
            await agent_process.wait()
        agent_process.out.seek(0)
        out = agent_process.out.read().decode()

        assert "Sending CTRL_BREAK_EVENT" in out, (
            "When sending a SIGINT, the main process should send a CTRL_BREAK_EVENT to"
            f" the uvicorn subprocess. Output:\n{out}"
        )
