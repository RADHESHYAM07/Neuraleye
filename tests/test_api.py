from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_health_endpoint():
    # PROMPT: "Generate health check test"
    # CHANGES MADE: Added to verify app mounts correctly.
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] in ["ok", "degraded"]

def test_metrics_endpoint():
    # PROMPT: "Test metrics endpoint on empty DB"
    response = client.get("/stores/STORE_BLR_002/metrics")
    assert response.status_code == 200
    data = response.json()
    assert "unique_visitors" in data
    assert data["unique_visitors"] >= 0

def test_funnel_endpoint():
    response = client.get("/stores/STORE_BLR_002/funnel")
    assert response.status_code == 200
    data = response.json()
    assert "stages" in data

def test_anomalies_endpoint():
    response = client.get("/stores/STORE_BLR_002/anomalies")
    assert response.status_code == 200
    data = response.json()
    assert "active_anomalies" in data
