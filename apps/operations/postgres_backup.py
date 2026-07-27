import os
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path


class DatabaseDumpError(RuntimeError):
    def __init__(self, error_code: str) -> None:
        self.error_code = error_code
        super().__init__(error_code)


@dataclass(frozen=True, slots=True)
class PostgresDumpConfig:
    executable: Path
    database: str
    username: str
    password: str
    host: str
    port: int

    def __post_init__(self) -> None:
        executable = Path(self.executable)
        values = (self.database, self.username, self.password, self.host)
        if (
            not executable.is_absolute()
            or not executable.is_file()
            or executable.is_symlink()
            or not os.access(executable, os.X_OK)
            or any(not isinstance(value, str) or "\x00" in value for value in values)
            or not self.database
            or not self.username
            or isinstance(self.port, bool)
            or not isinstance(self.port, int)
            or not 1 <= self.port <= 65_535
        ):
            raise DatabaseDumpError("operations.backup_command_invalid.v1")


class PostgresDumpRunner:
    def __init__(self, config: PostgresDumpConfig, *, poll_seconds: int = 30) -> None:
        if (
            not isinstance(config, PostgresDumpConfig)
            or isinstance(poll_seconds, bool)
            or not isinstance(poll_seconds, int)
            or not 1 <= poll_seconds <= 300
        ):
            raise TypeError("PostgreSQL dump configuration is invalid")
        self.config = config
        self.poll_seconds = poll_seconds

    def __call__(self, destination: Path, heartbeat: Callable[[], object]) -> None:
        target = Path(destination)
        if (
            not target.is_absolute()
            or not target.parent.is_dir()
            or target.exists()
            or target.parent.is_symlink()
            or not callable(heartbeat)
        ):
            raise DatabaseDumpError("operations.backup_command_invalid.v1")
        descriptor = os.open(
            target,
            os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
        environment = {
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
            "PGPASSWORD": self.config.password,
        }
        command = (
            str(self.config.executable),
            "--format=custom",
            "--compress=6",
            "--no-owner",
            "--no-privileges",
            "--host",
            self.config.host,
            "--port",
            str(self.config.port),
            "--username",
            self.config.username,
            self.config.database,
        )
        process = None
        try:
            with os.fdopen(descriptor, "wb") as output:
                process = subprocess.Popen(
                    command,
                    stdin=subprocess.DEVNULL,
                    stdout=output,
                    stderr=subprocess.DEVNULL,
                    env=environment,
                    close_fds=True,
                )
                while True:
                    try:
                        return_code = process.wait(timeout=self.poll_seconds)
                        break
                    except subprocess.TimeoutExpired:
                        heartbeat()
                output.flush()
                os.fsync(output.fileno())
            if return_code != 0 or target.stat().st_size <= 0:
                raise DatabaseDumpError("operations.backup_database_failed.v1")
        except Exception as exc:
            if process is not None and process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
            try:
                target.unlink()
            except FileNotFoundError:
                pass
            if isinstance(exc, DatabaseDumpError):
                raise
            raise DatabaseDumpError("operations.backup_database_failed.v1") from None
