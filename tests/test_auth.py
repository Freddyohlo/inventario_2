import pytest

from app import auth


def test_hash_is_salted_and_verifiable():
    stored = auth.hash_password("secreta")
    assert stored != auth.hash_password("secreta"), "cada hash usa sal propia"
    assert auth.verify_password("secreta", stored)
    assert not auth.verify_password("otra", stored)


def test_verify_rejects_malformed_hash():
    assert not auth.verify_password("x", "no-es-un-hash")
    assert not auth.verify_password("x", "md5$1$aa$bb")


def test_session_roundtrip():
    manager = auth.SessionManager("test-secret")
    token = manager.sign({"id": 7, "role": "admin"})
    assert manager.read(token) == {"uid": 7, "role": "admin"}


def test_session_rejects_tampering():
    manager = auth.SessionManager("test-secret")
    other = auth.SessionManager("another-secret")
    token = manager.sign({"id": 1, "role": "admin"})
    assert other.read(token) is None
    assert manager.read(token + "x") is None
    assert manager.read("garbage") is None


def test_create_user_rejects_bad_role(tmp_path):
    from app.db import connect, init_db
    conn = connect(tmp_path / "a.db")
    init_db(conn)
    with pytest.raises(ValueError):
        auth.create_user(conn, username="x", password="y", role="root")
    conn.close()


def test_authenticate_returns_none_on_unknown_user(tmp_path):
    from app.db import connect, init_db
    conn = connect(tmp_path / "a.db")
    init_db(conn)
    assert auth.authenticate(conn, "nadie", "x") is None
    conn.close()
