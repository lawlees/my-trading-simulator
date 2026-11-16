"""Linux peer authorization for the Schwab Unix socket."""

import pwd
import socket
import struct


class PeerAuthorizationError(PermissionError):
    """Unix socket peer is not authorized."""


def authorize_socket_peer(
    connection: socket.socket,
    allowed_username: str = "ubuntu",
) -> int:
    """
    Authorize a Unix socket connection by Linux UID.

    Fail closed on platforms without SO_PEERCRED.

    Returns the authorized peer UID.
    """

    if not hasattr(socket, "SO_PEERCRED"):
        raise PeerAuthorizationError(
            "Linux peer credentials unavailable"
        )

    try:
        allowed_uid = pwd.getpwnam(
            allowed_username
        ).pw_uid
    except KeyError:
        raise PeerAuthorizationError(
            "Authorized account not found"
        ) from None

    credential_size = struct.calcsize("3i")

    try:
        credentials = connection.getsockopt(
            socket.SOL_SOCKET,
            socket.SO_PEERCRED,
            credential_size,
        )

        if len(credentials) != credential_size:
            raise PeerAuthorizationError(
                "Invalid peer credentials"
            )

        peer_pid, peer_uid, peer_gid = struct.unpack(
            "3i", credentials
        )

    except OSError:
        raise PeerAuthorizationError(
            "Unable to verify socket peer"
        ) from None

    if peer_pid <= 0 or peer_uid != allowed_uid:
        raise PeerAuthorizationError(
            "Unauthorized socket peer"
        )

    return peer_uid
