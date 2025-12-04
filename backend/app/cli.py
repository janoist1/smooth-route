import typer
from typing import Optional
from app.services.google_maps import google_maps_service
from app.core.database import SessionLocal, engine
from app.models.models import Route, StreetViewImage, Base
from app.core.config import settings
from datetime import datetime
from rich.console import Console
from rich.table import Table

app = typer.Typer()
console = Console()

@app.command()
def init_db():
    """
    Initialize the database (create tables).
    """
    console.print("[bold blue]Creating database tables...[/bold blue]")
    Base.metadata.create_all(bind=engine)
    console.print("[bold green]Database tables created successfully![/bold green]")

def get_db_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@app.command()
def generate_route(origin: str, destination: str):
    """
    Generate a route between ORIGIN and DESTINATION and save metadata to DB.
    """
    console.print(f"[bold green]Generating route from '{origin}' to '{destination}'...[/bold green]")
    
    db = SessionLocal()
    try:
        # 1. Get Route
        polyline = google_maps_service.get_route(origin, destination)
        if not polyline:
            console.print("[bold red]Error: Route not found[/bold red]")
            return

        # 2. Decode & Interpolate
        points = google_maps_service.decode_polyline(polyline)
        dense_points = google_maps_service.interpolate_points(points, interval_meters=10.0)
        
        console.print(f"Found route with {len(dense_points)} points after interpolation.")

        # 3. Generate Metadata
        images_metadata = google_maps_service.generate_street_view_metadata(dense_points)
        
        # 4. Save to DB
        db_route = Route(
            origin=origin,
            destination=destination,
            path=f"LINESTRING({', '.join([f'{p[1]} {p[0]}' for p in dense_points])})"
        )
        db.add(db_route)
        db.commit()
        db.refresh(db_route)
        
        db_images = []
        for meta in images_metadata:
            db_img = StreetViewImage(
                route_id=db_route.id,
                latitude=meta['latitude'],
                longitude=meta['longitude'],
                heading=meta['heading'],
                pitch=meta['pitch'],
                image_url=meta['image_url'],
                location=f"POINT({meta['longitude']} {meta['latitude']})"
            )
            db_images.append(db_img)
        
        db.add_all(db_images)
        db.commit()
        
        console.print(f"[bold green]Success! Route ID: {db_route.id}[/bold green]")
        console.print(f"Saved {len(db_images)} image metadata points.")

    except Exception as e:
        console.print(f"[bold red]Error: {str(e)}[/bold red]")
    finally:
        db.close()

@app.command()
def list_routes():
    """
    List all saved routes.
    """
    db = SessionLocal()
    try:
        routes = db.query(Route).all()
        
        table = Table(title="Saved Routes")
        table.add_column("ID", justify="right", style="cyan", no_wrap=True)
        table.add_column("Origin", style="magenta")
        table.add_column("Destination", style="magenta")
        table.add_column("Created At", justify="right", style="green")
        table.add_column("Images", justify="right", style="blue")

        for route in routes:
            image_count = db.query(StreetViewImage).filter(StreetViewImage.route_id == route.id).count()
            table.add_row(
                str(route.id), 
                route.origin, 
                route.destination, 
                route.created_at.strftime("%Y-%m-%d %H:%M"),
                str(image_count)
            )

        console.print(table)
    finally:
        db.close()

if __name__ == "__main__":
    app()
