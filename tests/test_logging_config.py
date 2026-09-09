import logging

import app.main  # noqa: F401  (import side effect: module-level logging.basicConfig)


def test_root_logger_has_a_handler():
    assert logging.getLogger().handlers, (
        "root logger has no handlers configured; log records emitted anywhere "
        "in the app (e.g. via logger.info) will be silently dropped"
    )


def test_chat_requests_logger_reaches_info():
    assert logging.getLogger("chat.requests").getEffectiveLevel() <= logging.INFO


def test_banking_audit_logger_reaches_info():
    assert logging.getLogger("banking.audit").getEffectiveLevel() <= logging.INFO
