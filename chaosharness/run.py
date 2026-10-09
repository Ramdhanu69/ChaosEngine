import sys
from .cli import main

def run_shim():
    # If the first argument is not already 'run', insert 'run' so that
    # 'python -m chaosharness.run --model ...' works seamlessly as the 'run' command.
    if len(sys.argv) > 1 and sys.argv[1] not in ("run", "compare", "selftest", "route", "-h", "--help"):
        sys.argv.insert(1, "run")
    elif len(sys.argv) == 1:
        sys.argv.append("run")
    return main()

if __name__ == "__main__":
    sys.exit(run_shim())
