from borrowed_hands.timeout import InactivityTimer, Phase


def make():
    return InactivityTimer(now=0, idle_limit=120, prompt_limit=60)


def test_prompt_after_idle_limit():
    t = make()
    assert t.tick(119) is Phase.ACTIVE
    assert t.tick(120) is Phase.PROMPT


def test_activity_resets_idle():
    t = make()
    t.activity(100)
    assert t.tick(200) is Phase.ACTIVE
    assert t.tick(220) is Phase.PROMPT


def test_no_answer_ends_after_prompt_limit():
    t = make()
    t.tick(120)
    assert t.tick(179) is Phase.PROMPT
    assert t.tick(180) is Phase.ENDED


def test_yes_resets_and_no_ends():
    t = make()
    t.tick(120)
    t.answer(True, 130)
    assert t.phase is Phase.ACTIVE
    assert t.tick(249) is Phase.ACTIVE
    assert t.tick(250) is Phase.PROMPT
    t.answer(False, 251)
    assert t.phase is Phase.ENDED


def test_activity_does_not_dismiss_prompt():
    t = make()
    t.tick(120)
    t.activity(125)
    assert t.tick(180) is Phase.ENDED


def test_seconds_left():
    t = make()
    assert t.seconds_left(20) == 100
    t.tick(120)
    assert t.seconds_left(150) == 30
