from alfred_brain.persona import system_prompt


def test_full_has_persona_and_constraint():
    p = system_prompt("full")
    assert "ALFRED" in p
    assert "reluctant superintelligence" in p.lower()
    assert "sir" in p.lower()
    assert "unambiguous" in p.lower()  # high-stakes clarity constraint


def test_off_drops_snark_but_keeps_identity_and_constraint():
    p = system_prompt("off")
    assert "ALFRED" in p
    assert "reluctant superintelligence" not in p.lower()
    assert "unambiguous" in p.lower()


def test_light_is_subtle():
    p = system_prompt("light")
    assert "subtle" in p.lower()
    assert "unambiguous" in p.lower()
