from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch
from app.main import app
from app.services.google_maps import GoogleMapsService

client = TestClient(app)

# Mock the GoogleMapsService
mock_google_maps = MagicMock(spec=GoogleMapsService)
mock_google_maps.get_route.return_value = "encoded_polyline"
mock_google_maps.decode_polyline.return_value = [(47.4979, 19.0402), (47.4980, 19.0403)]
mock_google_maps.interpolate_points.return_value = [(47.4979, 19.0402), (47.4980, 19.0403)]
mock_google_maps.generate_street_view_metadata.return_value = [
    {
        "latitude": 47.4979,
        "longitude": 19.0402,
        "heading": 45.0,
        "pitch": 0.0,
        "image_url": "http://mock.url/1"
    },
    {
        "latitude": 47.4980,
        "longitude": 19.0403,
        "heading": 45.0,
        "pitch": 0.0,
        "image_url": "http://mock.url/2"
    }
]

# Mock DB Session
mock_db_session = MagicMock()

@patch("app.api.routes.google_maps_service", mock_google_maps)
@patch("app.api.routes.get_db")
def test_generate_route(mock_get_db):
    # Setup mock DB
    mock_get_db.return_value = mock_db_session
    
    # Mock the count query to return 0 (under quota)
    mock_db_session.query.return_value.filter.return_value.count.return_value = 0
    
    response = client.post("/api/v1/generate-route", json={
        "origin": "Budapest, Keleti",
        "destination": "Budapest, Nyugati"
    })
    
    assert response.status_code == 200
    data = response.json()
    assert "route_id" in data
    assert data["total_points"] == 2
    assert len(data["images"]) == 2
    assert data["images"][0]["image_url"] == "http://mock.url/1"

@patch("app.api.routes.google_maps_service", mock_google_maps)
@patch("app.api.routes.get_db")
def test_quota_exceeded(mock_get_db):
    # Setup mock DB
    mock_get_db.return_value = mock_db_session
    
    # Mock the count query to return limit + 1
    mock_db_session.query.return_value.filter.return_value.count.return_value = 1001
    
    response = client.post("/api/v1/generate-route", json={
        "origin": "Budapest, Keleti",
        "destination": "Budapest, Nyugati"
    })
    
    assert response.status_code == 429
    assert response.json()["detail"] == "Daily image quota exceeded"
