def test_signup_success(client):
    resp = client.post(
        "/api/v1/auth/signup",
        json={
            "full_name": "Keerthu Test",
            "email": "keerthu@example.com",
            "password": "Passw0rd!",
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["user"]["email"] == "keerthu@example.com"
    assert "hashed_password" not in body["user"]
    assert body["tokens"]["access_token"]


def test_signup_duplicate_email_rejected(client):
    payload = {"full_name": "Alex", "email": "dup@example.com", "password": "Passw0rd!"}
    first = client.post("/api/v1/auth/signup", json=payload)
    second = client.post("/api/v1/auth/signup", json=payload)
    assert first.status_code == 201
    assert second.status_code == 409


def test_signup_weak_password_rejected(client):
    resp = client.post(
        "/api/v1/auth/signup",
        json={"full_name": "Alex", "email": "weak@example.com", "password": "onlyletters"},
    )
    assert resp.status_code == 422


def test_login_success_and_wrong_password(client):
    client.post(
        "/api/v1/auth/signup",
        json={"full_name": "Beth", "email": "login@example.com", "password": "Passw0rd!"},
    )
    good = client.post(
        "/api/v1/auth/login", json={"email": "login@example.com", "password": "Passw0rd!"}
    )
    bad = client.post(
        "/api/v1/auth/login", json={"email": "login@example.com", "password": "wrongpass1"}
    )
    assert good.status_code == 200
    assert bad.status_code == 401


def test_me_requires_valid_token(client):
    signup = client.post(
        "/api/v1/auth/signup",
        json={"full_name": "Cara", "email": "me@example.com", "password": "Passw0rd!"},
    )
    access_token = signup.json()["tokens"]["access_token"]

    unauthorized = client.get("/api/v1/auth/me")
    authorized = client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {access_token}"}
    )

    assert unauthorized.status_code == 401
    assert authorized.status_code == 200
    assert authorized.json()["email"] == "me@example.com"


def test_refresh_issues_new_token_pair(client):
    signup = client.post(
        "/api/v1/auth/signup",
        json={"full_name": "Dave", "email": "refresh@example.com", "password": "Passw0rd!"},
    )
    refresh_token = signup.json()["tokens"]["refresh_token"]

    resp = client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
    assert resp.status_code == 200
    assert resp.json()["access_token"]
