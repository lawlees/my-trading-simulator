"""Local read-only Schwab market-data socket server."""

import os
import socket
import stat
from pathlib import Path

from my_trading_simulator.market_data.socket_protocol import (
    SOCKET_PATH,
)
from my_trading_simulator.market_data.socket_directory_security import (
    validate_socket_directory,
)
from my_trading_simulator.market_data.socket_handler import (
    handle_market_data_connection,
)
from my_trading_simulator.market_data.socket_dispatcher import (
    dispatch_market_data_request,
)
from my_trading_simulator.market_data.socket_peer_auth import (
    authorize_socket_peer,
    PeerAuthorizationError,
)
from my_trading_simulator.market_data.schwab_market_data_worker import (
    run_schwab_operation,
    DEFAULT_LOCK_PATH,
)


class MarketDataSocketServer:
    """Serve validated market-data requests over a Unix socket."""

    def __init__(
        self,
        socket_path=SOCKET_PATH,
        client_factory=None,
        lock_path=DEFAULT_LOCK_PATH,
        peer_authorizer=None,
        directory_validator=None,
    ):
        self.socket_path = Path(socket_path)
        self.client_factory = client_factory
        self.lock_path = lock_path
        self.directory_validator = (
            directory_validator
            if directory_validator is not None
            else validate_socket_directory
        )
        self.peer_authorizer = (
            peer_authorizer
            if peer_authorizer is not None
            else authorize_socket_peer
        )

    def _execute(self, request):
        return run_schwab_operation(
            lambda client: dispatch_market_data_request(
                client, request
            ),
            client_factory=self.client_factory,
            lock_path=self.lock_path,
        )

    def serve(self, max_connections=None, stop_event=None):
        """
        Serve requests sequentially.

        max_connections is available for tests.
        Production operation will use a managed service.
        """

        if (
            max_connections is not None
            and (
                type(max_connections) is not int
                or max_connections < 1
            )
        ):
            raise ValueError("Invalid connection limit")

        if self.socket_path.is_symlink():
            raise RuntimeError("Refusing symlink socket path")

        if self.socket_path.exists():
            raise RuntimeError(
                "Socket path already exists; refusing replacement"
            )

        # The runtime directory must already exist.
        if not self.socket_path.parent.is_dir():
            raise RuntimeError("Socket directory does not exist")

        # Fail closed before binding the socket.
        self.directory_validator(self.socket_path.parent)

        # Socket directory ownership is checked before bind; setgid
        # directory provides the dedicated IPC group on Linux.
        with socket.socket(
            socket.AF_UNIX, socket.SOCK_STREAM
        ) as listener:
            listener.bind(str(self.socket_path))

            # Record the filesystem socket identity immediately
            # after binding, for safe cleanup on macOS and Linux.
            original = os.lstat(self.socket_path)

            try:
                os.chmod(self.socket_path, 0o660)
                listener.listen(5)
                listener.settimeout(0.25)

                count = 0

                while True:
                    if (
                        stop_event is not None
                        and stop_event.is_set()
                    ):
                        break

                    try:
                        connection, _ = listener.accept()
                    except socket.timeout:
                        continue

                    with connection:
                        try:
                            self.peer_authorizer(connection)
                        except PeerAuthorizationError:
                            # Reject before parsing or Schwab initialization.
                            continue
                        except Exception:
                            # Unexpected authorizer failures also fail closed.
                            # Do not leak internal exception data to clients.
                            continue

                        handle_market_data_connection(
                            connection,
                            self._execute,
                        )

                    count += 1

                    if (
                        max_connections is not None
                        and count >= max_connections
                    ):
                        break
            finally:
                # Remove only our own socket inode.
                try:
                    current = os.lstat(self.socket_path)
                    if (
                        stat.S_ISSOCK(current.st_mode)
                        and current.st_ino == original.st_ino
                        and current.st_dev == original.st_dev
                    ):
                        self.socket_path.unlink()
                except FileNotFoundError:
                    pass
