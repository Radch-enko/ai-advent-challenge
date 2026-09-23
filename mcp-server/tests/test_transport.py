import server as finances_server


def test_cli_uses_stdio_by_default(monkeypatch) -> None:
    calls = []
    monkeypatch.setattr(
        finances_server.server, "run", lambda *args, **kwargs: calls.append((args, kwargs))
    )

    finances_server.main([])

    assert calls == [(("stdio",), {})]


def test_cli_runs_streamable_http_on_fixed_loopback_endpoint(monkeypatch) -> None:
    calls = []
    monkeypatch.setattr(
        finances_server.server, "run", lambda *args, **kwargs: calls.append((args, kwargs))
    )

    finances_server.main(["--transport", "streamable-http"])

    assert calls == [
        (
            ("streamable-http",),
            {"host": "127.0.0.1", "port": 8001, "streamable_http_path": "/mcp"},
        )
    ]
