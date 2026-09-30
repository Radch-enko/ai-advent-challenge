from copia.service import app


def test_fastapi_does_not_auto_configure_otel_exporters() -> None:
    telemetry = getattr(app, "_telemetry", None)
    if telemetry is None:
        telemetry = app.extra.get("telemetry")

    assert telemetry is not None
    assert telemetry["auto_configure"] is False
