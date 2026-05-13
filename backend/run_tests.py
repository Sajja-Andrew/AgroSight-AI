#!/usr/bin/env python
"""Single-command test runner.

Usage:
    python run_tests.py              # run all tests
    python run_tests.py -m "not slow" # skip slow tests
    python run_tests.py -x           # stop on first failure
"""
import subprocess
import sys


def main():
    args = ["-m", "pytest"] + sys.argv[1:]
    result = subprocess.run([sys.executable] + args, cwd=".")
    sys.exit(result.returncode)


if __name__ == "__main__":
    main()
