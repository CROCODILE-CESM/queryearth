import queryearth


def test_version_is_a_string():
    assert isinstance(queryearth.__version__, str)
    assert queryearth.__version__
