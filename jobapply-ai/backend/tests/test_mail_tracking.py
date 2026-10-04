from app.services.mail_tracking import classify_message


def test_mail_classification_prioritises_safety_signals():
    assert classify_message("Mail delivery failed", "undeliverable") == "bounce"
    assert classify_message("Automatic reply", "I am out of office") == "auto_reply"
    assert classify_message("Interview invitation", "schedule a call") == "interview"
    assert classify_message("Application update", "unfortunately we chose another candidate") == "rejection"
    assert classify_message("Re: application", "Thanks for reaching out") == "reply"


def test_mail_classification_is_safe_for_empty_metadata():
    assert classify_message("", "") == "reply"
