#!/usr/bin/env python3
"""
AgentPay All-in-One Development Launcher
Starts PostgreSQL (Docker), FastAPI Backend, and Vite Frontend concurrently.
"""

import os
import sys
import subprocess
import signal
import time
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = ROOT_DIR / "backend"
FRONTEND_DIR = ROOT_DIR / "frontend"


def check_docker():
    print("🐘 [1/4] Checking PostgreSQL Docker container...")
    try:
        subprocess.run(["docker", "compose", "up", "-d"], cwd=ROOT_DIR, check=True)
        print("✓ PostgreSQL is running on port 5432.")
    except Exception as e:
        print(f"⚠️ Warning: Could not run docker compose: {e}")
        print("  Make sure Docker Desktop is open and running.")


def check_backend_migrations():
    print("🐍 [2/4] Checking Backend virtualenv & database migrations...")
    venv_dir = BACKEND_DIR / ".venv"
    if not venv_dir.exists():
        print("  Creating Python virtual environment...")
        subprocess.run([sys.executable, "-m", "venv", ".venv"], cwd=BACKEND_DIR, check=True)
        pip_path = venv_dir / "bin" / "pip"
        subprocess.run([str(pip_path), "install", "-r", "requirements.txt"], cwd=BACKEND_DIR, check=True)

    alembic_path = venv_dir / "bin" / "alembic"
    if alembic_path.exists():
        subprocess.run([str(alembic_path), "upgrade", "head"], cwd=BACKEND_DIR, check=True)
        print("✓ Database schema is up-to-date.")


def check_frontend_deps():
    print("⚛️ [3/4] Checking Frontend dependencies...")
    node_modules = FRONTEND_DIR / "node_modules"
    if not node_modules.exists():
        print("  Running npm install in frontend...")
        subprocess.run(["npm", "install"], cwd=FRONTEND_DIR, check=True)
    print("✓ Frontend dependencies are ready.")


def main():
    print("=" * 65)
    print("       🛡️  AgentPay Full Stack Development Environment")
    print("=" * 65)

    check_docker()
    check_backend_migrations()
    check_frontend_deps()

    print("\n🚀 [4/4] Launching Backend & Frontend services...")

    venv_uvicorn = BACKEND_DIR / ".venv" / "bin" / "uvicorn"
    backend_cmd = [
        str(venv_uvicorn if venv_uvicorn.exists() else "uvicorn"),
        "app.main:app",
        "--reload",
        "--host",
        "127.0.0.1",
        "--port",
        "8000",
    ]

    frontend_cmd = ["npm", "run", "dev"]

    processes = []

    try:
        backend_proc = subprocess.Popen(backend_cmd, cwd=BACKEND_DIR)
        processes.append(backend_proc)

        frontend_proc = subprocess.Popen(frontend_cmd, cwd=FRONTEND_DIR)
        processes.append(frontend_proc)

        time.sleep(2)
        print("\n" + "=" * 65)
        print("  🌟 AgentPay is now running!")
        print("=" * 65)
        print("  🌐 Frontend Dashboard: http://localhost:5173")
        print("  ⚙️  Backend API Docs:  http://127.0.0.1:8000/docs")
        print("  🩺 Backend Health:    http://127.0.0.1:8000/health")
        print("-----------------------------------------------------------------")
        print("  Press Ctrl+C to stop all services.")
        print("-----------------------------------------------------------------\n")

        while True:
            time.sleep(1)

    except KeyboardInterrupt:
        print("\n🛑 Stopping all AgentPay processes...")
    finally:
        for proc in processes:
            try:
                proc.terminate()
                proc.wait(timeout=3)
            except Exception:
                proc.kill()
        print("✓ All processes terminated.")


if __name__ == "__main__":
    main()
