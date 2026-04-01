"""SSH utilities for remote MD execution and file transfer."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable
import time

import paramiko


class SSHManagerError(Exception):
    """Raised when SSH operations fail with user-friendly context."""


@dataclass
class SSHConfig:
    host: str
    port: int
    username: str
    password: str = ""
    key_path: str = ""
    remote_workdir: str = "~/md_jobs"


class SSHManager:
    """Thin wrapper around Paramiko for command execution and SFTP operations."""

    def __init__(self, config: SSHConfig):
        self.config = config
        self.client: paramiko.SSHClient | None = None

    def connect(self) -> None:
        try:
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            connect_kwargs = {
                "hostname": self.config.host,
                "port": self.config.port,
                "username": self.config.username,
                "timeout": 12,
            }
            if self.config.key_path:
                connect_kwargs["key_filename"] = self.config.key_path
            else:
                connect_kwargs["password"] = self.config.password

            client.connect(**connect_kwargs)
            self.client = client
        except Exception as exc:
            raise SSHManagerError(
                "Connection Timed Out or failed. Please check host, port, username, and credentials."
            ) from exc

    def disconnect(self) -> None:
        if self.client is not None:
            self.client.close()
            self.client = None

    def test_connection(self) -> bool:
        self.connect()
        self.disconnect()
        return True

    def _require_client(self) -> paramiko.SSHClient:
        if self.client is None:
            raise SSHManagerError("SSH client is not connected.")
        return self.client

    def upload_file(self, local_path: str) -> str:
        client = self._require_client()
        local = Path(local_path)
        remote_dir = self.config.remote_workdir
        remote_path = f"{remote_dir}/{local.name}"
        try:
            self._run_simple_command(f"mkdir -p {remote_dir}")
            with client.open_sftp() as sftp:
                sftp.put(str(local), remote_path)
        except Exception as exc:
            raise SSHManagerError(f"File upload failed for {local.name}.") from exc
        return remote_path

    def _run_simple_command(self, command: str) -> None:
        client = self._require_client()
        _, stdout, stderr = client.exec_command(command)
        exit_code = stdout.channel.recv_exit_status()
        if exit_code != 0:
            raise SSHManagerError(stderr.read().decode("utf-8", errors="ignore") or "Remote command failed.")

    def run_command_stream(
        self,
        command: str,
        on_stdout: Callable[[str], None],
        on_stderr: Callable[[str], None],
    ) -> int:
        client = self._require_client()
        try:
            _, stdout, stderr = client.exec_command(command, get_pty=True)
            channel = stdout.channel
            while True:
                if channel.recv_ready():
                    chunk = channel.recv(4096).decode("utf-8", errors="ignore")
                    if chunk:
                        on_stdout(chunk)
                if channel.recv_stderr_ready():
                    chunk = channel.recv_stderr(4096).decode("utf-8", errors="ignore")
                    if chunk:
                        on_stderr(chunk)
                if channel.exit_status_ready() and not channel.recv_ready() and not channel.recv_stderr_ready():
                    break
                time.sleep(0.1)
            return channel.recv_exit_status()
        except Exception as exc:
            raise SSHManagerError("Failed while streaming remote command output.") from exc

    def download_matching_files(self, local_dir: str, extensions: Iterable[str]) -> list[str]:
        client = self._require_client()
        downloaded: list[str] = []
        try:
            Path(local_dir).mkdir(parents=True, exist_ok=True)
            with client.open_sftp() as sftp:
                for entry in sftp.listdir_attr(self.config.remote_workdir):
                    if any(entry.filename.endswith(ext) for ext in extensions):
                        remote_path = f"{self.config.remote_workdir}/{entry.filename}"
                        local_path = str(Path(local_dir) / entry.filename)
                        sftp.get(remote_path, local_path)
                        downloaded.append(local_path)
        except Exception as exc:
            raise SSHManagerError("Failed to download result files from remote server.") from exc
        return downloaded
