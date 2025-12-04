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

@app.command()
def download_images(route_id: int, output_dir: str = "data/images", limit: int = 0):
    """
    Download Street View images for a route.
    
    ROUTE_ID: The route ID to download images for.
    --output-dir: Directory to save images (default: data/images)
    --limit: Max number of images to download (0 = all)
    """
    import requests
    import os
    from rich.progress import track
    
    db = SessionLocal()
    try:
        # Get images for route
        query = db.query(StreetViewImage).filter(StreetViewImage.route_id == route_id)
        if limit > 0:
            query = query.limit(limit)
        images = query.all()
        
        if not images:
            console.print(f"[bold red]No images found for route {route_id}[/bold red]")
            return
        
        # Create output directory
        route_dir = os.path.join(output_dir, f"route_{route_id}")
        os.makedirs(route_dir, exist_ok=True)
        
        console.print(f"[bold blue]Downloading {len(images)} images to {route_dir}...[/bold blue]")
        
        downloaded = 0
        errors = 0
        
        for img in track(images, description="Downloading..."):
            try:
                response = requests.get(img.image_url, timeout=30)
                if response.status_code == 200:
                    # Check if it's actually an image (not an error response)
                    content_type = response.headers.get('content-type', '')
                    if 'image' in content_type:
                        filename = f"{img.id:05d}_{img.latitude:.6f}_{img.longitude:.6f}.jpg"
                        filepath = os.path.join(route_dir, filename)
                        
                        with open(filepath, 'wb') as f:
                            f.write(response.content)
                        
                        # Update image_path in DB
                        img.image_url = filepath
                        downloaded += 1
                    else:
                        console.print(f"[yellow]Warning: No Street View at ({img.latitude}, {img.longitude})[/yellow]")
                        errors += 1
                else:
                    errors += 1
            except Exception as e:
                console.print(f"[red]Error downloading image {img.id}: {e}[/red]")
                errors += 1
        
        db.commit()
        console.print(f"[bold green]Downloaded {downloaded} images. Errors: {errors}[/bold green]")
        console.print(f"[bold]Images saved to: {route_dir}[/bold]")
        
    except Exception as e:
        console.print(f"[bold red]Error: {str(e)}[/bold red]")
    finally:
        db.close()

@app.command()
def delete_route(route_id: int, force: bool = False):
    """
    Delete a route and its associated images (DB + files).
    
    ROUTE_ID: The route ID to delete.
    --force: Skip confirmation prompt.
    """
    import os
    import shutil
    
    db = SessionLocal()
    try:
        route = db.query(Route).filter(Route.id == route_id).first()
        if not route:
            console.print(f"[bold red]Route {route_id} not found[/bold red]")
            return
        
        image_count = db.query(StreetViewImage).filter(StreetViewImage.route_id == route_id).count()
        
        if not force:
            console.print(f"[bold yellow]Route {route_id}: {route.origin} → {route.destination}[/bold yellow]")
            console.print(f"This will delete {image_count} image records and local files.")
            confirm = typer.confirm("Are you sure?")
            if not confirm:
                console.print("[dim]Cancelled.[/dim]")
                return
        
        # Delete local image files
        route_dir = f"data/images/route_{route_id}"
        if os.path.exists(route_dir):
            shutil.rmtree(route_dir)
            console.print(f"[dim]Deleted directory: {route_dir}[/dim]")
        
        # Delete from DB (cascade)
        db.query(StreetViewImage).filter(StreetViewImage.route_id == route_id).delete()
        db.query(Route).filter(Route.id == route_id).delete()
        db.commit()
        
        console.print(f"[bold green]Deleted route {route_id} and {image_count} images.[/bold green]")
        
    except Exception as e:
        console.print(f"[bold red]Error: {str(e)}[/bold red]")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    app()
