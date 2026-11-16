#!/usr/bin/env python3
"""Local web controls for Soundcore Liberty 4 NC (A3947)."""
import argparse
import contextlib
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import math
from pathlib import Path
import secrets
import select
import subprocess
import tempfile
import sys
import webbrowser
import time

ROOT = Path(__file__).resolve().parent
HOST = "127.0.0.1"
MODES = ("Noise Cancellation", "Transparency", "Normal")
EQ_PRESET = slice(37, 39)
EQ_LEFT = slice(39, 49)
EQ_RIGHT = slice(49, 59)
HEAR_ID_ENABLED = 60
HEAR_ID_DATA = slice(61, 106)
HEAR_ID_GENRE = 106
LISTENING_MODE = slice(126, 133)
MISSING_CURVE = bytes([255]) * 10


def frame(group, command, payload=b""):
    data = bytes((8, 238, 0, 0, 0, group, command))
    data += (10 + len(payload)).to_bytes(2, "little") + payload
    return data + bytes((sum(data) % 256,))


# Soundcore's eight-band compensation matrix, documented by OpenSCQ30
# and soundcore-lr-balance. Compute one curve to apply to both earbuds.
DRC = (
    (1.26, -.6035, .177, -.0494, .0345, -.0197, .0075, -.00217),
    (-.6035, 1.6435, -.6885, .204, -.068, .045, -.0235, .0075),
    (.177, -.6885, 1.6435, -.6885, .208, -.07, .045, -.0197),
    (-.0494, .204, -.6885, 1.6435, -.697, .208, -.068, .0345),
    (.0345, -.068, .208, -.697, 1.6435, -.6885, .204, -.0494),
    (-.0197, .045, -.07, .208, -.6885, 1.6435, -.6885, .177),
    (.0075, -.0235, .045, -.068, .204, -.6885, 1.7385, -.6035),
    (-.00217, .0075, -.0197, .0345, -.0494, .177, -.6035, 1.5),
)


def eq_payload(state, bands):
    encoded = bytes(round(x * 10) + 120 for x in bands)
    projected = [sum(coef * x for coef, x in zip(row, bands)) for row in DRC]
    drc = bytes(120 + int(math.copysign(math.floor(abs(x) + .5), x))
                for x in projected) + bytes((120, 0))
    return (b"\xfe\xfe" + bytes((state[HEAR_ID_GENRE], 0))
            + (encoded + bytes((120, 120))) * 2
            + bytes(3) + state[HEAR_ID_DATA]
            + drc + drc + b"\x00")


@contextlib.contextmanager
def bluetooth_macos(helper):
    with tempfile.TemporaryFile(mode="w+t") as errors:
        process = subprocess.Popen([str(helper)], text=True, stdin=subprocess.PIPE,
                                   stdout=subprocess.PIPE, stderr=errors)

        def line():
            if not select.select([process.stdout], [], [], 12)[0]:
                raise RuntimeError("Bluetooth timed out. Reconnect the earbuds and retry.")
            result = process.stdout.readline()
            if result == "":
                errors.seek(0)
                raise RuntimeError(errors.read().strip() or
                                   "Bluetooth access failed. Allow Terminal in Privacy & Security → Bluetooth.")
            return result.rstrip("\n")

        def command(group, number, payload=b""):
            process.stdin.write(frame(group, number, payload).hex() + "\n")
            process.stdin.flush()
            response = line()
            return None if response == "-" else bytes.fromhex(response)

        try:
            if line() != "READY":
                raise RuntimeError("The Bluetooth helper failed to start.")
            yield command
        finally:
            process.stdin.close()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
            process.stdout.close()


def get_state(send):
    state = send(1, 1)
    if not state or len(state) < LISTENING_MODE.stop or state[1] not in (0, 1):
        raise RuntimeError("The earbuds did not return a recognized Liberty 4 NC state. Reconnect them and try again.")
    return state


def reported_curves(state):
    return [
        curve[:8] for curve in (state[EQ_LEFT], state[EQ_RIGHT])
        if curve != MISSING_CURVE and all(b < 255 for b in curve[:8])
    ]


def status(state):
    curves = reported_curves(state)
    mode = state[LISTENING_MODE.start]
    return {
        "mode": mode if mode < len(MODES) else None,
        "stereo": state[1] == 1,
        "hearID": state[HEAR_ID_ENABLED] == 1,
        "eq": [round((x - 120) / 10, 1) for x in curves[0]] if curves else None,
        "firmware": state[6:11].decode("ascii", errors="replace"),
    }


def confirm_state(send, matches, message):
    # Some firmware acknowledges a change before the next state read reflects it.
    for _ in range(3):
        time.sleep(.15)
        state = get_state(send)
        if matches(state):
            return status(state)
    return {**status(state), "warning": message}


def use_device(open_bluetooth, action, value):
    with open_bluetooth() as send:
        state = get_state(send)
        if action == "mode":
            mode = state[LISTENING_MODE]
            if mode[0] >= len(MODES):
                raise RuntimeError("The earbuds returned an unknown listening mode.")
            if value != mode[0]:
                send(6, 129, bytes((value,)) + mode[1:])
                return confirm_state(
                    send, lambda current: current[LISTENING_MODE.start] == value,
                    "The earbuds did not confirm the requested listening mode.",
                )
        if action == "eq":
            if state[1] != 1:
                raise RuntimeError("Take both earbuds out of the case before applying EQ.")
            if not reported_curves(state):
                raise RuntimeError("The earbuds did not report an EQ curve. Read the earbuds again.")
            send(3, 135, eq_payload(state, value))
            stored = bytes(round(x * 10) + 120 for x in value)

            def matches(current):
                curves = reported_curves(current)
                return (current[EQ_PRESET] == b"\xfe\xfe" and curves
                        and all(curve == stored for curve in curves)
                        and current[HEAR_ID_ENABLED] == 0)

            return confirm_state(send, matches, "The earbuds did not confirm the custom EQ.")
        return status(state)


class Handler(BaseHTTPRequestHandler):
    def answer(self, code, body, mime="application/json"):
        self.send_response(code)
        self.send_header("Content-Type", mime)
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy",
                         "default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; frame-ancestors 'none'")
        data = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.headers.get("Host") != self.server.host:
            self.answer(403, {"error": "Open the local URL printed in Terminal."})
            return
        assets = {"/": ("index.html", "text/html; charset=utf-8"),
                  "/style.css": ("style.css", "text/css"),
                  "/app.js": ("app.js", "text/javascript")}
        if self.path not in assets:
            self.answer(404, {"error": "Page not found."})
            return
        name, mime = assets[self.path]
        body = (ROOT / name).read_bytes().replace(b"__TOKEN__", self.server.token.encode())
        self.answer(200, body, mime)

    def do_POST(self):
        if (self.headers.get("Host") != self.server.host or self.path != "/control"
                or self.headers.get("Origin") != "http://" + self.server.host
                or not secrets.compare_digest(self.headers.get("X-Soundcore-Token", ""), self.server.token)):
            self.answer(403, {"error": "Reload the local app to reconnect."})
            return
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 < size <= 1024:
                raise ValueError
            data = json.loads(self.rfile.read(size))
            action, value = data["action"], data.get("value")
            if action == "eq":
                if not isinstance(value, list) or len(value) != 8 or not all(
                        type(x) in (int, float) and -12 <= x <= 13.4 for x in value):
                    raise ValueError
                value = [round(x, 1) for x in value]
            elif action == "mode":
                if type(value) is not int or not 0 <= value < len(MODES):
                    raise ValueError
            elif action != "status":
                raise ValueError
        except (ValueError, KeyError, TypeError, AttributeError):
            self.answer(400, {"error": "Invalid control values."})
            return

        try:
            result = self.server.device(action, value)
        except (OSError, RuntimeError) as error:
            self.answer(503, {"error": str(error)})
            return
        self.answer(200, result)


class Server(HTTPServer):
    def get_request(self):
        connection, address = super().get_request()
        connection.settimeout(30)
        return connection, address


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--helper", type=Path)
    parser.add_argument("--address", help="Override Windows Bluetooth device detection")
    parser.add_argument("--port", type=int, default=0)
    args = parser.parse_args()
    if sys.platform == "win32":
        from windows_bluetooth import bluetooth_windows

        def open_bluetooth():
            return bluetooth_windows(args.address, frame)
    elif sys.platform == "darwin" and args.helper:
        def open_bluetooth():
            return bluetooth_macos(args.helper.resolve())
    else:
        parser.error("Use Start-Soundcore.command on macOS or Start-Soundcore.bat on Windows.")

    with Server((HOST, args.port), Handler) as server:
        server.host = f"{HOST}:{server.server_port}"
        server.token = secrets.token_urlsafe(32)
        server.device = lambda action, value: use_device(open_bluetooth, action, value)
        url = "http://" + server.host
        print(f"Soundcore Control → {url}\nLeave this window open. Press Ctrl+C to stop.", flush=True)
        webbrowser.open(url)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
