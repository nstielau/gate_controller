"""USB-managed OTA journal and two application slots. No networking or GPIO.

The root drawbridge.py is a USB recovery copy, never modified by OTA. Alternate
checksummed journals select verified files; a torn journal cannot promote a file.
FAT/media corruption still requires USB recovery; this is not a flash partition
bootloader or a sandbox for malicious Python.
"""

import hashlib
import json
import os

MAX_BYTES = 65536
BOOTSTRAP_VERSION = "1.0.0"
BOARD_ID = "seeed_xiao_esp32_s3_sense"


def digest(data):
    h = hashlib.new("sha256")
    h.update(data)
    return "".join("{:02x}".format(b) for b in h.digest())


def file_digest(path):
    h = hashlib.new("sha256")
    size = 0
    with open(path, "rb") as source:
        while True:
            chunk = source.read(1024)
            if not chunk:
                break
            h.update(chunk)
            size += len(chunk)
            if size > MAX_BYTES:
                raise ValueError("artifact_too_large")
    return size, "".join("{:02x}".format(b) for b in h.digest())


def version_ok(value):
    if type(value) is not str:
        return False
    parts = value.split(".")
    return len(parts) == 3 and all(p.isdigit() and str(int(p)) == p for p in parts)


def validate_manifest(m, board_id, cp_major):
    if (
        type(m) is not dict
        or type(m.get("schema")) is not int
        or m["schema"] != 1
        or not version_ok(m.get("app_version"))
        or type(m.get("app_api_version")) is not int
        or m.get("app_api_version") != 1
        or m.get("minimum_bootstrap_version") != BOOTSTRAP_VERSION
        or cp_major != 10
        or m.get("circuitpython_major") != cp_major
        or board_id != BOARD_ID
        or m.get("supported_board_ids") != [BOARD_ID]
        or type(m.get("sequence")) is not int
        or not 1 <= m["sequence"] <= 9007199254740991
        or type(m.get("size")) is not int
        or not 1 <= m["size"] <= MAX_BYTES
        or type(m.get("sha256")) is not str
        or len(m["sha256"]) != 64
        or any(c not in "0123456789abcdef" for c in m["sha256"])
    ):
        raise ValueError("incompatible_manifest")
    return {k: m[k] for k in ("app_version", "sequence", "size", "sha256")}


class UpdateStore:
    def __init__(self, root="/ota", sync=None):
        self.root = root
        self.sync = sync or os.sync
        self.state = {
            "generation": 0,
            "active": None,
            "trial": None,
            "floor": 0,
            "outcome": "current",
        }
        for slot in (0, 1):
            try:
                with open(self.root + "/state{}.json".format(slot)) as source:
                    envelope = json.loads(source.read(4096))
                body = envelope["body"]
                if digest(body.encode()) != envelope["sha256"]:
                    continue
                state = json.loads(body)
                if (
                    type(state["generation"]) is int
                    and state["generation"] > self.state["generation"]
                    and type(state["floor"]) is int
                    and state["floor"] >= 0
                    and state["outcome"] in ("current", "trial", "rolled_back")
                ):
                    # Validate path-bearing fields before accepting a journal.
                    for item in (state["active"], state["trial"]):
                        if item is not None and (
                            type(item["slot"]) is not int or item["slot"] not in (0, 1)
                        ):
                            raise ValueError("invalid_slot")
                    self.state = state
            except (OSError, ValueError, KeyError, TypeError):
                pass

    def save(self, state):
        try:
            os.mkdir(self.root)
        except OSError:
            os.stat(self.root)
        state = dict(state)
        state["generation"] = self.state["generation"] + 1
        body = json.dumps(state)
        path = self.root + "/state{}.json".format(state["generation"] % 2)
        # Overwrite only the older journal. The other complete generation remains.
        with open(path, "w") as target:
            target.write(json.dumps({"body": body, "sha256": digest(body.encode())}))
            target.flush()
        self.sync()
        self.state = state

    def path(self, item):
        return self.root + "/app{}.py".format(item["slot"])

    def verified(self, item):
        try:
            return file_digest(self.path(item)) == (item["size"], item["sha256"])
        except (OSError, ValueError, KeyError):
            return False

    def begin_boot(self):
        trial = self.state["trial"]
        if trial:
            if trial.get("started") or not self.verified(trial):
                self.rollback()
            else:
                trial = dict(trial, started=True)
                self.save(dict(self.state, trial=trial))
                return self.path(trial), trial
        active = self.state["active"]
        if active and self.verified(active):
            return self.path(active), active
        if active:
            self.save(dict(self.state, active=None, outcome="rolled_back"))
        return None, None

    def stage(self, manifest, chunks, service):
        if self.state["trial"] or manifest["sequence"] <= self.state["floor"]:
            return False
        try:
            os.mkdir(self.root)
        except OSError:
            os.stat(self.root)
        stat = os.statvfs(self.root)
        if stat[0] * stat[4] < manifest["size"] + 16384:
            raise OSError("insufficient_space")
        active = self.state["active"]
        item = dict(manifest, slot=1 - active["slot"] if active else 0, started=False)
        with open(self.path(item), "wb") as target:
            size = 0
            for chunk in chunks:
                service()  # abort if a hold arrived during transfer
                size += len(chunk)
                if size > manifest["size"]:
                    raise ValueError("artifact_too_large")
                target.write(chunk)
            target.flush()
        self.sync()
        if not self.verified(item):
            raise ValueError("artifact_digest_mismatch")
        service()
        self.save(dict(self.state, trial=item, floor=item["sequence"], outcome="trial"))
        return True

    def confirm(self):
        if self.state["trial"]:
            item = dict(self.state["trial"])
            item.pop("started", None)
            self.save(dict(self.state, active=item, trial=None, outcome="current"))

    def rollback(self):
        self.save(dict(self.state, trial=None, outcome="rolled_back"))
