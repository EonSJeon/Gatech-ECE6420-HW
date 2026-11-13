#!/usr/bin/env python3
"""Explicitly register an environment if ECE6420 (Local) is unavailable."""
import importlib.util
import subprocess
import sys


def main():
    required = ("numpy", "matplotlib", "nbformat", "nbclient", "ipykernel", "reportlab")
    missing = [name for name in required if importlib.util.find_spec(name) is None]
    if missing:
        raise SystemExit("Install HW09/requirements.txt with this Python first. Missing: " + ", ".join(missing))
    subprocess.run([sys.executable, "-m", "ipykernel", "install", "--user",
                    "--name", "ece6420-local", "--display-name", "ECE6420 (Local)"], check=True)
    print("Select kernel: ECE6420 (Local)")
    print("Local interpreter: " + sys.executable)
    print("Spectre runs on gt-ece; figures and the report are created locally.")


if __name__ == "__main__":
    main()
