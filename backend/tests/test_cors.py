from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


def test_allows_requests_from_the_frontend_origin():
    response = client.get("/api/health", headers={"Origin": "http://localhost:3000"})
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"


def test_preflight_allows_post_to_reviews_endpoint():
    response = client.options(
        "/api/reviews",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"
