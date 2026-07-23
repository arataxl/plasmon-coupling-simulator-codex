"""実サーバーと実SSEを通すブラウザUI回帰テスト。"""

from __future__ import annotations

import base64
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time
from typing import Any
from urllib.parse import urlparse
from urllib.request import urlopen


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def _chrome_executable() -> str:
    candidates = (
        os.environ.get("CHROME_PATH"),
        shutil.which("chrome"),
        shutil.which("chrome.exe"),
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    )
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return candidate
    raise AssertionError("Headless Chrome is required for the live browser workflow test")


def _available_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def _wait_until(predicate: Any, *, timeout_seconds: float, description: str) -> Any:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(0.05)
    raise AssertionError(f"Timed out while waiting for {description}")


class _ChromeCdp:
    """追加依存なしで最小限のChrome DevTools Protocolを扱う。"""

    def __init__(self, web_socket_url: str) -> None:
        parsed = urlparse(web_socket_url)
        assert parsed.hostname is not None
        assert parsed.port is not None
        self._socket = socket.create_connection((parsed.hostname, parsed.port), timeout=5)
        self._socket.settimeout(5)
        resource = parsed.path
        if parsed.query:
            resource = f"{resource}?{parsed.query}"
        key = base64.b64encode(os.urandom(16)).decode("ascii")
        request = (
            f"GET {resource} HTTP/1.1\r\n"
            f"Host: {parsed.hostname}:{parsed.port}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            "Sec-WebSocket-Version: 13\r\n\r\n"
        ).encode("ascii")
        self._socket.sendall(request)
        response = self._read_http_headers()
        assert b" 101 " in response.splitlines()[0], response.decode("latin-1", "replace")
        self._next_id = 1
        self.events: list[dict[str, Any]] = []

    def close(self) -> None:
        self._socket.close()

    def call(self, method: str, parameters: dict[str, Any] | None = None) -> dict[str, Any]:
        request_id = self._next_id
        self._next_id += 1
        request: dict[str, Any] = {"id": request_id, "method": method}
        if parameters:
            request["params"] = parameters
        self._send_json(request)
        while True:
            message = self._receive_json()
            if message.get("id") == request_id:
                if "error" in message:
                    raise AssertionError(f"CDP {method} failed: {message['error']}")
                return message.get("result", {})
            self.events.append(message)

    def evaluate(self, expression: str) -> Any:
        result = self.call(
            "Runtime.evaluate",
            {
                "expression": expression,
                "awaitPromise": True,
                "returnByValue": True,
            },
        )
        details = result["result"]
        if "exceptionDetails" in result:
            raise AssertionError(f"JavaScript evaluation failed: {result['exceptionDetails']}")
        return details.get("value")

    def _read_http_headers(self) -> bytes:
        data = bytearray()
        while b"\r\n\r\n" not in data:
            chunk = self._socket.recv(1024)
            if not chunk:
                raise AssertionError("Chrome closed the CDP socket during the WebSocket handshake")
            data.extend(chunk)
        return bytes(data)

    def _receive_exactly(self, length: int) -> bytes:
        data = bytearray()
        while len(data) < length:
            chunk = self._socket.recv(length - len(data))
            if not chunk:
                raise AssertionError("Chrome closed the CDP socket")
            data.extend(chunk)
        return bytes(data)

    def _send_frame(self, opcode: int, payload: bytes) -> None:
        frame = bytearray([0x80 | opcode])
        payload_length = len(payload)
        if payload_length < 126:
            frame.append(0x80 | payload_length)
        elif payload_length <= 0xFFFF:
            frame.append(0x80 | 126)
            frame.extend(payload_length.to_bytes(2, "big"))
        else:
            frame.append(0x80 | 127)
            frame.extend(payload_length.to_bytes(8, "big"))
        mask = os.urandom(4)
        frame.extend(mask)
        frame.extend(byte ^ mask[index % 4] for index, byte in enumerate(payload))
        self._socket.sendall(frame)

    def _send_json(self, message: dict[str, Any]) -> None:
        self._send_frame(0x1, json.dumps(message).encode("utf-8"))

    def _receive_json(self) -> dict[str, Any]:
        payload = bytearray()
        while True:
            first, second = self._receive_exactly(2)
            opcode = first & 0x0F
            final = bool(first & 0x80)
            payload_length = second & 0x7F
            if payload_length == 126:
                payload_length = int.from_bytes(self._receive_exactly(2), "big")
            elif payload_length == 127:
                payload_length = int.from_bytes(self._receive_exactly(8), "big")
            if second & 0x80:
                mask = self._receive_exactly(4)
                raw_payload = bytes(
                    byte ^ mask[index % 4]
                    for index, byte in enumerate(self._receive_exactly(payload_length))
                )
            else:
                raw_payload = self._receive_exactly(payload_length)
            if opcode == 0x8:
                raise AssertionError("Chrome closed the CDP socket")
            if opcode == 0x9:
                self._send_frame(0xA, raw_payload)
                continue
            if opcode not in {0x0, 0x1}:
                continue
            payload.extend(raw_payload)
            if final:
                return json.loads(payload.decode("utf-8"))


def _wait_for_http(url: str) -> None:
    def responds() -> bool:
        try:
            with urlopen(url, timeout=1) as response:
                return response.status == 200
        except OSError:
            return False

    _wait_until(responds, timeout_seconds=15, description="the FastAPI server")


def _start_chrome(tmp_path: Path) -> tuple[subprocess.Popen[bytes], _ChromeCdp]:
    profile = tmp_path / "chrome-profile"
    process = subprocess.Popen(
        [
            _chrome_executable(),
            "--headless=new",
            "--disable-gpu",
            "--no-sandbox",
            "--remote-debugging-port=0",
            f"--user-data-dir={profile}",
            "about:blank",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    active_port_file = profile / "DevToolsActivePort"
    _wait_until(
        active_port_file.is_file,
        timeout_seconds=15,
        description="Chrome DevTools endpoint",
    )
    debug_port = active_port_file.read_text(encoding="utf-8").splitlines()[0]
    with urlopen(f"http://127.0.0.1:{debug_port}/json/list", timeout=5) as response:
        targets = json.load(response)
    target = next(target for target in targets if target.get("type") == "page")
    client = _ChromeCdp(target["webSocketDebuggerUrl"])
    client.call("Page.enable")
    client.call("Runtime.enable")
    client.call("Log.enable")
    return process, client


def _stop_process(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=10)


def test_real_page_keeps_japanese_default_and_renders_history_after_sse(
    tmp_path: Path,
) -> None:
    """実index.htmlの初期化、SSE完了、履歴DOM描画を一続きで検証する。"""
    port = _available_port()
    server = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "src.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        cwd=REPOSITORY_ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    chrome: subprocess.Popen[bytes] | None = None
    client: _ChromeCdp | None = None
    try:
        base_url = f"http://127.0.0.1:{port}/"
        _wait_for_http(base_url)
        chrome, client = _start_chrome(tmp_path)
        client.call("Page.navigate", {"url": base_url})

        _wait_until(
            lambda: client.evaluate(
                "Boolean(window.PlasmonI18n && window.PlasmonProgress && window.PlasmonResults)"
            ),
            timeout_seconds=15,
            description="the real UI initialization",
        )
        _wait_until(
            lambda: client.evaluate("window.PlasmonI18n.getLanguage() === 'ja'"),
            timeout_seconds=15,
            description="the Japanese default language",
        )
        assert client.evaluate("document.documentElement.lang") == "ja"
        assert client.evaluate("document.documentElement.dataset.uiReady") == "true"
        assert client.evaluate("getComputedStyle(document.body).visibility") == "visible"

        client.evaluate("document.querySelector('[data-language=\"en\"]').click()")
        _wait_until(
            lambda: client.evaluate("window.PlasmonI18n.getLanguage() === 'en'"),
            timeout_seconds=15,
            description="manual English language selection",
        )
        client.call("Page.reload", {"ignoreCache": True})
        _wait_until(
            lambda: client.evaluate(
                "Boolean(window.PlasmonI18n && window.PlasmonI18n.getLanguage() === 'en')"
            ),
            timeout_seconds=15,
            description="the persisted language selection after reload",
        )
        client.evaluate("document.querySelector('[data-language=\"ja\"]').click()")
        _wait_until(
            lambda: client.evaluate("window.PlasmonI18n.getLanguage() === 'ja'"),
            timeout_seconds=15,
            description="restoring Japanese before the simulation",
        )

        client.evaluate(
            """
            (() => {
              document.getElementById('apply-dimer').click();
              document.getElementById('start-wavelength-nm').value = '400';
              document.getElementById('end-wavelength-nm').value = '520';
              document.getElementById('wavelength-step-nm').value = '10';
            })()
            """
        )
        _wait_until(
            lambda: client.evaluate("document.querySelectorAll('#particle-rows tr').length === 2"),
            timeout_seconds=15,
            description="the dimer preset layout",
        )
        client.evaluate("document.getElementById('simulation-form').requestSubmit()")
        _wait_until(
            lambda: client.evaluate(
                "document.querySelectorAll('#history-list .history-entry').length === 1"
            ),
            timeout_seconds=30,
            description="the first SSE-completed history entry",
        )
        assert client.evaluate(
            "!document.getElementById('result-smoothing-control').hidden && "
            "document.getElementById('result-smoothing').checked"
        ) is True
        assert client.evaluate(
            "JSON.parse(localStorage.getItem('plasmon-coupling-simulator.history.v1'))[0].spectrum."
            "raw_c_ext_m2.some((value, index, raw) => value !== "
            "JSON.parse(localStorage.getItem('plasmon-coupling-simulator.history.v1'))[0].spectrum.c_ext_m2[index])"
        ) is True
        client.evaluate("document.getElementById('experimental-quadrupole-coupling').click()")
        client.evaluate("document.getElementById('simulation-form').requestSubmit()")
        _wait_until(
            lambda: client.evaluate(
                "document.querySelectorAll('#history-list .history-entry').length === 2"
            ),
            timeout_seconds=30,
            description="the second SSE-completed history entry",
        )
        labels = client.evaluate(
            "[...document.querySelectorAll('.history-entry-label')].map((item) => item.textContent)"
        )
        assert any("四極子: あり" in label for label in labels)
        assert any("四極子: なし" in label for label in labels)
        smoothed_result_values = client.evaluate(
            "JSON.stringify(document.getElementById('spectrum-plot').data.map((trace) => trace.y))"
        )
        client.evaluate(
            "(() => { const control = document.getElementById('result-smoothing'); "
            "control.checked = false; control.dispatchEvent(new Event('change')); })()"
        )
        raw_result_values = client.evaluate(
            "JSON.stringify(document.getElementById('spectrum-plot').data.map((trace) => trace.y))"
        )
        assert raw_result_values != smoothed_result_values
        client.evaluate(
            "(() => { const control = document.getElementById('result-smoothing'); "
            "control.checked = true; control.dispatchEvent(new Event('change')); })()"
        )
        client.evaluate("document.querySelector('.history-detail-button').click()")
        assert client.evaluate("document.getElementById('history-detail-dialog').open") is True
        assert client.evaluate("document.querySelectorAll('#history-detail-particles li').length") == 2
        client.evaluate("document.getElementById('history-detail-close').click()")
        client.evaluate(
            """
            (() => {
              document.getElementById('history-select-all').click();
            })()
            """
        )
        assert client.evaluate(
            "[...document.querySelectorAll('.history-entry input[type=checkbox]')].every((item) => item.checked)"
        ) is True
        assert client.evaluate("!document.getElementById('history-compare').disabled") is True
        client.evaluate(
            """
            (() => {
              const smoothing = document.getElementById('result-smoothing');
              smoothing.checked = false;
              smoothing.dispatchEvent(new Event('change'));
              document.getElementById('history-compare').click();
            })()
            """
        )
        _wait_until(
            lambda: client.evaluate(
                "Boolean(document.getElementById('spectrum-plot').data && "
                "document.getElementById('spectrum-plot').data.length === 2)"
            ),
            timeout_seconds=15,
            description="the raw-spectrum comparison",
        )
        raw_comparison_values = client.evaluate(
            "JSON.stringify(document.getElementById('spectrum-plot').data.map((trace) => trace.y))"
        )
        client.evaluate(
            "(() => { const smoothing = document.getElementById('result-smoothing'); "
            "smoothing.checked = true; smoothing.dispatchEvent(new Event('change')); })()"
        )
        smoothed_comparison_values = client.evaluate(
            "JSON.stringify(document.getElementById('spectrum-plot').data.map((trace) => trace.y))"
        )
        assert raw_comparison_values != smoothed_comparison_values
        client.evaluate(
            """
            (() => {
              const quantity = document.getElementById('history-compare-quantity');
              quantity.value = 'c_sca';
              quantity.dispatchEvent(new Event('change'));
              const mode = document.getElementById('history-normalization-mode');
              mode.value = 'peak';
              mode.dispatchEvent(new Event('change'));
              document.getElementById('history-compare').click();
            })()
            """
        )
        _wait_until(
            lambda: client.evaluate(
                "Boolean(document.getElementById('spectrum-plot').data && "
                "document.getElementById('spectrum-plot').data.length === 2)"
            ),
            timeout_seconds=15,
            description="the Csca peak-normalized comparison",
        )
        assert client.evaluate(
            "document.getElementById('spectrum-plot').data.every((trace) => "
            "Math.abs(Math.max(...trace.y) - 1) < 1e-12)"
        ) is True
        client.evaluate(
            """
            (() => {
              const mode = document.getElementById('history-normalization-mode');
              mode.value = 'reference';
              mode.dispatchEvent(new Event('change'));
              const reference = document.getElementById('history-reference-wavelength-nm');
              reference.value = '1600';
              reference.dispatchEvent(new Event('change'));
            })()
            """
        )
        _wait_until(
            lambda: client.evaluate(
                "!document.getElementById('history-comparison-error').hidden"
            ),
            timeout_seconds=15,
            description="the out-of-range reference-wavelength error",
        )
        client.evaluate(
            """
            (() => {
              const reference = document.getElementById('history-reference-wavelength-nm');
              reference.value = '460';
              reference.dispatchEvent(new Event('change'));
            })()
            """
        )
        _wait_until(
            lambda: client.evaluate(
                "document.getElementById('history-comparison-error').hidden"
            ),
            timeout_seconds=15,
            description="the in-range reference-wavelength comparison",
        )
        assert client.evaluate(
            """
            document.getElementById('spectrum-plot').data.every((trace) => {
              const wavelengths = trace.x;
              const values = trace.y;
              const upper = wavelengths.findIndex((wavelength) => wavelength >= 460);
              if (upper < 0) return false;
              if (wavelengths[upper] === 460) return Math.abs(values[upper] - 1) < 1e-12;
              const lower = upper - 1;
              const fraction = (460 - wavelengths[lower]) / (wavelengths[upper] - wavelengths[lower]);
              const interpolated = values[lower] + fraction * (values[upper] - values[lower]);
              return Math.abs(interpolated - 1) < 1e-12;
            })
            """
        ) is True
        client.evaluate("document.getElementById('history-deselect-all').click()")
        assert client.evaluate(
            "[...document.querySelectorAll('.history-entry input[type=checkbox]')].every((item) => !item.checked)"
        ) is True
        assert client.evaluate("document.getElementById('history-compare').disabled") is True
        assert client.evaluate("document.getElementById('error-message').hidden") is True

        # 最後の評価で、直前までに到着したコンソール／例外イベントも回収する。
        client.evaluate("0")
        runtime_exceptions = [
            event for event in client.events if event.get("method") == "Runtime.exceptionThrown"
        ]
        log_errors = [
            event
            for event in client.events
            if event.get("method") == "Log.entryAdded"
            and event.get("params", {}).get("entry", {}).get("level") == "error"
        ]
        assert not runtime_exceptions
        assert not log_errors
    finally:
        if client is not None:
            client.close()
        if chrome is not None:
            _stop_process(chrome)
        _stop_process(server)
