import signal
import subprocess
import sys
import threading


def _stream(proc: subprocess.Popen, prefix: str) -> None:
    assert proc.stdout
    for line in iter(proc.stdout.readline, b""):
        sys.stdout.write(f"{prefix} {line.decode()}")
        sys.stdout.flush()


def main() -> None:
    api = subprocess.Popen(
        ["uvicorn", "src.main:app", "--reload", "--port", "8000"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    worker = subprocess.Popen(
        ["python", "-m", "src.workers.grade_submission.consumer"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )

    threading.Thread(target=_stream, args=(api, "[api]   "), daemon=True).start()
    threading.Thread(target=_stream, args=(worker, "[worker]"), daemon=True).start()

    def _shutdown(sig, frame) -> None:  # type: ignore[no-untyped-def]
        api.terminate()
        worker.terminate()
        sys.exit(0)

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    # encerra ambos se qualquer um morrer
    exited = api.wait()
    worker.terminate()
    sys.exit(exited)
