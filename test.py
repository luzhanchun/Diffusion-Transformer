import os
import sys
import time
import signal
import subprocess
from pathlib import Path

class Traffic:
    def __init__(self):
        self.p = None

    def stop_child_group(self, timeout: float = 3.0):
        if self.p.poll() is not None:
            return

        pgid = os.getpgid(self.p.pid)
        os.killpg(pgid, signal.SIGTERM)

        try:
            self.p.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            os.killpg(pgid, signal.SIGKILL)
            self.p.wait()

    def open_child(self):
        base_dir = Path(__file__).resolve().parent
        child_script = base_dir / "child.py"

        self.p = subprocess.Popen(
            [sys.executable, str(child_script), "--count", "100"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            preexec_fn=os.setsid,
        )
        print("Child started")

    def save(self):
        self.stop_child_group(3.0)
        print("[main] child group stopped", flush=True)
    def work(self):
        for i in range(5):
            time.sleep(1)
            print("[main] working")
        self.save()
if __name__ == "__main__":
    generator = Traffic()
    generator.open_child()
    generator.work()