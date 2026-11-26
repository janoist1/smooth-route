import googlemaps
from typing import Dict, List, Optional, Tuple
from app.core.config import settings
from app.services.capture_date import parse_capture_date
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

        try:
            directions_result = self.client.directions(
                origin,
                destination,
                mode="driving",
                alternatives=False
            )
        except Exception as e:
            print(f"DEBUG: Error in initial directions call: {e}")
            directions_result = None

        if not directions_result:
            # Try to geocode inputs and retry if they weren't coordinates
            print(f"DEBUG: No route found for raw inputs. Attempting geocoding for {origin} -> {destination}")
            
            # Simple check if they look like coords (can use implicit knowledge or simple logic)
            geo_origin = self.geocode(origin)
            geo_dest = self.geocode(destination)
            
            if geo_origin and geo_dest:
                 print(f"DEBUG: Retrying route with geocoded coords: {geo_origin} -> {geo_dest}")
                 try:
                     directions_result = self.client.directions(
                        geo_origin,
                        geo_dest,
                        mode="driving",
                        alternatives=False
                    )
                 except Exception as e:
                     print(f"DEBUG: Error in retry directions call: {e}")
                     import traceback
                     traceback.print_exc()
                     directions_result = None

        if not directions_result:
            print("DEBUG: Still no route found after geocoding.", flush=True)
            return []

        # Extract the polyline from the first route's first leg
        try:
             route = directions_result[0]
             encoded_polyline = route['overview_polyline']['points']
             decoded_points = googlemaps.convert.decode_polyline(encoded_polyline)
             return decoded_points
        except Exception as e:
             print(f"DEBUG: Error parsing route result: {e}")
             return []

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

    def get_street_view_url(self, lat: float, lng: float, heading: float = 0, pitch: Optional[float] = None) -> str:
        """
        Street View Static request URL for a point — WITHOUT the API key.

        The URL is stored in `street_view_images.image_url` until the image is
        downloaded, and `image_url` is readable through the public API, so the
        key must never be part of it. `sv_client.image_from_url` adds the
        configured key when the image is actually requested.
        """
        if pitch is None:
            from app.core.settings_manager import settings_manager
            pitch = settings_manager.get_setting("google_maps_pitch", -20.0)

        base_url = "https://maps.googleapis.com/maps/api/streetview"
        return f"{base_url}?size=600x400&location={lat},{lng}&heading={heading}&pitch={pitch}"

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

    def get_panorama_metadata(
        self,
        lat: Optional[float] = None,
        lng: Optional[float] = None,
        radius: int = 50,
        pano_id: Optional[str] = None,
    ) -> Optional[Dict]:
        """Free Street View Metadata API lookup (no billable image request).

        Looks up by `pano_id` when given (exact panorama), else by location
        (the panorama live today nearest to lat/lng within `radius` m).
        Returns {pano_id, lat, lng, date} or None when there is no panorama.
        `date` is the raw month-precision capture date, e.g. "2019-06".

        Goes through the shared gentle client (`sv_client`): paced at the
        configured steady rate, and a quota / billing / key signal raises
        `StreetViewFatal` so the calling job stops instead of hammering on.
        """
        from app.services.sv_client import StreetViewError, default_client

        if not settings.GOOGLE_MAPS_API_KEY:
            return None
        try:
            return default_client().metadata(lat, lng, pano_id=pano_id, radius=radius)
        except StreetViewError as e:  # this lookup failed; the job goes on
            print(f"SV Metadata error: {e}")
            return None

    def generate_street_view_metadata(self, points: List[Tuple[float, float]]) -> List[Dict]:
        """
        Generates metadata for Street View images along the route.
        Validates availability with Street View API and snaps to exact location.
        """
        metadata = []
        seen_panos = set()
        
        print(f"DEBUG: Validating {len(points)} points with Street View API...", flush=True)

        for i in range(len(points)):
            current_interpolated_point = points[i]
            
            # calculate heading from route path (more stable to use original path direction)
            if i < len(points) - 1:
                next_point = points[i+1]
                heading = self.calculate_heading(current_interpolated_point, next_point)
            elif i > 0:
                prev_point = points[i-1]
                heading = self.calculate_heading(prev_point, current_interpolated_point)
            else:
                heading = 0.0

            # Check Street View
            sv_meta = self.get_panorama_metadata(current_interpolated_point[0], current_interpolated_point[1])
            
            if sv_meta:
                pano_id = sv_meta['pano_id']
                if pano_id in seen_panos:
                     continue # Skip duplicate panoramas (snapped to same spot)
                
                seen_panos.add(pano_id)
                
                # Use EXACT coordinates from Street View
                final_lat = sv_meta['lat']
                final_lng = sv_meta['lng']
                
                # Re-generate URL with exact coords
                url = self.get_street_view_url(final_lat, final_lng, heading=heading, pitch=-20.0)
                
                metadata.append({
                    "latitude": final_lat,
                    "longitude": final_lng,
                    "heading": heading,
                    "pitch": -20.0,
                    "image_url": url,
                    "pano_id": pano_id,
                    # Capture month of this exact panorama (free metadata field).
                    "capture_date": parse_capture_date(sv_meta.get("date")),
                })
            
        return metadata

    def geocode(self, address: str) -> Optional[str]:
        """
        Geocodes an address string to 'lat,lng' format.
        Returns None if geocoding fails.
        """
        if not self.client:
            return None
        
        try:
            result = self.client.geocode(address)
            if result:
                location = result[0]['geometry']['location']
                return f"{location['lat']},{location['lng']}"
            return None
        except Exception as e:
            print(f"Geocoding error: {e}")
            return None

google_maps_service = GoogleMapsService()
