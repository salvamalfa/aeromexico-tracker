"""Process-local network guard used by offline rebuild workers."""

from __future__ import annotations

from contextlib import contextmanager
import ipaddress
import socket
from typing import Iterator


class OfflineNetworkError(RuntimeError):
    pass


def _is_loopback_address(address: object) -> bool:
    """Allow process-local IPC without resolving hostnames or permitting egress."""

    if not isinstance(address, tuple) or not address:
        return True
    host = address[0]
    if not isinstance(host, str):
        return False
    if host.casefold() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


@contextmanager
def block_network() -> Iterator[None]:
    """Reject TCP/UDP connections while allowing local file-based analytics."""

    original_socket = socket.socket
    original_create_connection = socket.create_connection

    class GuardedSocket(original_socket):
        def connect(self, address: object) -> None:
            if not _is_loopback_address(address):
                raise OfflineNetworkError(
                    f"Network access is disabled during rebuild: {address}"
                )
            return super().connect(address)

        def connect_ex(self, address: object) -> int:
            if not _is_loopback_address(address):
                raise OfflineNetworkError(
                    f"Network access is disabled during rebuild: {address}"
                )
            return super().connect_ex(address)

    def guarded_create_connection(*args: object, **kwargs: object) -> socket.socket:
        address = args[0] if args else kwargs.get("address", "unknown")
        if not _is_loopback_address(address):
            raise OfflineNetworkError(
                f"Network access is disabled during rebuild: {address}"
            )
        return original_create_connection(*args, **kwargs)

    socket.socket = GuardedSocket
    socket.create_connection = guarded_create_connection
    try:
        yield
    finally:
        socket.socket = original_socket
        socket.create_connection = original_create_connection
