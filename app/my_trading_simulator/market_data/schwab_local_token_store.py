
"""Secure local storage for Schwab OAuth tokens.

Features:
- Atomic token-file replacement.
- Owner-only token file permissions (0600).
- Owner-only token directory permissions (0700).
- File and directory ownership validation.
- Symbolic-link rejection.
- Validation of schwab-py token metadata.
- No logging of OAuth credentials.

The caller must hold the exclusive Schwab worker lock.

The token directory must be a trusted location. This implementation
validates the immediate parent directory and uses no-follow access
when reading the token file.
"""

import json
import os
import stat
import tempfile
from pathlib import Path


class SchwabLocalTokenStore:
    """Persist complete schwab-py OAuth tokens securely."""

    def __init__(self, token_path: str | Path):
        self.token_path = Path(token_path)

    @staticmethod
    def validate_token(token: dict) -> None:
        """Validate the complete schwab-py OAuth token format."""
        if (
            not isinstance(token, dict)
            or not isinstance(token.get("token"), dict)
            or not isinstance(
                token.get("creation_timestamp"), (int, float)
            )
            or not token["token"].get("access_token")
            or not token["token"].get("refresh_token")
        ):
            raise ValueError(
                "Invalid Schwab OAuth token format"
            )

    def validate_directory_security(self) -> None:
        """Require an owned, private, non-symlink token directory."""
        directory = self.token_path.parent

        directory_stat = directory.lstat()

        if not stat.S_ISDIR(directory_stat.st_mode):
            raise PermissionError(
                "Schwab OAuth token directory must be "
                "a real directory, not a symbolic link"
            )

        if directory_stat.st_uid != os.getuid():
            raise PermissionError(
                "Schwab OAuth token directory must be "
                "owned by the current user"
            )

        if stat.S_IMODE(directory_stat.st_mode) != 0o700:
            raise PermissionError(
                "Schwab OAuth token directory must have "
                "permissions 0700"
            )

    def validate_file_security(self) -> None:
        """Require a regular token file owned by this user, mode 0600."""
        self.validate_directory_security()

        file_stat = self.token_path.lstat()

        if not stat.S_ISREG(file_stat.st_mode):
            raise PermissionError(
                "Schwab OAuth token path must be a regular file"
            )

        if file_stat.st_uid != os.getuid():
            raise PermissionError(
                "Schwab OAuth token file must be owned by the worker"
            )

        if stat.S_IMODE(file_stat.st_mode) != 0o600:
            raise PermissionError(
                "Schwab OAuth token file must have permissions 0600"
            )

    def read_token(self) -> dict:
        """Read a securely owned OAuth token file."""
        self.validate_file_security()

        # O_NOFOLLOW prevents the final path component from
        # being followed if it becomes a symbolic link.
        flags = os.O_RDONLY | os.O_NOFOLLOW
        fd = os.open(self.token_path, flags)

        try:
            file_stat = os.fstat(fd)

            if (
                not stat.S_ISREG(file_stat.st_mode)
                or file_stat.st_uid != os.getuid()
                or stat.S_IMODE(file_stat.st_mode) != 0o600
            ):
                raise PermissionError(
                    "Schwab OAuth token file security changed"
                )

            with os.fdopen(fd, "r", encoding="utf-8") as file:
                fd = -1
                token = json.load(file)

        finally:
            if fd >= 0:
                os.close(fd)

        self.validate_token(token)
        return token

    def write_token(
        self,
        token: dict,
        *args,
        **kwargs,
    ) -> None:
        """Atomically persist a complete refreshed OAuth token."""
        self.validate_token(token)

        self.token_path.parent.mkdir(
            parents=True,
            exist_ok=True,
            mode=0o700,
        )

        self.validate_directory_security()

        # Refuse to overwrite an existing symbolic link.
        if self.token_path.is_symlink():
            raise PermissionError(
                "Schwab OAuth token path cannot be a symbolic link"
            )

        if self.token_path.exists():
            self.validate_file_security()

        temp_path = None

        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self.token_path.parent,
                prefix=".schwab-token-",
                suffix=".tmp",
                delete=False,
            ) as temp_file:
                temp_path = Path(temp_file.name)

                os.chmod(temp_path, 0o600)

                json.dump(token, temp_file)

                temp_file.flush()
                os.fsync(temp_file.fileno())

            os.replace(
                temp_path,
                self.token_path,
            )

            # Ensure the final token file remains owner-only.
            os.chmod(self.token_path, 0o600)

            # Persist the directory entry where supported.
            dir_fd = os.open(
                self.token_path.parent,
                os.O_RDONLY | getattr(os, "O_DIRECTORY", 0),
            )

            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)

        finally:
            if temp_path is not None:
                temp_path.unlink(missing_ok=True)
