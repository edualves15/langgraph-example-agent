from app.errors import describe_error, error_hint


class _HttpErr(Exception):
    def __init__(self, status_code):
        super().__init__("provider error")
        self.status_code = status_code


def test_describe_error_known_categories():
    assert "Limite" in describe_error(_HttpErr(429))
    assert "autenticação" in describe_error(_HttpErr(401)).lower()
    assert "indisponível" in describe_error(_HttpErr(503)).lower()
    assert "tempo limite" in describe_error(TimeoutError("x")).lower()


def test_describe_error_generic_does_not_leak():
    msg = describe_error(ValueError("/secret/path leaked token=abc123"))
    assert "secret" not in msg
    assert "token" not in msg
    assert "ValueError" not in msg
    assert "inesperado" in msg.lower()


def test_error_hint_for_log_has_detail():
    hint = error_hint(ValueError("boom on /secret/path"))
    assert hint.startswith("ValueError")
    assert "boom" in hint
