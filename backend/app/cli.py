import typer
import os
from typing import Optional
from app.services.google_maps import google_maps_service
from app.core.database import SessionLocal, engine
from app.models.models import StreetViewImage, Base
from app.core.config import settings
from datetime import datetime
from rich.console import Console
from rich.table import Table
from geoalchemy2 import Geometry

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
def collect_points(origin: str, destination: str):
    """
    Collect road points along a route from ORIGIN to DESTINATION.
    
    Route is only used as a tool to collect points efficiently.
    Points are stored point-based (location + heading), NOT route-based.
    When planning routes later, we query existing points.
    
    Uses spatial deduplication to reuse existing points.
    """
    from app.services.processing_service import processing_service
    
    console.print(f"[bold green]Collecting points from '{origin}' to '{destination}'...[/bold green]")
    console.print(f"[dim]Note: Route is only a tool - points are stored point-based, not route-based.[/dim]")
    
    try:
        result = processing_service.collect_points(origin, destination)
        
        console.print(f"[bold green]Success! Points collected.[/bold green]")
        console.print(f"Total points along route: {result['total']}")
        console.print(f"New points created: {result['new']} | Reused existing: {result['reused']}")

    except Exception as e:
        console.print(f"[bold red]Error: {str(e)}[/bold red]")


@app.command()
def list_points():
    """
    List all collected road points.
    """
    db = SessionLocal()
    try:
        total_points = db.query(StreetViewImage).count()
        points_with_images = (
            db.query(StreetViewImage)
            .filter(StreetViewImage.image_url.like("%data/images%"))
            .count()
        )
        points_with_rqi = (
            db.query(StreetViewImage)
            .filter(StreetViewImage.rqi_score.isnot(None))
            .count()
        )

        table = Table(title="Road Points Summary")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="magenta", justify="right")

        table.add_row("Total Points", str(total_points))
        table.add_row("Points with Images", str(points_with_images))
        table.add_row("Points with RQI", str(points_with_rqi))

        console.print(table)

        # Show recent points
        recent = (
            db.query(StreetViewImage)
            .order_by(StreetViewImage.created_at.desc())
            .limit(10)
            .all()
        )
        if recent:
            console.print("\n[bold]Recent Points:[/bold]")
            for p in recent:
                rqi_str = f"RQI: {p.rqi_score}" if p.rqi_score else "No RQI"
                console.print(
                    f"  [{p.id}] ({p.latitude:.6f}, {p.longitude:.6f}) heading={int(p.heading)}° - {rqi_str}"
                )
    finally:
        db.close()


@app.command()
def download_images(
    output_dir: Optional[str] = None,
    limit: int = 0
):
    """
    Download Street View images for points that don't have images yet.
    
    Point-based: Downloads images for points that have URLs but no local files.
    Images are saved with unique identifiers (coordinate + heading).
    
    --output-dir: Directory to save images (default: {DATA_DIR}/images)
    --limit: Max number of images to download (0 = all pending)
    """
    from app.services.processing_service import processing_service
    
    try:
        console.print(f"[bold blue]Checking for pending downloads...[/bold blue]")
        
        result = processing_service.download_images(output_dir, limit)
        
        if result['downloaded'] == 0 and result['skipped'] == 0 and result['errors'] == 0:
            console.print(f"[bold yellow]No points found that need downloading[/bold yellow]")
        else:
            console.print(f"[bold green]Downloaded {result['downloaded']} new images. Skipped {result['skipped']} (already exist). Errors: {result['errors']}[/bold green]")
            
            # Determine output dir for display
            if output_dir is None:
                data_dir = settings.DATA_DIR
                output_dir = os.path.join(data_dir, "images")
            console.print(f"[bold]Images saved to: {output_dir}[/bold]")
        
    except Exception as e:
        console.print(f"[bold red]Error: {str(e)}[/bold red]")


@app.command()
def analyze_image(image_path: str, simple: bool = False):
    """
    Analyze a single image for road quality.

    IMAGE_PATH: Path to the image file.
    --simple: Use simple heuristic analysis (no YOLO).
    """
    from app.services.road_quality import road_quality_service
    import os
    import json # Added for printing metadata

    if not os.path.exists(image_path):
        console.print(f"[bold red]File not found: {image_path}[/bold red]")
        return

    console.print(f"[bold blue]Analyzing: {image_path}[/bold blue]")

    if simple:
        result = road_quality_service.analyze_image_simple(image_path)
    else:
        result = road_quality_service.analyze_image(image_path)

    # Display results
    rqi_color = {1: "green", 2: "green", 3: "yellow", 4: "red", 5: "bold red"}
    color = rqi_color.get(int(result.rqi_score), "white")

    console.print(f"\n[{color}]RQI Score: {result.rqi_score}/5[/{color}]")
    console.print(f"Damage count: {result.damage_count}")

    if result.damage_types:
        console.print("Damage types:")
        for dtype, count in result.damage_types.items():
            console.print(f"  - {dtype}: {count}")
            
    if result.analysis_metadata:
        console.print("\n[dim]Detailed Metadata:[/dim]")
        console.print(json.dumps(result.analysis_metadata, indent=2))


@app.command()
def analyze_points(
    lat: Optional[float] = None,
    lng: Optional[float] = None,
    radius: float = 1000.0,
    limit: int = 0,
    simple: bool = False,
    save: bool = True,
    reanalyze: bool = False
):
    """
    Analyze road points for quality (RQI).
    
    Point-based: Analyzes points, not routes.
    
    Options:
    - Analyze all points: --lat and --lng not specified
    - Analyze points in area: specify --lat, --lng, --radius (meters)
    
    --lat, --lng: Center point for area analysis (optional)
    --radius: Radius in meters for area analysis (default: 1000m)
    --limit: Max number of points to analyze (0 = all)
    --simple: Use simple heuristic analysis (no YOLO)
    --save/--no-save: Save RQI scores to database
    --reanalyze: Re-analyze points that already have RQI but missing analysis_metadata
    """
    from app.services.processing_service import processing_service
    
    try:
        console.print(f"[bold blue]Starting analysis...[/bold blue]")
        if lat and lng:
            console.print(f"[dim]Analyzing points within {radius}m of ({lat}, {lng})[/dim]")
        
        # Note: processing_service.analyze_points currently saves automatically.
        # The 'save' and 'reanalyze' flags might need to be added to the service if needed.
        # For now, we assume standard behavior.
        
        result = processing_service.analyze_points(lat, lng, radius, limit, simple, reanalyze=reanalyze)
        
        console.print(f"[bold green]Analysis complete.[/bold green]")
        console.print(f"Analyzed: {result['analyzed']} | Errors: {result['errors']} | Total candidates: {result['total']}")
        
    except Exception as e:
        console.print(f"[bold red]Error: {str(e)}[/bold red]")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    app()
