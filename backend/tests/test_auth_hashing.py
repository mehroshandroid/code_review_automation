from app.auth.hashing import hash_password, verify_password


def test_hash_password_produces_a_different_string_than_the_input():
    hashed = hash_password("correct horse battery staple")
    assert hashed != "correct horse battery staple"


def test_verify_password_returns_true_for_the_correct_password():
    hashed = hash_password("correct horse battery staple")
    assert verify_password("correct horse battery staple", hashed) is True


def test_verify_password_returns_false_for_the_wrong_password():
    hashed = hash_password("correct horse battery staple")
    assert verify_password("wrong password", hashed) is False


def test_hash_password_is_salted_so_the_same_password_hashes_differently(monkeypatch):
    assert hash_password("same password") != hash_password("same password")
