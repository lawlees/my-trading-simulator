"""Validate the private runtime directory for Schwab IPC."""

import grp
import os
import pwd
import stat
from pathlib import Path


class SocketDirectorySecurityError(PermissionError):
    """Socket runtime directory failed security checks."""


def validate_socket_directory(
    directory: str | Path,
    *,
    expected_user: str = "schwab-worker",
    expected_group: str = "trading-market-data",
) -> None:
    """Require expected ownership and restrictive permissions.

    The production directory must be owned by the dedicated worker,
    have the socket-access group, and use mode 2770.
    """

    path = Path(directory)

    try:
        info = os.lstat(path)

        expected_uid = pwd.getpwnam(expected_user).pw_uid
        expected_gid = grp.getgrnam(expected_group).gr_gid

    except (OSError, KeyError) as error:
        raise SocketDirectorySecurityError(
            "Socket directory security verification failed"
        ) from error

    if not stat.S_ISDIR(info.st_mode):
        raise SocketDirectorySecurityError(
            "Socket runtime path is not a real directory"
        )

    if info.st_uid != expected_uid:
        raise SocketDirectorySecurityError(
            "Incorrect socket directory owner"
        )

    if info.st_gid != expected_gid:
        raise SocketDirectorySecurityError(
            "Incorrect socket directory group"
        )

    if stat.S_IMODE(info.st_mode) != 0o2770:
        raise SocketDirectorySecurityError(
            "Unsafe socket directory permissions"
        )
