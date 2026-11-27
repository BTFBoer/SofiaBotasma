import sys

if sys.version_info < (3, 12):
    sys.exit(
        f"Sofia needs Python 3.12 or newer (this is {sys.version.split()[0]}). "
        "Install a current Python from https://www.python.org/downloads/"
    )

from app.main import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
