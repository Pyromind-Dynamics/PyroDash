"""docker-rt fixes for SWE-bench harness eval capture + grading.

Problems under docker-rt:
1. eval.sh markers use ``: '>>>>> Start Test Output'`` (no stdout); with
   ``set -x`` the trace goes to stderr. docker-rt exec often drops stderr, so
   grading never sees markers → always ``patch_successfully_applied=False``.
2. ``exec_run_with_timeout`` may not demux/merge streams, so test logs are
   truncated or empty even when tests ran.

Fixes:
- rewrite markers to ``echo`` when writing ``eval.sh``
- run eval with ``2>&1`` and demux stdout+stderr
- grading fallback: parse whole log if markers missing
"""

from __future__ import annotations

import shlex
import threading
import time
from pathlib import Path
from typing import Any

_installed = False

_START = ">>>>> Start Test Output"
_END = ">>>>> End Test Output"

# docker-rt ignores exec -e / PATH; relink bare python → testbed (same as
# docker_rt_testbed_exec.sh). Keep free of `#` / `name()` — not needed here
# because this string is assembled in Python, not parsed by docker-rt first.
_TB_PY = "/opt/miniconda3/envs/testbed/bin/python"
_LN_PREFIX = (
    f"ln -sfn {_TB_PY} /opt/miniconda3/bin/python; "
    f"ln -sfn {_TB_PY} /opt/miniconda3/bin/python3; "
    f"ln -sfn {_TB_PY} /opt/miniconda3/bin/python3.9; "
    f"ln -sfn {_TB_PY} /opt/miniconda3/bin/python3.10; "
    f"ln -sfn {_TB_PY} /opt/miniconda3/bin/python3.11; "
    f"ln -sfn {_TB_PY} /opt/miniconda3/bin/python3.12; "
)



def fix_eval_script_markers(script: str) -> str:
    """Send harness markers to stdout (not stderr via set -x)."""
    if not isinstance(script, str):
        return script
    out = script
    for marker in (_START, _END):
        # swebench emits: : '>>>>> Start Test Output'
        out = out.replace(f": '{marker}'", f"echo '{marker}'")
        out = out.replace(f': "{marker}"', f'echo "{marker}"')
    return out


def _patch_eval_sh_write() -> None:
    _orig = Path.write_text

    def write_text(self: Path, data: Any, *args: Any, **kwargs: Any) -> int:
        if self.name == "eval.sh" and isinstance(data, str):
            data = fix_eval_script_markers(data)
        return _orig(self, data, *args, **kwargs)

    Path.write_text = write_text  # type: ignore[method-assign,assignment]


def _patch_exec_run_with_timeout() -> None:
    import swebench.harness.docker_utils as docker_utils
    import swebench.harness.run_evaluation as run_evaluation

    def exec_run_with_timeout(container, cmd, timeout: int | None = 60):
        exec_result = b""
        exec_id = None
        exception = None
        timed_out = False

        # Merge stderr into the captured stream (docker-rt often omits stderr).
        # Use /bin/bash -c (not -lc): after python→testbed relink, login shells
        # break conda hooks that still expect base python.
        if isinstance(cmd, str):
            cmd_list = ["/bin/bash", "-c", f"{_LN_PREFIX}{cmd} 2>&1"]
        elif isinstance(cmd, (list, tuple)):
            cmd_list = [
                "/bin/bash",
                "-c",
                f"{_LN_PREFIX}{shlex.join(list(cmd))} 2>&1",
            ]
        else:
            cmd_list = cmd


        def run_command():
            nonlocal exec_result, exec_id, exception
            try:
                exec_id = container.client.api.exec_create(container.id, cmd_list)["Id"]
                try:
                    exec_stream = container.client.api.exec_start(
                        exec_id, stream=True, demux=True
                    )
                except TypeError:
                    exec_stream = container.client.api.exec_start(exec_id, stream=True)
                for chunk in exec_stream:
                    if chunk is None:
                        continue
                    if isinstance(chunk, tuple):
                        out, err = chunk
                        if out:
                            exec_result += out
                        if err:
                            exec_result += err
                    else:
                        exec_result += chunk
            except Exception as e:
                exception = e

        thread = threading.Thread(target=run_command)
        start_time = time.time()
        thread.start()
        thread.join(timeout)

        if exception:
            raise exception

        if thread.is_alive():
            if exec_id is not None:
                try:
                    exec_pid = container.client.api.exec_inspect(exec_id)["Pid"]
                    container.exec_run(f"kill -TERM {exec_pid}", detach=True)
                except Exception:
                    pass
            timed_out = True
        end_time = time.time()
        try:
            text = exec_result.decode()
        except Exception:
            text = exec_result.decode("utf-8", errors="replace")
        return text, timed_out, end_time - start_time

    docker_utils.exec_run_with_timeout = exec_run_with_timeout  # type: ignore[assignment]
    # run_evaluation imported the symbol by name — patch both.
    run_evaluation.exec_run_with_timeout = exec_run_with_timeout  # type: ignore[assignment]


def _patch_get_logs_eval() -> None:
    import swebench.harness.grading as grading
    from swebench.harness.constants import (
        APPLY_PATCH_FAIL,
        END_TEST_OUTPUT,
        RESET_FAILED,
        START_TEST_OUTPUT,
        TESTS_ERROR,
        TESTS_TIMEOUT,
    )
    from swebench.harness.log_parsers import MAP_REPO_TO_PARSER

    def get_logs_eval(test_spec, log_fp: str):
        log_parser = MAP_REPO_TO_PARSER[test_spec.repo]

        with open(log_fp) as f:
            content = f.read()

        bad_codes = list(
            filter(
                lambda x: x in content,
                [APPLY_PATCH_FAIL, RESET_FAILED, TESTS_ERROR, TESTS_TIMEOUT],
            )
        )
        if bad_codes:
            return {}, False

        if START_TEST_OUTPUT in content and END_TEST_OUTPUT in content:
            test_content = content.split(START_TEST_OUTPUT)[1].split(END_TEST_OUTPUT)[0]
            status_map = log_parser(test_content, test_spec)
            if not status_map:
                status_map = log_parser(content, test_spec)
            return status_map, True

        # docker-rt: markers often missing; still try to grade from full log.
        if content.strip():
            status_map = log_parser(content, test_spec)
            if status_map:
                return status_map, True

        return {}, False

    grading.get_logs_eval = get_logs_eval  # type: ignore[assignment]


def install() -> None:
    global _installed
    if _installed:
        return
    _patch_eval_sh_write()
    # Import harness modules before patching symbols they bind.
    import swebench.harness.docker_utils  # noqa: F401
    import swebench.harness.run_evaluation  # noqa: F401
    import swebench.harness.grading  # noqa: F401

    _patch_exec_run_with_timeout()
    _patch_get_logs_eval()
    _installed = True
    print(
        "[harness_docker_rt_fix] installed (eval markers→stdout, exec 2>&1+demux, "
        "testbed python relink, grading fallback without markers)",
        flush=True,
    )
