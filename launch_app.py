#!/usr/bin/env python3
"""
One-click launcher for the Stock Backtester.

Creates a private virtual environment (.venv, first run only), installs
dependencies into it, starts the Streamlit server in the background, and
opens it in your default browser automatically -- no terminal commands to
remember, and it never touches your system-wide Python packages.

You normally don't run this file directly: double-click
  Windows : run_app.bat
  macOS   : run_app.command
  Linux   : run_app.sh
which each just call this script.
"""
import os
import subprocess
import sys
import time
import venv
import webbrowser

APP_FILE = "streamlit_app.py"
PORT = 8501
VENV_DIR = ".venv"


def venv_python(venv_dir: str) -> str:
    if os.name == "nt":
        return os.path.join(venv_dir, "Scripts", "python.exe")
    return os.path.join(venv_dir, "bin", "python")


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    os.chdir(here)

    if not os.path.exists(VENV_DIR):
        print("First run: creating a private virtual environment (this only happens once)...")
        venv.create(VENV_DIR, with_pip=True)

    py = venv_python(VENV_DIR)

    print("Checking dependencies (first run may take a minute; instant after that)...")
    subprocess.run([py, "-m", "pip", "install", "-q", "--upgrade", "pip"])
    subprocess.run([py, "-m", "pip", "install", "-q", "-r", "requirements.txt"])

    print(f"Starting Stock Backtester on http://localhost:{PORT} ...")
    proc = subprocess.Popen([
        py, "-m", "streamlit", "run", APP_FILE,
        "--server.headless", "true", "--server.port", str(PORT),
    ])

    time.sleep(4)
    webbrowser.open(f"http://localhost:{PORT}")

    print("\nApp is running in this window. To stop it, close this window or press Ctrl+C.\n")
    try:
        proc.wait()
    except KeyboardInterrupt:
        proc.terminate()


if __name__ == "__main__":
    main()

