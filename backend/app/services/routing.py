"""Provider switch for route planning; Street View stays with Google."""
from app.core.config import settings


class RoutingService:
    @property
    def provider(self):
        # Lazy imports: OSM planning needs no Google key or client.
        if settings.ROUTING_PROVIDER == "google":
            from app.services.google_maps import google_maps_service
            return google_maps_service
        from app.services.routing_osm import osm_routing_service
        return osm_routing_service

    def get_route(self, origin: str, destination: str) -> list[dict]:
        return self.provider.get_route(origin, destination)

    def get_routes(self, origin: str, destination: str, max_routes: int = 3) -> list[dict]:
        return self.provider.get_routes(origin, destination, max_routes=max_routes)

    def geocode(self, address: str) -> str | None:
        return self.provider.geocode(address)


routing_service = RoutingService()
