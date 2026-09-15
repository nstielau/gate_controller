"""Require an explicit version bump and change note for staged USB-base changes."""

import ast
from pathlib import PurePosixPath
import re
import subprocess

VERSION_PATH = "circuitpython/lib/gate_base.py"
VERSION_RE = re.compile(r"(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)")


def protected(path):
    path = PurePosixPath(path)
    return (
        path.parts[0] == "circuitpython"
        and str(path) != "circuitpython/drawbridge.py"
        and path.suffix in (".py", ".mpy", ".pem", ".crt")
    )


def read_version(source):
    for item in ast.parse(source).body:
        if isinstance(item, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "BASE_VERSION" for target in item.targets
        ):
            version = ast.literal_eval(item.value)
            if isinstance(version, str) and VERSION_RE.fullmatch(version):
                return version
    raise ValueError("gate_base.py must define a semantic BASE_VERSION")


def check(root="."):
    def git(*args):
        return subprocess.check_output(["git", *args], cwd=root).decode()

    paths = git("diff", "--cached", "--name-only", "--no-renames", "-z").split("\0")
    changes = [p for p in paths if p and protected(p)]
    if not changes:
        return
    message = (
        "USB-managed base firmware changed. Ordinary OTA work belongs in "
        "circuitpython/drawbridge.py. For an intentional base change, stage an increased "
        "BASE_VERSION in circuitpython/lib/gate_base.py and a change note at "
        "docs/base-firmware/<version>.md. See AGENTS.md."
    )
    if VERSION_PATH not in paths:
        raise ValueError(message)
    try:
        version = read_version(git("show", ":" + VERSION_PATH))
        # The initial unversioned bootstrap was 1.0.0.
        has_previous = (
            subprocess.run(
                ["git", "cat-file", "-e", "HEAD:" + VERSION_PATH],
                cwd=root,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            ).returncode
            == 0
        )
        previous = read_version(git("show", "HEAD:" + VERSION_PATH)) if has_previous else "1.0.0"
        note = "docs/base-firmware/" + version + ".md"
        if (
            tuple(map(int, version.split("."))) <= tuple(map(int, previous.split(".")))
            or note not in paths
            or len(git("show", ":" + note).strip()) < 40
        ):
            raise ValueError(message)
    except (SyntaxError, subprocess.CalledProcessError) as error:
        raise ValueError(message) from error
    print("Intentional USB base change: " + previous + " -> " + version)


if __name__ == "__main__":
    try:
        check()
    except ValueError as error:
        raise SystemExit(str(error)) from None
