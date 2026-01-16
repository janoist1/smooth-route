
import sys
import os

# Add the backend directory to sys.path so we can import 'app'
sys.path.append(os.path.join(os.getcwd(), 'backend'))

try:
    from app.services.google_maps import google_maps_service
    
    print("Testing get_route with address inputs...")
    origin = "Budapest, Aulich utca 1."
    destination = "Székesfehérvár"
    
    # Test geocoding explicitly first to see if it works
    print(f"Testing geocoding for origin: '{origin}'")
    geo_origin = google_maps_service.geocode(origin)
    print(f"Geocoded Origin: {geo_origin}")
    
    print(f"Testing geocoding for destination: '{destination}'")
    geo_dest = google_maps_service.geocode(destination)
    print(f"Geocoded Destination: {geo_dest}")

    # Test get_route
    print("\nTesting full get_route...")
    route_points = google_maps_service.get_route(origin, destination)
    
    if route_points:
        print(f"SUCCESS: Route found with {len(route_points)} points.")
        print(f"First point: {route_points[0]}")
    else:
        print("FAILURE: No route found.")

except Exception as e:
    print(f"EXCEPTION: {e}")
    import traceback
    traceback.print_exc()
