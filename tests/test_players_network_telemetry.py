import json

from scraping_biwenger.players.network_telemetry import (
    PlayerRunNetworkTelemetry,
    attach_page_network_telemetry,
    network_action,
)


class FakePage:
    def __init__(self):
        self.handlers = {}

    def on(self, event_name, handler):
        self.handlers.setdefault(event_name, []).append(handler)

    def emit(self, event_name, payload):
        for handler in self.handlers.get(event_name, []):
            handler(payload)


class FakeRequest:
    def __init__(self, url: str, method: str = "GET", resource_type: str = "xhr", failure_text: str = ""):
        self._url = url
        self._method = method
        self._resource_type = resource_type
        self._failure_text = failure_text

    def url(self):
        return self._url

    def method(self):
        return self._method

    def resource_type(self):
        return self._resource_type

    def failure(self):
        return {"errorText": self._failure_text}


class FakeResponse:
    def __init__(self, request, status: int, url: str):
        self._request = request
        self._status = status
        self._url = url

    def request(self):
        return self._request

    def status(self):
        return self._status

    def url(self):
        return self._url


class FakeDownload:
    def __init__(self, url: str, suggested_filename: str):
        self._url = url
        self._suggested_filename = suggested_filename

    def url(self):
        return self._url

    def suggested_filename(self):
        return self._suggested_filename


def test_network_telemetry_writes_raw_events_and_summary(tmp_path):
    page = FakePage()
    telemetry = PlayerRunNetworkTelemetry(tmp_path)
    attach_page_network_telemetry(page, telemetry)

    with network_action(page, "open_player_href", player_slug="mbappe", href="/la-liga/players/mbappe"):
        request = FakeRequest("https://biwenger.as.com/la-liga/players/mbappe", resource_type="document")
        page.emit("request", request)
        page.emit("response", FakeResponse(request, 200, "https://biwenger.as.com/la-liga/players/mbappe"))

    with network_action(page, "download_value_csv", player_slug="mbappe"):
        request = FakeRequest("https://biwenger.as.com/api/value/export.csv")
        page.emit("request", request)
        page.emit("response", FakeResponse(request, 200, "https://biwenger.as.com/api/value/export.csv"))
        page.emit("download", FakeDownload("https://biwenger.as.com/api/value/export.csv", "mbappe.csv"))

    telemetry.close()

    events = [json.loads(line) for line in telemetry.telemetry_path.read_text(encoding="utf-8").splitlines()]
    assert any(event["type"] == "action_started" and event["action"] == "open_player_href" for event in events)
    assert any(event["type"] == "request" and event["action"] == "download_value_csv" for event in events)
    assert any(event["type"] == "download" for event in events)

    summary = json.loads(telemetry.summary_path.read_text(encoding="utf-8"))
    assert summary["overall"]["request_count"] == 2
    assert summary["core_overall"]["request_count"] == 2
    assert summary["actions"]["open_player_href"]["request_count"] == 1
    assert summary["core_actions"]["open_player_href"]["request_count"] == 1
    assert summary["actions"]["download_value_csv"]["download_count"] == 1
    assert summary["core_actions"]["download_value_csv"]["download_count"] == 1


def test_network_telemetry_attributes_response_to_request_action(tmp_path):
    page = FakePage()
    telemetry = PlayerRunNetworkTelemetry(tmp_path)
    attach_page_network_telemetry(page, telemetry)

    with network_action(page, "open_player_href", player_slug="mbappe"):
        request = FakeRequest("https://biwenger.as.com/la-liga/players/mbappe", resource_type="document")
        page.emit("request", request)

    with network_action(page, "open_value_tab", player_slug="mbappe"):
        page.emit("response", FakeResponse(request, 200, "https://biwenger.as.com/la-liga/players/mbappe"))
        failed_request = FakeRequest(
            "https://biwenger.as.com/api/value",
            resource_type="fetch",
            failure_text="timed out",
        )
        page.emit("request", failed_request)
        page.emit("requestfailed", failed_request)

    telemetry.close()

    summary = json.loads(telemetry.summary_path.read_text(encoding="utf-8"))
    assert summary["actions"]["open_player_href"]["response_count"] == 1
    assert summary["actions"]["open_value_tab"]["response_count"] == 0
    assert summary["actions"]["open_value_tab"]["failed_request_count"] == 1
    assert summary["core_actions"]["open_value_tab"]["failed_request_count"] == 1
