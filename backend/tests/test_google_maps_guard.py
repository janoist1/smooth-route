"""Route billing guards, using only mocked Google clients and HTTP sessions."""
from unittest.mock import Mock

import googlemaps
import pytest
from graphql import GraphQLError

from app.core.config import settings
from app.graphql.limits import InputLimitError, should_mask_error
from app.services.google_maps import GoogleMapsService
from app.services.directions_quota import default_quota

ROUTE = {"overview_polyline": {"points": "_p~iF~ps|U_ulLnnqC"}, "legs": [], "summary": "A"}
GEOCODE = [{"geometry": {"location": {"lat": 47.5, "lng": 19.04}}}]


@pytest.fixture
def service(monkeypatch):
    monkeypatch.setattr(settings, "PUBLIC_READ_ONLY", False)
    svc = GoogleMapsService.__new__(GoogleMapsService)
    svc.client = Mock()
    svc.client.directions.return_value = []
    svc.client.geocode.return_value = GEOCODE
    return svc


@pytest.mark.parametrize("method", ["get_route", "get_routes"])
@pytest.mark.parametrize("origin,destination", [
    ("47.5,19.04", "47.6,19.1"), ("47.5,19.04", "Győr"), ("Budapest", "47.5,19.04"),
    (" 47.5 , 19.04 ", "Győr"),
])
def test_coordinate_inputs_make_exactly_one_directions_call(service, method, origin, destination):
    assert getattr(service, method)(origin, destination) == []
    service.client.directions.assert_called_once()
    service.client.geocode.assert_not_called()
    assert default_quota().used() == 1


@pytest.mark.parametrize("method", ["get_route", "get_routes"])
@pytest.mark.parametrize("fails", [False, True])
def test_public_mode_never_geocodes_or_retries(service, monkeypatch, method, fails):
    monkeypatch.setattr(settings, "PUBLIC_READ_ONLY", True)
    if fails:
        service.client.directions.side_effect = ConnectionError("mock failure")
    assert getattr(service, method)("Budapest", "Győr") == []
    service.client.directions.assert_called_once()
    service.client.geocode.assert_not_called()
    assert default_quota().used() == 1


@pytest.mark.parametrize("method", ["get_route", "get_routes"])
def test_local_address_retry_counts_all_four_calls(service, method):
    service.client.directions.side_effect = [[], [ROUTE]]
    assert getattr(service, method)("Budapest", "Győr")
    assert service.client.directions.call_count == 2
    assert service.client.geocode.call_count == 2
    assert default_quota().used() == 4


@pytest.mark.parametrize("method", ["get_route", "get_routes"])
@pytest.mark.parametrize("cap,directions,geocodes", [(0, 0, 0), (1, 1, 0), (2, 1, 1), (3, 1, 2)])
def test_cap_blocks_each_billable_call_before_sending(service, monkeypatch, method, cap, directions, geocodes):
    monkeypatch.setattr(settings, "GOOGLE_DIRECTIONS_DAILY_CAP", cap)
    with pytest.raises(GraphQLError, match="daily cap reached") as caught:
        getattr(service, method)("Budapest", "Győr")
    assert caught.value.extensions == {"code": "RESOURCE_EXHAUSTED"}
    assert not should_mask_error(GraphQLError("wrapper", original_error=caught.value))
    assert service.client.directions.call_count == directions
    assert service.client.geocode.call_count == geocodes
    assert default_quota().used() == cap


def test_standalone_geocoding_shares_directions_budget(service, monkeypatch):
    monkeypatch.setattr(settings, "GOOGLE_DIRECTIONS_DAILY_CAP", 2)
    assert service.geocode("Budapest") == "47.5,19.04"
    assert service.get_routes("47.5,19.04", "Győr") == []
    with pytest.raises(GraphQLError, match="daily cap reached"):
        service.geocode("Győr")
    assert service.client.geocode.call_count == service.client.directions.call_count == 1


@pytest.mark.parametrize("method", ["get_route", "get_routes"])
@pytest.mark.parametrize("value", ["40.7 -74.0", "+34.05,-118.24", "N40.7 W74.0", "40.7,-74.0"])
def test_service_rejects_bad_coordinates_without_google_calls(service, method, value):
    with pytest.raises(InputLimitError):
        getattr(service, method)(value, "Győr")
    service.client.directions.assert_not_called()
    service.client.geocode.assert_not_called()
    assert default_quota().used() == 0


@pytest.mark.parametrize("method", ["get_route", "get_routes"])
def test_broken_counter_blocks_google_call(service, method):
    default_quota().path.write_text("{broken")
    with pytest.raises(GraphQLError, match="counter is unavailable"):
        getattr(service, method)("Budapest", "Győr")
    service.client.directions.assert_not_called()
    service.client.geocode.assert_not_called()


@pytest.mark.parametrize("method", ["get_route", "get_routes", "geocode"])
@pytest.mark.parametrize("status,body", [
    (503, {}), (200, {"status": "UNKNOWN_ERROR"}), (200, {"status": "OVER_QUERY_LIMIT"}),
])
def test_sdk_does_not_send_hidden_retries(monkeypatch, method, status, body):
    monkeypatch.setattr(settings, "PUBLIC_READ_ONLY", True)
    monkeypatch.setattr(settings, "GOOGLE_MAPS_API_KEY", "AIza" + "x" * 35)
    response = Mock(status_code=status)
    response.json.return_value = body
    session = Mock()
    session.get.return_value = response
    # Exercise the real SDK's retry path, while every HTTP operation is mocked.
    monkeypatch.setattr(googlemaps.client.requests, "Session", lambda: session)
    service = GoogleMapsService()
    if method == "geocode":
        assert service.geocode("Budapest") is None
    else:
        assert getattr(service, method)("Budapest", "Győr") == []
    session.get.assert_called_once()
    assert default_quota().used() == 1
