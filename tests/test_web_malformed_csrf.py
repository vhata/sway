"""Malformed CSRF fields on the local app are expired forms, not server errors."""

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from httpx import Client

from sway.web import create_app


def issue_cookie(client: Client) -> None:
    response = client.get("/")
    assert re.search(r'name="csrf" value="[^"]+"', response.text) is not None


@pytest.fixture
def client(tmp_path: Path) -> Client:
    return TestClient(create_app(tmp_path))


def test_uploaded_csrf_field_is_an_expired_form(client: Client) -> None:
    issue_cookie(client)
    response = client.post(
        "/games", data={"players": "2"}, files={"csrf": ("csrf.txt", b"token", "text/plain")}
    )
    assert response.status_code == 403, response.text
    assert "Please reload your table." in response.text


def test_non_ascii_csrf_field_is_an_expired_form(client: Client) -> None:
    issue_cookie(client)
    response = client.post("/games", data={"csrf": "jeton-été", "players": "2"})
    assert response.status_code == 403, response.text
    assert "Please reload your table." in response.text
