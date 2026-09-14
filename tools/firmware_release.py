"""Build a single-file firmware release from a clean, tagged Git commit."""

import argparse
import ast
import hashlib
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def build_release(version):
    if not re.fullmatch(r"(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)", version):
        raise ValueError("Use a semantic version, e.g. 1.0.0")

    def git(*args):
        return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()

    if git("status", "--porcelain", "--untracked-files=all"):
        raise ValueError("Commit all source changes before creating a firmware release")
    head = git("rev-parse", "HEAD")
    if git("rev-parse", "firmware-v" + version + "^{commit}") != head:
        raise ValueError("The firmware tag must point to HEAD")
    subprocess.run(
        [str(ROOT / ".venv/bin/python"), "-m", "unittest", "discover", "-s", "test_suite"],
        cwd=ROOT,
        check=True,
    )
    source = (ROOT / "circuitpython/drawbridge.py").read_bytes()
    constants = {}
    for item in ast.parse(source).body:
        if isinstance(item, ast.Assign) and isinstance(item.targets[0], ast.Name):
            if item.targets[0].id in ("APP_VERSION", "APP_API_VERSION"):
                constants[item.targets[0].id] = ast.literal_eval(item.value)
    if constants != {"APP_VERSION": version, "APP_API_VERSION": 1} or len(source) > 65536:
        raise ValueError("Application version/API or size mismatch")
    checksum = hashlib.sha256(source).hexdigest()
    manifest = {
        "schema": 1,
        "app_version": version,
        "app_api_version": 1,
        "minimum_bootstrap_version": "1.0.0",
        "circuitpython_major": 10,
        "supported_board_ids": ["seeed_xiao_esp32_s3_sense"],
        "size": len(source),
        "sha256": checksum,
        "artifact_object": f"firmware/{version}/{checksum}/drawbridge.py",
        "git_commit": head,
    }
    out = ROOT / "artifacts/firmware" / version
    out.mkdir(parents=True, exist_ok=True)
    for name, value in {
        "drawbridge.py": source,
        "manifest.json": (json.dumps(manifest, indent=2) + "\n").encode(),
    }.items():
        path = out / name
        if path.exists() and path.read_bytes() != value:
            raise ValueError("Refusing to replace an existing release artifact")
        path.write_bytes(value)
    return out


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("version")
    parser.add_argument("--publish", action="store_true")
    args = parser.parse_args()
    try:
        output = build_release(args.version)
        if args.publish:
            subprocess.run(
                [
                    "gh",
                    "release",
                    "create",
                    "firmware-v" + args.version,
                    str(output / "drawbridge.py"),
                    str(output / "manifest.json"),
                    "--repo",
                    "nstielau/gate_controller",
                    "--verify-tag",
                    "--title",
                    "Drawbridge firmware " + args.version,
                    "--generate-notes",
                ],
                check=True,
            )
        print("Firmware artifacts: " + str(output))
    except (ValueError, subprocess.CalledProcessError) as error:
        raise SystemExit(str(error)) from None
