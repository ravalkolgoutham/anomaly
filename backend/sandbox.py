import tempfile
import time
from pathlib import Path

import docker
from docker.errors import DockerException


IMAGE = "gcc:latest"
TIME_LIMIT_SECONDS = 5


def execute_cpp_validation(cpp_code: str) -> dict:
    """Compile and run reviewed C++ in a restricted, temporary Docker container."""
    if not isinstance(cpp_code, str) or not cpp_code.strip():
        return {
            "status": "compile_error",
            "stdout": "",
            "stderr": "No C++ source code was provided.",
        }

    if len(cpp_code.encode("utf-8")) > 200_000:
        return {
            "status": "compile_error",
            "stdout": "",
            "stderr": "C++ source exceeds the 200 KB sandbox limit.",
        }

    client = None
    container = None
    timed_out = False

    try:
        client = docker.from_env()

        # The temporary source directory is mounted read-only in the container.
        with tempfile.TemporaryDirectory(prefix="cpp_validation_") as temp_dir:
            source_dir = Path(temp_dir)
            (source_dir / "main.cpp").write_text(cpp_code, encoding="utf-8")

            container = client.containers.create(
                image=IMAGE,
                command=[
                    "bash",
                    "-lc",
                    "g++ -std=c++17 -O2 -pipe /input/main.cpp "
                    "-o /tmp/main && echo __COMPILE_OK__ && /tmp/main",
                ],
                working_dir="/tmp",
                user="65534:65534",
                network_mode="none",
                read_only=True,
                cap_drop=["ALL"],
                security_opt=["no-new-privileges:true"],
                mem_limit="512m",
                nano_cpus=1_000_000_000,
                pids_limit=64,
                # exec is required to run the compiled program from /tmp.
                tmpfs={
                    "/tmp": "rw,exec,nosuid,nodev,size=64m,mode=1777"
                },
                volumes={
                    str(source_dir): {
                        "bind": "/input",
                        "mode": "ro",
                    }
                },
                detach=True,
            )

            container.start()
            deadline = time.monotonic() + TIME_LIMIT_SECONDS

            while time.monotonic() < deadline:
                container.reload()
                if container.status in ("exited", "dead"):
                    break
                time.sleep(0.1)
            else:
                timed_out = True
                try:
                    container.kill()
                except DockerException:
                    pass

            try:
                result = container.wait(timeout=3)
                exit_code = result.get("StatusCode", 1)
            except DockerException:
                exit_code = 1

            stdout = container.logs(stdout=True, stderr=False).decode(
                "utf-8", errors="replace"
            )
            stderr = container.logs(stdout=False, stderr=True).decode(
                "utf-8", errors="replace"
            )

            if timed_out:
                status = "timeout"
            elif "__COMPILE_OK__" not in stdout:
                status = "compile_error"
            elif exit_code != 0 or "ALL_TESTS_PASSED" not in stdout:
                status = "runtime_error"
                if exit_code == 0 and "ALL_TESTS_PASSED" not in stdout:
                    stderr += (
                        "\nProgram exited without printing ALL_TESTS_PASSED."
                    )
            else:
                status = "success"

            stdout = stdout.replace("__COMPILE_OK__\n", "").strip()

            return {
                "status": status,
                "stdout": stdout,
                "stderr": stderr.strip(),
            }

    except DockerException as exc:
        return {
            "status": "runtime_error",
            "stdout": "",
            "stderr": f"Docker error: {exc}",
        }
    finally:
        if container is not None:
            try:
                container.remove(force=True)
            except DockerException:
                pass
        if client is not None:
            client.close()