from nightwatch.security.access import RealtimeTicketRegistry, valid_frontend_token


def test_frontend_token_comparison_and_one_time_ticket() -> None:
    assert valid_frontend_token("secret", "secret")
    assert not valid_frontend_token("secret", "other")
    registry = RealtimeTicketRegistry()
    ticket = registry.issue("test-secret", 30)
    assert registry.consume(ticket, "test-secret")
    assert not registry.consume(ticket, "test-secret")
