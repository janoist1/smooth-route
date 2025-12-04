import googlemaps
from typing import List, Dict, Tuple
from app.core.config import settings
import math

class GoogleMapsService:
    def __init__(self):
        if settings.GOOGLE_MAPS_API_KEY:
            self.client = googlemaps.Client(key=settings.GOOGLE_MAPS_API_KEY)
        else:
            self.client = None

    def get_route(self, origin: str, destination: str) -> List[Dict]:
        """
        Get route between origin and destination using Google Directions API.
        Returns a list of steps/points.
        """
        if not self.client:
            raise ValueError("Google Maps API Key not configured")

        directions_result = self.client.directions(
            origin,
            destination,
            mode="driving",
            alternatives=False
        )

        if not directions_result:
            return []

        # Extract the polyline from the first route's first leg
        # In a real app, we might want to handle multiple legs/routes
        route = directions_result[0]
        leg = route['legs'][0]
        
        # We can use the 'overview_polyline' for the whole route, 
        # or iterate through steps for more detail. 
        # Overview polyline is usually sufficient for geometry.
        return route['overview_polyline']['points']

    def decode_polyline(self, polyline_str: str) -> List[Tuple[float, float]]:
        """
        Decodes a polyline string into a list of (lat, lng) tuples.
        """
        decoded = googlemaps.convert.decode_polyline(polyline_str)
        # Convert from list of dicts to list of tuples
        return [(point['lat'], point['lng']) for point in decoded]

    def interpolate_points(self, points: List[Tuple[float, float]], interval_meters: float = 10.0) -> List[Tuple[float, float]]:
        """
        Interpolates points along the path to ensure they are spaced approximately 'interval_meters' apart.
        """
        if not points:
            return []

        interpolated_points = [points[0]]
        
        for i in range(len(points) - 1):
            start = points[i]
            end = points[i+1]
            
            dist = self._haversine_distance(start, end)
            
            if dist > interval_meters:
                num_points = int(dist // interval_meters)
                for j in range(1, num_points + 1):
                    fraction = j / (num_points + 1)
                    lat = start[0] + (end[0] - start[0]) * fraction
                    lng = start[1] + (end[1] - start[1]) * fraction
                    interpolated_points.append((lat, lng))
            
            interpolated_points.append(end)
            
        return interpolated_points

    def _haversine_distance(self, p1: Tuple[float, float], p2: Tuple[float, float]) -> float:
        """
        Calculate the great circle distance between two points on the earth (specified in decimal degrees)
        """
        lat1, lon1 = p1
        lat2, lon2 = p2
        
        R = 6371000  # Radius of earth in meters
        
        phi1 = math.radians(lat1)
        phi2 = math.radians(lat2)
        dphi = math.radians(lat2 - lat1)
        dlambda = math.radians(lon2 - lon1)
        
        a = math.sin(dphi/2)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda/2)**2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        
        return R * c

    def get_street_view_url(self, lat: float, lng: float, heading: float = 0, pitch: float = 0) -> str:
        """
        Generates a signed URL for Street View Static API.
        Note: Actual signing logic would be needed if 'signature' is required.
        For now, we just return the URL structure.
        """
        base_url = "https://maps.googleapis.com/maps/api/streetview"
        return f"{base_url}?size=600x400&location={lat},{lng}&heading={heading}&pitch={pitch}&key={settings.GOOGLE_MAPS_API_KEY}"

    def calculate_heading(self, p1: Tuple[float, float], p2: Tuple[float, float]) -> float:
        """
        Calculates the bearing between two points.
        """
        lat1, lon1 = math.radians(p1[0]), math.radians(p1[1])
        lat2, lon2 = math.radians(p2[0]), math.radians(p2[1])
        
        dlon = lon2 - lon1
        
        y = math.sin(dlon) * math.cos(lat2)
        x = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(dlon)
        
        initial_bearing = math.atan2(y, x)
        
        # Now we have the initial bearing but math.atan2 return values
        # from -180 to +180 which is not what we want for a compass bearing
        # The solution is to normalize the initial bearing as shown below
        initial_bearing = math.degrees(initial_bearing)
        compass_bearing = (initial_bearing + 360) % 360
        
        return compass_bearing

    def generate_street_view_metadata(self, points: List[Tuple[float, float]]) -> List[Dict]:
        """
        Generates metadata for Street View images along the route.
        Calculates heading based on the path.
        """
        metadata = []
        for i in range(len(points)):
            current_point = points[i]
            
            # Calculate heading
            if i < len(points) - 1:
                next_point = points[i+1]
                heading = self.calculate_heading(current_point, next_point)
            elif i > 0:
                # For the last point, use the heading from the previous point
                prev_point = points[i-1]
                heading = self.calculate_heading(prev_point, current_point)
            else:
                heading = 0.0

            url = self.get_street_view_url(current_point[0], current_point[1], heading=heading)
            
            metadata.append({
                "latitude": current_point[0],
                "longitude": current_point[1],
                "heading": heading,
                "pitch": 0.0,
                "image_url": url
            })
            
        return metadata
google_maps_service = GoogleMapsService()
