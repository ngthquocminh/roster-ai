from fastapi.testclient import TestClient

from api.deps import get_telemetry_sink
from api.main import app


class RecordingSink:
    def __init__(self) -> None:
        self.records = []

    def emit(self, record) -> None:
        self.records.append(record)


def test_http_middleware_emits_templated_request_record() -> None:
    sink = RecordingSink()
    previous = dict(app.dependency_overrides)
    app.dependency_overrides[get_telemetry_sink] = lambda: sink
    try:
        with TestClient(app) as client:
            response = client.get("/health")
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous)

    assert response.status_code == 200
    records = [r for r in sink.records if r.event == "api.request.completed"]
    assert len(records) == 1
    assert records[0].labels == {
        "route_template": "/health",
        "method": "GET",
        "status_class": "2xx",
    }
    assert records[0].duration_ms is not None
    assert records[0].correlation.request_id is not None
