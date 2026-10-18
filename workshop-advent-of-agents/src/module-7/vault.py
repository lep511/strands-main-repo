"""Refresh-token vaults with AWS Secrets Manager version semantics.

Both backends behave the same way, so the delegation code does not care which one it gets:

  write_initial(name, value)        first version, labelled AWSCURRENT
  read_current(name)                (value, version_id) of AWSCURRENT
  rotate(name, value, previous_id)  new AWSCURRENT, then strip every label from the old
                                    version so it is deprecated and can never be read again
  versions(name)                    version history (ids and labels only, never values)

LocalVault keeps files under src/module-7/.vault/ (mode 0600) and a per-secret lock.
SecretsManagerVault uses the agent's own AWS identity (layer 1) to reach Secrets Manager.
"""

import fcntl
import json
import os
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

CURRENT, PREVIOUS = "AWSCURRENT", "AWSPREVIOUS"
SECRET_PREFIX = "advent-of-agents/day7/"


class VaultError(Exception):
    pass


class VaultAccessDenied(Exception):
    """Layer 1 failed: the agent's own identity is not allowed to open the vault."""


class LocalVault:
    def __init__(self, root: Path = Path(__file__).with_name(".vault")):
        self.root = root

    def _path(self, name: str) -> Path:
        return self.root / (name.replace("/", "__") + ".json")

    def _load(self, name: str) -> list[dict]:
        path = self._path(name)
        if not path.exists():
            raise VaultError(f"secret '{name}' not found")
        return json.loads(path.read_text())

    def _save(self, name: str, versions: list[dict]) -> None:
        self.root.mkdir(mode=0o700, exist_ok=True)
        path = self._path(name)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(versions, indent=2))
        os.chmod(tmp, 0o600)
        tmp.replace(path)

    @contextmanager
    def lock(self, name: str):
        """One refresh at a time per user: a concurrent refresh would look like token reuse."""
        self.root.mkdir(mode=0o700, exist_ok=True)
        with open(self._path(name).with_suffix(".lock"), "w") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            yield

    def write_initial(self, name: str, value: str) -> str:
        try:
            versions = self._load(name)
        except VaultError:
            versions = []
        for v in versions:
            v["stages"], v["value"] = [], None  # a fresh consent supersedes everything stored before
        vid = str(uuid.uuid4())
        versions.append({"id": vid, "value": value, "stages": [CURRENT], "created": time.time()})
        self._save(name, versions)
        return vid

    def read_current(self, name: str) -> tuple[str, str]:
        for v in self._load(name):
            if CURRENT in v["stages"]:
                return v["value"], v["id"]
        raise VaultError(f"secret '{name}' has no {CURRENT} version")

    def rotate(self, name: str, value: str, previous_id: str) -> str:
        versions = self._load(name)
        current = next((v for v in versions if CURRENT in v["stages"]), None)
        if current is None or current["id"] != previous_id:
            raise VaultError("stale rotation: AWSCURRENT changed since it was read")
        for v in versions:
            # Deprecate the old version and wipe its value: a leaked copy of this file must not
            # contain a usable token (Secrets Manager garbage-collects deprecated versions).
            v["stages"], v["value"] = [], None
        vid = str(uuid.uuid4())
        versions.append({"id": vid, "value": value, "stages": [CURRENT], "created": time.time()})
        self._save(name, versions)
        return vid

    def versions(self, name: str) -> list[dict]:
        return [{"id": v["id"][:8], "stages": v["stages"]} for v in self._load(name)]

    def delete(self, name: str) -> None:
        self._path(name).unlink(missing_ok=True)


class SecretsManagerVault:
    """AWS Secrets Manager backend. Authenticates with the caller's AWS identity."""

    def __init__(self, client=None, region: str | None = None, prefix: str = SECRET_PREFIX):
        if client is None:
            import boto3

            client = boto3.client("secretsmanager", region_name=region or os.getenv("AWS_REGION", "us-east-1"))
        self.sm = client
        self.prefix = prefix

    def _id(self, name: str) -> str:
        return self.prefix + name

    @contextmanager
    def lock(self, name: str):
        # Secrets Manager has no compare-and-swap; rotate() re-checks AWSCURRENT instead, and
        # production schedulers should run one job per user (e.g. SQS FIFO MessageGroupId=user).
        yield

    def write_initial(self, name: str, value: str) -> str:
        try:
            resp = self.sm.create_secret(Name=self._id(name), SecretString=value,
                                         Description="Day 7 offline_access refresh token",
                                         Tags=[{"Key": "workshop", "Value": "advent-of-agents-day7"}])
            return resp["VersionId"]
        except self.sm.exceptions.ResourceExistsException:
            new_id = self.sm.put_secret_value(SecretId=self._id(name), SecretString=value)["VersionId"]
            self._deprecate_all_but(name, new_id)
            return new_id

    def read_current(self, name: str) -> tuple[str, str]:
        try:
            resp = self.sm.get_secret_value(SecretId=self._id(name), VersionStage=CURRENT)
        except self.sm.exceptions.ResourceNotFoundException as e:
            raise VaultError(f"secret '{name}' not found") from e
        except self.sm.exceptions.ClientError as e:
            if e.response["Error"]["Code"] in ("AccessDeniedException", "AccessDenied"):
                raise VaultAccessDenied(e.response["Error"]["Message"]) from e
            raise
        return resp["SecretString"], resp["VersionId"]

    def rotate(self, name: str, value: str, previous_id: str) -> str:
        stages = self.sm.describe_secret(SecretId=self._id(name))["VersionIdsToStages"]
        if CURRENT not in stages.get(previous_id, []):
            raise VaultError("stale rotation: AWSCURRENT changed since it was read")
        # put_secret_value moves AWSCURRENT to the new version and AWSPREVIOUS to the old one.
        new_id = self.sm.put_secret_value(SecretId=self._id(name), SecretString=value)["VersionId"]
        self._deprecate_all_but(name, new_id)
        return new_id

    def _deprecate_all_but(self, name: str, keep_id: str) -> None:
        # Removing AWSPREVIOUS leaves the old version unlabelled ("deprecated"): it cannot be
        # fetched by stage any more and Secrets Manager garbage-collects it.
        stages = self.sm.describe_secret(SecretId=self._id(name))["VersionIdsToStages"]
        for vid, labels in stages.items():
            if vid != keep_id and PREVIOUS in labels:
                self.sm.update_secret_version_stage(SecretId=self._id(name), VersionStage=PREVIOUS,
                                                    RemoveFromVersionId=vid)

    def versions(self, name: str) -> list[dict]:
        resp = self.sm.list_secret_version_ids(SecretId=self._id(name), IncludeDeprecated=True)
        return [{"id": v["VersionId"][:8], "stages": v.get("VersionStages", [])}
                for v in sorted(resp["Versions"], key=lambda v: v["CreatedDate"])]

    def delete(self, name: str) -> None:
        try:
            self.sm.delete_secret(SecretId=self._id(name), ForceDeleteWithoutRecovery=True)
        except self.sm.exceptions.ResourceNotFoundException:
            pass


def get_vault(kind: str = "local"):
    return SecretsManagerVault() if kind == "aws" else LocalVault()


def secret_name(user_id: str) -> str:
    return f"refresh-token/{user_id}"
