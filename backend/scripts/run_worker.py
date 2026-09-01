"""
AgentOS Phase 15 — Standalone Worker Runner Script.

Usage:
    python backend/scripts/run_worker.py [--id WORKER_ID] [--caps CAP1,CAP2] [--max-tasks N]
"""

from __future__ import annotations

import argparse
import os
import signal
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.services.worker_runtime import WorkerRuntime


def main():
    parser = argparse.ArgumentParser(description="AgentOS Distributed Worker Daemon")
    parser.add_argument("--id", default=os.getenv("WORKER_ID"), help="Unique worker identifier")
    parser.add_argument(
        "--caps",
        default=os.getenv("WORKER_CAPABILITIES", "CODING,TESTING,RESEARCH,DEBUGGING,DEVOPS,CYBERSECURITY"),
        help="Comma-separated capabilities",
    )
    parser.add_argument(
        "--max-tasks",
        type=int,
        default=int(os.getenv("WORKER_MAX_TASKS", "2")),
        help="Maximum concurrent tasks for this worker",
    )
    args = parser.parse_args()

    capabilities = [c.strip() for c in args.caps.split(",") if c.strip()]

    print("==================================================")
    print("  AgentOS Phase 15 Distributed Worker Daemon")
    print(f"  Worker ID:    {args.id or 'auto-generated'}")
    print(f"  Capabilities: {capabilities}")
    print(f"  Max Tasks:    {args.max_tasks}")
    print("==================================================")

    runtime = WorkerRuntime(
        worker_id=args.id,
        capabilities=capabilities,
        max_tasks=args.max_tasks,
    )

    def handle_signal(sig, frame):
        print(f"\n[INFO] Received signal {sig}. Draining worker...")
        runtime.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    runtime.start()
    print("[INFO] Worker is active and listening for tasks. Press Ctrl+C to exit.")

    try:
        while True:
            time.sleep(1.0)
    except KeyboardInterrupt:
        handle_signal(signal.SIGINT, None)


if __name__ == "__main__":
    main()

