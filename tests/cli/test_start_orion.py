import re
import signal
import subprocess
import sys
import time

import pytest

ORION_START_ARGS = [
    "prefect",
    "orion",
    "start",
    "--host",
    "0.0.0.0",
    "--port",
    "4200",
    "--log-level",
    "INFO",
]
SHUTDOWN_TIMEOUT = 10


class TestUvicornSignalForwarding:
    @pytest.mark.skipif(
        sys.platform == "win32",
        reason="SIGTERM is only used in non-Windows environments",
    )
    def test_sigint_sends_sigterm_then_sigkill(self):
        with subprocess.Popen(
            ORION_START_ARGS,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        ) as proc:
            out = []
            for line in proc.stdout:
                print(line)
                out.append(line)
                if b"Uvicorn running" in line:
                    break
            assert proc.returncode is None, "Orion should now be running"
            proc.send_signal(signal.SIGINT)
            time.sleep(0.1)
            proc.send_signal(signal.SIGINT)
            proc.wait(timeout=SHUTDOWN_TIMEOUT)
            out += proc.stdout
        out = "".join(line.decode() for line in out)

        assert proc.returncode == 0, "The main process should exit gracefully"
        assert re.search(
            r"(Sending SIGTERM)(.|\s)*(Sending SIGKILL)", out
        ), "When sending two SIGINT shortly after each other, the main process should first send a SIGTERM and then a SIGKILL to the uvicorn subprocess"

    @pytest.mark.skipif(
        sys.platform == "win32",
        reason="SIGTERM is only used in non-Windows environments",
    )
    def test_sigterm_sends_sigterm_then_sigkill(self):
        with subprocess.Popen(
            ORION_START_ARGS,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        ) as proc:
            out = []
            for line in proc.stdout:
                print(line)
                out.append(line)
                if b"Uvicorn running" in line:
                    break
            assert proc.returncode is None, "Orion should now be running"
            proc.send_signal(signal.SIGTERM)
            time.sleep(0.1)
            proc.send_signal(signal.SIGTERM)
            proc.wait(timeout=SHUTDOWN_TIMEOUT)
            out += proc.stdout
        out = "".join(line.decode() for line in out)

        assert proc.returncode == 0, "The main process should exit gracefully"
        assert re.search(
            r"(Sending SIGTERM)(.|\s)*(Sending SIGKILL)", out
        ), "When sending two SIGTERM shortly after each other, the main process should first send a SIGTERM and then a SIGKILL to the uvicorn subprocess"

    @pytest.mark.skipif(
        sys.platform == "win32",
        reason="SIGTERM is only used in non-Windows environments",
    )
    def test_sigterm_sends_sigterm_directly(self):
        with subprocess.Popen(
            ORION_START_ARGS,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        ) as proc:
            out = []
            for line in proc.stdout:
                print(line)
                out.append(line)
                if b"Uvicorn running" in line:
                    break
            assert proc.returncode is None, "Orion should now be running"
            proc.send_signal(signal.SIGTERM)
            proc.wait(timeout=SHUTDOWN_TIMEOUT)
            out += proc.stdout
        out = "".join(line.decode() for line in out)

        assert proc.returncode == 0, "The main process should exit gracefully"
        assert re.search(
            r"(Sending SIGTERM)(.|\s)*(Application shutdown complete)", out
        ), "When sending a SIGTERM, the main process should send a SIGTERM to the uvicorn subprocess"

    @pytest.mark.skipif(
        sys.platform != "win32",
        reason="CTRL_BREAK_EVENT is only defined in Windows",
    )
    def test_sends_ctrl_break_win32(self):
        with subprocess.Popen(
            ORION_START_ARGS,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        ) as proc:
            out = []
            for line in proc.stdout:
                print(line)
                out.append(line)
                if b"Uvicorn running" in line:
                    break
            assert proc.returncode is None, "Orion should now be running"
            proc.send_signal(signal.SIGINT)
            proc.wait(timeout=SHUTDOWN_TIMEOUT)
            out += proc.stdout
        out = "".join(line.decode() for line in out)

        assert proc.returncode == 0, "The main process should exit gracefully"
        assert re.search(
            r"Sending CTRL_BREAK_EVENT", out
        ), "When sending a SIGINT, the main process should send a CTRL_BREAK_EVENT to the uvicorn subprocess"
