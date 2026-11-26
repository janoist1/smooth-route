import typer
import os
from typing import Optional
from app.core.database import SessionLocal, engine
from app.models.models import StreetViewImage, Base
from app.core.config import settings
from app.services.segment_aggregation import frame_usable
from rich.console import Console
from rich.table import Table
from sqlalchemy import or_

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
    console.print("[dim]Note: Route is only a tool - points are stored point-based, not route-based.[/dim]")
    
    try:
        result = processing_service.collect_points(origin, destination)
        
        console.print("[bold green]Success! Points collected.[/bold green]")
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
            .filter(
                or_(
                    StreetViewImage.image_url.like("images/%"),
                    StreetViewImage.image_url.like("%data/images%")
                )
            )
            .count()
        )
        points_with_rqi = sum(
            frame_usable(metadata)
            for (metadata,) in db.query(StreetViewImage.analysis_metadata)
            .filter(StreetViewImage.dino_rqi_score.isnot(None))
            .yield_per(1000)
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
                score = p.dino_rqi_score if frame_usable(p.analysis_metadata) else None
                rqi_str = f"RQI: {score}" if score is not None else "No RQI"
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
        console.print("[bold blue]Checking for pending downloads...[/bold blue]")
        
        result = processing_service.download_images(output_dir, limit)
        
        if result['downloaded'] == 0 and result['skipped'] == 0 and result['errors'] == 0:
            console.print("[bold yellow]No points found that need downloading[/bold yellow]")
        else:
            console.print(f"[bold green]Downloaded {result['downloaded']} new images. Skipped {result['skipped']} (already exist). Errors: {result['errors']}[/bold green]")
            
            # Determine output dir for display
            if output_dir is None:
                data_dir = settings.resolve_data_dir()
                output_dir = os.path.join(data_dir, "images")
            console.print(f"[bold]Images saved to: {output_dir}[/bold]")
        
    except Exception as e:
        console.print(f"[bold red]Error: {str(e)}[/bold red]")


@app.command()
def fetch_missing_images(
    limit: int = typer.Option(0, help="Max number of images to download (0 = all missing)"),
    output_dir: Optional[str] = typer.Option(None, help="Directory to save images")
):
    """
    Find points with missing image files on disk and re-download them from Google.
    
    This command checks every point in the database, verifies if the file exists on disk,
    and if missing, regenerates the Google Street View URL and downloads the image.
    """
    from app.services.processing_service import processing_service
    
    try:
        console.print("[bold blue]Checking for missing images on disk...[/bold blue]")
        
        result = processing_service.download_missing_images(output_dir, limit)
        
        console.print("[bold green]Sync complete![/bold green]")
        console.print(f"Downloaded: {result['downloaded']} | Healthy (Skipped): {result['skipped']} | Errors: {result['errors']}")
        
    except Exception as e:
        console.print(f"[bold red]Error: {str(e)}[/bold red]")
        import traceback
        traceback.print_exc()


@app.command()
def analyze_image(image_path: str):
    """
    Analyze a single image for damage (YOLO).

    IMAGE_PATH: Path to the image file.
    """
    from app.services.road_quality import road_quality_service
    import os
    import json # Added for printing metadata

    if not os.path.exists(image_path):
        console.print(f"[bold red]File not found: {image_path}[/bold red]")
        return

    console.print(f"[bold blue]Analyzing: {image_path}[/bold blue]")

    result = road_quality_service.analyze_image(image_path)

    # YOLO supplies damage information; its legacy score is not product RQI.
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
    --reanalyze: Re-analyze points that already have RQI scores.
    """
    from app.services.processing_service import processing_service
    
    try:
        console.print("[bold blue]Starting analysis (Strategy: YOLO)...[/bold blue]")
        if lat and lng:
            console.print(f"[dim]Analyzing points within {radius}m of ({lat}, {lng})[/dim]")
        
        result = processing_service.analyze_points(
            lat=lat, 
            lng=lng, 
            radius=radius, 
            limit=limit, 
            strategy="YOLO", 
            reanalyze=reanalyze
        )
        
        console.print("[bold green]Analysis complete.[/bold green]")
        console.print(f"Analyzed: {result['analyzed']} | Errors: {result['errors']} | Total candidates: {result['total']}")
        
    except Exception as e:
        console.print(f"[bold red]Error: {str(e)}[/bold red]")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    app()
