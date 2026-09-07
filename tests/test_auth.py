"""
Auth and task-ownership tests (Phase 4).

Covers:
  - register → login → GET /users/me happy path
  - duplicate email → 400
  - wrong password / unknown email → 401
  - invalid token → 401
  - task endpoints require auth (401 without header)
  - ownership isolation: user A cannot read/update/delete user B's tasks
  - user A's task list excludes user B's tasks
"""


def _register(client, email, password="password123"):
    return client.post(
        "/auth/register", json={"email": email, "password": password}
    )


def _login(client, email, password="password123"):
    return client.post(
        "/auth/login", data={"username": email, "password": password}
    )


def _auth_headers(token):
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Registration & login
# ---------------------------------------------------------------------------

class TestAuthFlow:
    def test_register_returns_user_out(self, anon_client):
        resp = _register(anon_client, "new@example.com")
        assert resp.status_code == 201
        body = resp.json()
        assert body["email"] == "new@example.com"
        assert body["is_active"] is True
        assert "id" in body
        assert "hashed_password" not in body  # never leak the hash

    def test_login_returns_bearer_token(self, anon_client):
        _register(anon_client, "login@example.com")
        resp = _login(anon_client, "login@example.com")
        assert resp.status_code == 200
        body = resp.json()
        assert body["token_type"] == "bearer"
        assert body["access_token"]

    def test_register_then_me(self, anon_client):
        _register(anon_client, "me@example.com")
        token = _login(anon_client, "me@example.com").json()["access_token"]
        resp = anon_client.get("/users/me", headers=_auth_headers(token))
        assert resp.status_code == 200
        assert resp.json()["email"] == "me@example.com"

    def test_duplicate_email_returns_400(self, anon_client):
        _register(anon_client, "dupe@example.com")
        resp = _register(anon_client, "dupe@example.com")
        assert resp.status_code == 400

    def test_wrong_password_returns_401(self, anon_client):
        _register(anon_client, "pw@example.com")
        resp = _login(anon_client, "pw@example.com", password="wrongpass1")
        assert resp.status_code == 401

    def test_unknown_email_returns_401(self, anon_client):
        resp = _login(anon_client, "ghost@example.com")
        assert resp.status_code == 401

    def test_short_password_rejected_422(self, anon_client):
        resp = _register(anon_client, "short@example.com", password="short")
        assert resp.status_code == 422

    def test_invalid_email_rejected_422(self, anon_client):
        resp = anon_client.post(
            "/auth/register", json={"email": "not-an-email", "password": "password123"}
        )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Token validation on protected routes
# ---------------------------------------------------------------------------

class TestTokenValidation:
    def test_me_without_token_returns_401(self, anon_client):
        resp = anon_client.get("/users/me")
        assert resp.status_code == 401

    def test_me_with_invalid_token_returns_401(self, anon_client):
        resp = anon_client.get(
            "/users/me", headers=_auth_headers("not.a.real.token")
        )
        assert resp.status_code == 401

    def test_expired_token_returns_401(self, anon_client):
        # Register a real user, then forge an already-expired token for them
        from app.security import create_access_token

        reg = _register(anon_client, "expired@example.com")
        user_id = reg.json()["id"]
        expired = create_access_token(subject=user_id, expires_minutes=-1)

        resp = anon_client.get("/users/me", headers=_auth_headers(expired))
        assert resp.status_code == 401

    def test_tasks_list_without_token_returns_401(self, anon_client):
        resp = anon_client.get("/tasks")
        assert resp.status_code == 401

    def test_create_task_without_token_returns_401(self, anon_client):
        resp = anon_client.post("/tasks", json={"title": "No auth"})
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Ownership isolation
# ---------------------------------------------------------------------------

class TestTaskOwnership:
    def _make_task_for(self, client, token, title="Owned task"):
        resp = client.post(
            "/tasks", json={"title": title}, headers=_auth_headers(token)
        )
        assert resp.status_code == 201
        return resp.json()

    def test_user_b_cannot_read_user_a_task(self, anon_client):
        _register(anon_client, "a@example.com")
        token_a = _login(anon_client, "a@example.com").json()["access_token"]
        _register(anon_client, "b@example.com")
        token_b = _login(anon_client, "b@example.com").json()["access_token"]

        task = self._make_task_for(anon_client, token_a)

        resp = anon_client.get(
            f"/tasks/{task['id']}", headers=_auth_headers(token_b)
        )
        assert resp.status_code == 403

    def test_user_b_cannot_update_user_a_task(self, anon_client):
        _register(anon_client, "a@example.com")
        token_a = _login(anon_client, "a@example.com").json()["access_token"]
        _register(anon_client, "b@example.com")
        token_b = _login(anon_client, "b@example.com").json()["access_token"]

        task = self._make_task_for(anon_client, token_a)

        resp = anon_client.put(
            f"/tasks/{task['id']}",
            json={"title": "hijack", "version": 1},
            headers=_auth_headers(token_b),
        )
        assert resp.status_code == 403

    def test_user_b_cannot_delete_user_a_task(self, anon_client):
        _register(anon_client, "a@example.com")
        token_a = _login(anon_client, "a@example.com").json()["access_token"]
        _register(anon_client, "b@example.com")
        token_b = _login(anon_client, "b@example.com").json()["access_token"]

        task = self._make_task_for(anon_client, token_a)

        resp = anon_client.delete(
            f"/tasks/{task['id']}", headers=_auth_headers(token_b)
        )
        assert resp.status_code == 403

    def test_list_only_returns_own_tasks(self, anon_client):
        _register(anon_client, "a@example.com")
        token_a = _login(anon_client, "a@example.com").json()["access_token"]
        _register(anon_client, "b@example.com")
        token_b = _login(anon_client, "b@example.com").json()["access_token"]

        self._make_task_for(anon_client, token_a, title="A-task-1")
        self._make_task_for(anon_client, token_a, title="A-task-2")
        self._make_task_for(anon_client, token_b, title="B-task-1")

        resp_a = anon_client.get("/tasks", headers=_auth_headers(token_a))
        titles_a = [t["title"] for t in resp_a.json()["items"]]
        assert resp_a.json()["total"] == 2
        assert "B-task-1" not in titles_a

        resp_b = anon_client.get("/tasks", headers=_auth_headers(token_b))
        titles_b = [t["title"] for t in resp_b.json()["items"]]
        assert resp_b.json()["total"] == 1
        assert titles_b == ["B-task-1"]

    def test_nonexistent_task_returns_404_not_403(self, anon_client):
        _register(anon_client, "a@example.com")
        token_a = _login(anon_client, "a@example.com").json()["access_token"]
        resp = anon_client.get("/tasks/99999", headers=_auth_headers(token_a))
        assert resp.status_code == 404
