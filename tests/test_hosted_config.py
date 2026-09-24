"""Hosting must fail closed before opening a local save or accepting requests."""

from pathlib import Path

import pytest

from sway.hosting.config import HostedConfig


@pytest.mark.parametrize(
    "origin",
    [
        "http://sway.test",
        "https://sway.test/",
        "https://sway.test/path",
        "https://user:secret@sway.test",
        "https://sway.test?key=secret",
        "https://sway.test#secret",
        "https://*.test",
        "https://sway.test:443",
        "https://sway.test:",
        "https://sway.test:0",
        "https://sway.test:65536",
        "https://SWAY.test",
        "https://sway.test.",
        "https://sway.test\n",
        "https://sway_test",
        "https://-sway.test",
        "https://[bad]",
        "https://",
    ],
)
def test_reject_noncanonical_origin(tmp_path: Path, origin: str) -> None:
    with pytest.raises(ValueError):
        _ = HostedConfig(origin, tmp_path)


@pytest.mark.parametrize(
    "origin,host",
    [
        ("https://sway.test", "sway.test"),
        ("https://sway.test:8443", "sway.test:8443"),
        ("https://[::1]", "[::1]"),
    ],
)
def test_canonical_origin(tmp_path: Path, origin: str, host: str) -> None:
    config = HostedConfig(origin, tmp_path)
    assert config.canonical_host == host
    assert config.database_path == tmp_path / "hosted.sqlite3"
    assert len(config.allowed_hosts) == 1
    assert config.trusted_proxy_ips == ()


@pytest.mark.parametrize(
    "hosted,local", [("same", "same"), ("data", "data/local"), ("data/hosted", "data")]
)
def test_local_and_hosted_directories_never_overlap(
    tmp_path: Path, hosted: str, local: str
) -> None:
    with pytest.raises(ValueError, match="non-overlapping"):
        _ = HostedConfig("https://sway.test", tmp_path / hosted, tmp_path / local)


def test_reject_symlink_alias(tmp_path: Path) -> None:
    local = tmp_path / "local"
    local.mkdir()
    (tmp_path / "alias").symlink_to(local, target_is_directory=True)
    with pytest.raises(ValueError, match="non-overlapping"):
        _ = HostedConfig("https://sway.test", tmp_path / "alias" / "hosted", local)


def test_required_env_and_limits(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="required"):
        _ = HostedConfig.from_env({})
    env = {
        "SWAY_HOSTED_ORIGIN": "https://sway.test",
        "SWAY_HOSTED_DATA_DIR": str(tmp_path / "hosted"),
        "SWAY_DATA_DIR": str(tmp_path / "local"),
    }
    config = HostedConfig.from_env(env)
    assert config.max_request_bytes == 65536
    assert config.credential_requests_per_minute == 10
    for key in (
        "SWAY_HOSTED_MAX_REQUEST_BYTES",
        "SWAY_HOSTED_MUTATIONS_PER_MINUTE",
        "SWAY_HOSTED_CREDENTIALS_PER_MINUTE",
        "SWAY_HOSTED_MAX_RATE_LIMIT_KEYS",
    ):
        with pytest.raises(ValueError):
            _ = HostedConfig.from_env({**env, key: "0"})
    with pytest.raises(ValueError, match="Forwarded"):
        _ = HostedConfig.from_env({**env, "SWAY_TRUSTED_PROXY_IPS": "*"})


def test_storage_permissions(tmp_path: Path) -> None:
    config = HostedConfig("https://sway.test", tmp_path / "hosted")
    config.prepare_directory()
    assert config.data_dir.stat().st_mode & 0o777 == 0o700
    config.data_dir.chmod(0o755)
    with pytest.raises(ValueError, match="owner-only"):
        config.prepare_directory()


def test_process_lock_excludes_other_process_and_releases_after_crash(tmp_path: Path) -> None:
    import select
    import subprocess
    import sys

    config = HostedConfig("https://sway.test", tmp_path)
    child = """
import sys
from pathlib import Path
from sway.hosting.config import HostedConfig
config = HostedConfig('https://sway.test', Path(sys.argv[1]))
with config.process_lock():
    print('locked', flush=True)
    input()
"""
    with subprocess.Popen(
        [sys.executable, "-c", child, str(tmp_path)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    ) as process:
        try:
            assert process.stdout is not None
            ready, _, _ = select.select([process.stdout], [], [], 10)
            assert ready, "Child did not acquire process lock"
            assert process.stdout.readline().strip() == "locked"
            with pytest.raises(RuntimeError, match="Another hosted process"):
                with config.process_lock():
                    pytest.fail("Concurrent process acquired the lock")
        finally:
            process.kill()
            _ = process.communicate(timeout=10)
    with config.process_lock():
        assert (tmp_path / ".server.lock").stat().st_mode & 0o777 == 0o600
    with config.process_lock():
        pass


def test_process_lock_rejects_symlinks_and_permissive_file(tmp_path: Path) -> None:
    config = HostedConfig("https://sway.test", tmp_path)
    target = tmp_path / "target"
    target.touch(mode=0o600)
    lock = tmp_path / ".server.lock"
    lock.symlink_to(target)
    with pytest.raises(OSError):
        with config.process_lock():
            pytest.fail("Symlink lock accepted")
    lock.unlink()
    lock.touch(mode=0o644)
    lock.chmod(0o644)
    with pytest.raises(ValueError, match="owner-only"):
        with config.process_lock():
            pytest.fail("Public lock file accepted")
