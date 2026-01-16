"""Tests for API routes."""

import pytest
from fastapi.testclient import TestClient
from src.main import app

client = TestClient(app)


def test_root():
    """Test root endpoint."""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "AllDebrid Client"
    assert data["version"] == "1.0.0"


def test_health():
    """Test health check endpoint."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data


def test_app_version():
    """Test app version endpoint."""
    response = client.get("/api/v2/app/version")
    assert response.status_code == 200
    assert response.text == '"v4.5.0"'


def test_auth_login():
    """Test auth login endpoint."""
    response = client.post("/api/v2/auth/login")
    assert response.status_code == 200
    assert response.text == '"Ok."'
