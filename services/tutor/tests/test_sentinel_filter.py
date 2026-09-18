from tutor.state_machine import SentinelFilter
from tests.conftest import SENT


def run(chunks):
    f = SentinelFilter()
    out = "".join(f.feed(c) for c in chunks) + f.flush()
    return out, f.found


def test_passthrough_without_sentinel():
    assert run(["Hello ", "world."]) == ("Hello world.", False)


def test_sentinel_in_one_chunk_is_stripped():
    assert run(["Explain it back. " + SENT]) == ("Explain it back. ", True)


def test_sentinel_split_across_chunks_never_leaks():
    chunks = ["Explain it back. <", "<TEACH", "_BAC", "K>>"]
    f = SentinelFilter()
    emitted = []
    for c in chunks:
        emitted.append(f.feed(c))
    emitted.append(f.flush())
    assert "<" not in "".join(emitted)
    assert "".join(emitted) == "Explain it back. "
    assert f.found


def test_lone_angle_bracket_is_eventually_emitted():
    assert run(["a < b ", "and c"]) == ("a < b and c", False)


def test_sentinel_mid_text():
    assert run(["Question? " + SENT + " trailing"]) == ("Question?  trailing", True)
