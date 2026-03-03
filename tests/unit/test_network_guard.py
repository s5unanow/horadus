from __future__ import annotations

import socket

import pytest
from pytest_socket import SocketBlockedError

pytestmark = pytest.mark.unit


def test_network_calls_are_blocked_by_default() -> None:
    with pytest.raises(SocketBlockedError):
        socket.create_connection(("example.com", 80), timeout=0.1)
