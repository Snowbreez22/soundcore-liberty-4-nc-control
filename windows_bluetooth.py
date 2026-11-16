"""Windows Bluetooth Classic transport for the Liberty 4 NC."""
from contextlib import contextmanager
import ctypes
from pathlib import Path
import os
import re
import select
import socket
import struct
import subprocess
import time
from uuid import UUID

AF_BTH = 32
BTHPROTO_RFCOMM = 3
SERVICE = UUID("0cf12d31-fac3-4553-bd80-d6832e7b3947")
DEVICE_ID = re.compile(r"^BTHENUM\\DEV_([0-9a-f]{12})(?:\\|$)", re.IGNORECASE)
ADDRESS = re.compile(
    r"[0-9a-f]{12}|(?:[0-9a-f]{2}:){5}[0-9a-f]{2}|(?:[0-9a-f]{2}-){5}[0-9a-f]{2}",
    re.IGNORECASE,
)


def find_address(override):
    if override:
        if not ADDRESS.fullmatch(override):
            raise RuntimeError("Use a 12-digit Bluetooth address, such as 00:11:22:33:44:55.")
        return int(override.replace(":", "").replace("-", ""), 16)

    powershell = Path(os.environ["SystemRoot"]) / "System32/WindowsPowerShell/v1.0/powershell.exe"
    query = (
        "$ErrorActionPreference = 'Stop'; "
        "Get-PnpDevice -PresentOnly -Class Bluetooth | "
        "Where-Object { $_.FriendlyName -like '*Liberty 4 NC*' } | "
        "ForEach-Object { $_.InstanceId }"
    )
    try:
        result = subprocess.run(
            [str(powershell), "-NoProfile", "-NonInteractive", "-Command", query],
            capture_output=True, text=True, errors="replace", timeout=10, check=True,
        )
    except (OSError, subprocess.TimeoutExpired, subprocess.CalledProcessError) as error:
        raise RuntimeError("Windows Bluetooth discovery failed. Start with --address and the earbuds' Bluetooth address.") from error

    addresses = {int(match[1], 16) for match in
                 (DEVICE_ID.match(line.strip()) for line in result.stdout.splitlines()) if match}
    if len(addresses) != 1:
        raise RuntimeError(
            "Could not identify one Liberty 4 NC. Connect it in Windows Bluetooth settings, "
            "or restart with --address and the earbuds' Bluetooth address."
        )
    return addresses.pop()


def service_address(address):
    # SOCKADDR_BTH is packed. A zero port asks Windows to resolve the vendor UUID via SDP.
    return struct.pack("<HQ16sI", AF_BTH, address, SERVICE.bytes_le, 0)


def connect(sock, address):
    winsock = ctypes.WinDLL("Ws2_32.dll")
    winsock.connect.argtypes = (ctypes.c_size_t, ctypes.c_char_p, ctypes.c_int)
    winsock.connect.restype = ctypes.c_int
    winsock.WSAGetLastError.argtypes = ()
    winsock.WSAGetLastError.restype = ctypes.c_int
    endpoint = service_address(address)
    sock.setblocking(False)
    if winsock.connect(sock.fileno(), endpoint, len(endpoint)) != 0:
        error = winsock.WSAGetLastError()
        if error != 10035:  # WSAEWOULDBLOCK
            raise ctypes.WinError(error)
        _, writable, failed = select.select([], [sock], [sock], 10)
        if not writable and not failed:
            raise TimeoutError("Bluetooth connection timed out")
        error = sock.getsockopt(socket.SOL_SOCKET, socket.SO_ERROR)
        if error or failed:
            raise ctypes.WinError(error or 10061)
    sock.settimeout(2)


def read_reply(sock, command):
    pending = bytearray()
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        sock.settimeout(max(.001, deadline - time.monotonic()))
        try:
            data = sock.recv(4096)
        except TimeoutError:
            return None
        if not data:
            raise RuntimeError("The earbuds closed the Bluetooth control connection.")
        pending.extend(data)
        while len(pending) >= 2:
            if pending[:2] != b"\x09\xff":
                del pending[0]
                continue
            if len(pending) < 9:
                break
            length = int.from_bytes(pending[7:9], "little")
            if not 10 <= length <= 1024:
                del pending[0]
                continue
            if len(pending) < length:
                break
            packet = pending[:length]
            del pending[:length]
            if packet[5:7] == command and sum(packet[:-1]) % 256 == packet[-1]:
                return bytes(packet[9:-1])
    return None


@contextmanager
def bluetooth_windows(address_override, encode):
    address = find_address(address_override)
    try:
        sock = socket.socket(AF_BTH, socket.SOCK_STREAM, BTHPROTO_RFCOMM)
    except OSError as error:
        raise RuntimeError("Windows could not open a Bluetooth Classic socket. Check the Bluetooth adapter.") from error

    with sock:
        try:
            connect(sock, address)
        except OSError as error:
            raise RuntimeError(
                f"Windows could not open the Liberty 4 NC control service ({error}). "
                "Close the Soundcore phone app, reconnect the earbuds, and try again."
            ) from error

        def command(group, number, payload=b""):
            sock.settimeout(2)
            sock.sendall(encode(group, number, payload))
            return read_reply(sock, bytes((group, number)))

        yield command
