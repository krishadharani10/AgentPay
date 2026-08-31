def test_root_endpoint(client):
    """Test the root endpoint returns app welcome info."""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["app"] == "AgentPay"
    assert "docs" in data
    assert "health" in data


def test_health_endpoint(client):
    """Test the /health endpoint returns ok status and connected database."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["app"] == "AgentPay"
    assert data["environment"] == "test"
    assert data["database"] == "connected"
    assert data["version"] == "0.1.0"
