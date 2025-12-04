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
    from sqlalchemy import func
    
    console.print(f"[bold green]Collecting points from '{origin}' to '{destination}'...[/bold green]")
    console.print(f"[dim]Note: Route is only a tool - points are stored point-based, not route-based.[/dim]")
    
    db = SessionLocal()
    try:
        # 1. Get Route (as tool to collect points)
        polyline = google_maps_service.get_route(origin, destination)
        if not polyline:
            console.print("[bold red]Error: Route not found[/bold red]")
            return

        # 2. Decode & Interpolate
        points = google_maps_service.decode_polyline(polyline)
        dense_points = google_maps_service.interpolate_points(points, interval_meters=10.0)
        
        console.print(f"Found {len(dense_points)} points along the route after interpolation.")

        # 3. Generate Metadata
        images_metadata = google_maps_service.generate_street_view_metadata(dense_points)
        
        # 4. Process Points with Deduplication (Point-based, NO route storage)
        reused_count = 0
        new_count = 0
        
        for meta in images_metadata:
            lat, lng = meta['latitude'], meta['longitude']
            heading = meta['heading']
            point_wkt = f"POINT({lng} {lat})"
            
            # Check for existing image within radius and heading tolerance
            # Use ST_DistanceSphere for approximate meters distance (fast and simple)
            existing_img = db.query(StreetViewImage).filter(
                func.ST_DistanceSphere(
                    StreetViewImage.location,
                    func.ST_GeomFromText(point_wkt, 4326)
                ) < settings.DEDUPLICATION_RADIUS_METERS,
                func.abs(StreetViewImage.heading - heading) < settings.DEDUPLICATION_HEADING_TOLERANCE
            ).first()

            if existing_img:
                reused_count += 1
            else:
                # Create new point (point-based storage)
                new_img = StreetViewImage(
                    latitude=lat,
                    longitude=lng,
                    heading=heading,
                    pitch=meta['pitch'],
                    image_url=meta['image_url'],
                    location=point_wkt
                )
                db.add(new_img)
                new_count += 1
        
        db.commit()
        
        console.print(f"[bold green]Success! Points collected.[/bold green]")
        console.print(f"Total points along route: {len(images_metadata)}")
        console.print(f"New points created: {new_count} | Reused existing: {reused_count}")

    except Exception as e:
        console.print(f"[bold red]Error: {str(e)}[/bold red]")
        db.rollback()
    finally:
        db.close()

@app.command()
def list_points():
    """
    List all collected road points.
    """
    db = SessionLocal()
    try:
        total_points = db.query(StreetViewImage).count()
        points_with_images = db.query(StreetViewImage).filter(
            StreetViewImage.image_url.like('%data/images%')
        ).count()
        points_with_rqi = db.query(StreetViewImage).filter(
            StreetViewImage.rqi_score.isnot(None)
        ).count()
        
        table = Table(title="Road Points Summary")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="magenta", justify="right")
        
        table.add_row("Total Points", str(total_points))
        table.add_row("Points with Images", str(points_with_images))
        table.add_row("Points with RQI", str(points_with_rqi))
        
        console.print(table)
        
        # Show recent points
        recent = db.query(StreetViewImage).order_by(StreetViewImage.created_at.desc()).limit(10).all()
        if recent:
            console.print("\n[bold]Recent Points:[/bold]")
            for p in recent:
                rqi_str = f"RQI: {p.rqi_score}" if p.rqi_score else "No RQI"
                console.print(f"  [{p.id}] ({p.latitude:.6f}, {p.longitude:.6f}) heading={int(p.heading)}° - {rqi_str}")
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
    
    This command downloads images for all points created by 'collect-points' that
    have URLs but haven't been downloaded yet.
    
    --output-dir: Directory to save images (default: {DATA_DIR}/images)
    --limit: Max number of images to download (0 = all pending)
    """
    import requests
    import os
    from rich.progress import track
    
    # Use configured data directory or default
    if output_dir is None:
        data_dir = settings.DATA_DIR
        output_dir = os.path.join(data_dir, "images")
    
    db = SessionLocal()
    try:
        # Get absolute path for checking
        if not os.path.isabs(output_dir):
            # If relative, make it relative to backend directory or project root
            backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            project_root = os.path.dirname(backend_dir)
            output_dir = os.path.join(project_root, output_dir)
        
        # Point-based: images go directly to data/images/, NOT route_X subdirectory
        os.makedirs(output_dir, exist_ok=True)
        
        # Query: Get all points that need downloading
        # - Points with URLs (not yet downloaded)
        # - Points with local paths but files don't exist (need re-download)
        all_points = db.query(StreetViewImage).order_by(StreetViewImage.id).all()
        
        images_to_download = []
        for img in all_points:
            # Generate expected filename
            filename = f"{img.id:05d}_{img.latitude:.6f}_{img.longitude:.6f}_{int(img.heading)}.jpg"
            filepath = os.path.join(output_dir, filename)
            
            # Check if file already exists
            if os.path.exists(filepath):
                # File exists, update DB if needed
                if img.image_url != filepath:
                    img.image_url = filepath
                continue
            
            # Check if DB has local path but file doesn't exist
            if img.image_url and (img.image_url.startswith('/') or img.image_url.startswith('./') or 'data/' in img.image_url):
                # Local path in DB but file doesn't exist - need to regenerate URL and download
                images_to_download.append((img, None))  # None means regenerate URL
                continue
            
            # Check if it's a URL
            if img.image_url and (img.image_url.startswith('http://') or img.image_url.startswith('https://')):
                images_to_download.append((img, img.image_url))  # Use existing URL
                continue
        
        if limit > 0:
            images_to_download = images_to_download[:limit]
        
        if not images_to_download:
            console.print(f"[bold yellow]No points found that need downloading[/bold yellow]")
            console.print("[dim]All points have valid image files.[/dim]")
            db.commit()  # Commit any path updates
            return
        
        console.print(f"[bold blue]Downloading {len(images_to_download)} point images to {output_dir}...[/bold blue]")
        
        downloaded = 0
        skipped = 0
        errors = 0
        
        for img, url_to_use in track(images_to_download, description="Downloading..."):
            try:
                # Generate unique filename based on point (coordinate + heading)
                # Format: {image_id}_{lat}_{lng}_{heading}.jpg
                filename = f"{img.id:05d}_{img.latitude:.6f}_{img.longitude:.6f}_{int(img.heading)}.jpg"
                filepath = os.path.join(output_dir, filename)
                
                # Regenerate URL if needed (file was deleted but DB has local path)
                if url_to_use is None:
                    url_to_use = google_maps_service.get_street_view_url(
                        img.latitude, 
                        img.longitude, 
                        img.heading, 
                        img.pitch or 0
                    )
                
                response = requests.get(url_to_use, timeout=30)
                if response.status_code == 200:
                    # Check if it's actually an image (not an error response)
                    content_type = response.headers.get('content-type', '')
                    if 'image' in content_type:
                        with open(filepath, 'wb') as f:
                            f.write(response.content)
                        
                        # Update image_path in DB (point-based path)
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
        console.print(f"[bold green]Downloaded {downloaded} new images. Skipped {skipped} (already exist). Errors: {errors}[/bold green]")
        console.print(f"[bold]Images saved to: {output_dir}[/bold]")
        
    except Exception as e:
        console.print(f"[bold red]Error: {str(e)}[/bold red]")
    finally:
        db.close()


@app.command()
def analyze_image(image_path: str, simple: bool = False):
    """
    Analyze a single image for road quality.
    
    IMAGE_PATH: Path to the image file.
    --simple: Use simple heuristic analysis (no YOLO).
    """
    from app.services.road_quality import road_quality_service
    import os
    
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
    from app.services.road_quality import road_quality_service
    from rich.progress import track
    import os
    from sqlalchemy import func
    
    db = SessionLocal()
    try:
        # Point-based query: Get points to analyze
        # Determine correct data directory path
        # In Docker: always use /app/data
        # Locally: use relative path from project root
        if os.path.exists('/app'):
            # Running in Docker - always use /app/data
            data_dir = '/app/data'
        else:
            # Running locally
            data_dir = settings.DATA_DIR
            if not os.path.isabs(data_dir):
                backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                project_root = os.path.dirname(backend_dir)
                data_dir = os.path.join(project_root, data_dir)
        
        images_dir = os.path.join(data_dir, "images")
        
        # Match only local file paths (not URLs)
        # URLs start with 'http', local paths contain '/data/images/'
        from sqlalchemy import or_, and_, not_
        data_patterns = [
            f"%/data/images/%",  # Any path containing /data/images/
            f"{images_dir}%",    # Container path
        ]
        
        # Filter: must match data_patterns AND NOT start with 'http'
        local_file_filter = and_(
            or_(*[StreetViewImage.image_url.like(pattern) for pattern in data_patterns]),
            not_(StreetViewImage.image_url.like("http%"))
        )
        
        if lat is not None and lng is not None:
            # Area-based: points within radius
            center_point = f"POINT({lng} {lat})"
            filters = [
                func.ST_DistanceSphere(
                    StreetViewImage.location,
                    func.ST_GeomFromText(center_point, 4326)
                ) < radius,
                local_file_filter
            ]
            
            # If reanalyze is False, skip points that already have analysis_metadata
            if not reanalyze:
                filters.append(StreetViewImage.analysis_metadata.is_(None))
            
            query = db.query(StreetViewImage).filter(
                *filters
            ).order_by(StreetViewImage.id)
            
            if reanalyze:
                console.print(f"[dim]Re-analyzing points within {radius}m of ({lat}, {lng})[/dim]")
            else:
                console.print(f"[dim]Analyzing points within {radius}m of ({lat}, {lng}) (skipping those with analysis_metadata)[/dim]")
        else:
            # All points with downloaded images (local files, not URLs)
            filters = [local_file_filter]
            
            # If reanalyze is False, skip points that already have analysis_metadata
            if not reanalyze:
                filters.append(StreetViewImage.analysis_metadata.is_(None))
            
            query = db.query(StreetViewImage).filter(
                *filters
            ).order_by(StreetViewImage.id)
            
            if reanalyze:
                console.print(f"[dim]Re-analyzing all points with downloaded images[/dim]")
            else:
                console.print(f"[dim]Analyzing points with downloaded images (skipping those with analysis_metadata)[/dim]")
        
        if limit > 0:
            query = query.limit(limit)
        images = query.all()
        
        if not images:
            console.print(f"[bold red]No downloaded images found[/bold red]")
            console.print("[dim]Run 'download-images' first.[/dim]")
            return
        
        console.print(f"[bold blue]Analyzing {len(images)} points...[/bold blue]")
        console.print(f"[dim]Using images_dir: {images_dir} (exists: {os.path.exists(images_dir)})[/dim]")
        
        results = []
        skipped_missing = 0
        skipped_errors = 0
        analyzed_count = 0
        
        for img in track(images, description="Analyzing..."):
            # Convert host path to container path if needed
            image_path = img.image_url
            original_path = image_path
            
            # Convert path: if it's a container path (/app/) but we're running locally, convert it
            # If it's a host path but we're in Docker, convert it
            if image_path.startswith('/app/'):
                # Container path - check if we need to convert to local
                if not os.path.exists('/app'):
                    # Running locally, convert container path to local path
                    rel_path = image_path.replace('/app/data/images/', '')
                    image_path = os.path.join(images_dir, rel_path)
                # else: running in Docker, path is already correct
            elif image_path.startswith('/Users/') or image_path.startswith('/home/'):
                # Host path - check if we need to convert to container path
                if os.path.exists('/app'):
                    # Running in Docker, convert host path to container path
                    if '/data/images/' in image_path:
                        rel_path = image_path.split('/data/images/')[-1]
                        image_path = os.path.join(images_dir, rel_path)
                # else: running locally, path is already correct
            elif not image_path.startswith('/'):
                # Relative path, make it absolute
                image_path = os.path.join(images_dir, image_path)
            
            # Check if file exists
            if not os.path.exists(image_path):
                skipped_missing += 1
                # Debug: print first few missing files
                if skipped_missing <= 3:
                    console.print(f"[dim]Missing image ID {img.id}: {image_path} (images_dir: {images_dir})[/dim]")
                continue
            
            try:
                if simple:
                    result = road_quality_service.analyze_image_simple(image_path)
                else:
                    result = road_quality_service.analyze_image(image_path)
                
                results.append((img, result))
                analyzed_count += 1
                
                if save:
                    img.rqi_score = result.rqi_score
                    img.damage_count = result.damage_count
                    img.damage_types = result.damage_types
                    img.analysis_metadata = result.analysis_metadata
            except Exception as e:
                skipped_errors += 1
                # Print first few errors to help debug
                if skipped_errors <= 5:
                    console.print(f"[dim]Error analyzing image {img.id} ({image_path}): {str(e)[:150]}[/dim]")
                continue
        
        skipped_count = skipped_missing + skipped_errors
        
        if save:
            db.commit()
            console.print("[dim]RQI scores saved to database.[/dim]")
        
        # Report summary
        total_processed = analyzed_count + skipped_missing + skipped_errors
        console.print(f"[dim]Processed: {analyzed_count} analyzed, {skipped_missing} missing images, {skipped_errors} errors (total: {total_processed}/{len(images)})[/dim]")
        
        if skipped_count > 0:
            if skipped_missing > 0:
                console.print(f"[yellow]Warning: {skipped_missing} points skipped due to missing images[/yellow]")
            if skipped_errors > 0:
                console.print(f"[yellow]Warning: {skipped_errors} points skipped due to analysis errors[/yellow]")
        
        # Summary - use results list for accurate count of newly analyzed points
        if results:
            scores = [r.rqi_score for _, r in results]
            avg_rqi = sum(scores) / len(scores) if scores else 0
            
            table = Table(title="Points Analysis Summary")
            table.add_column("Metric", style="cyan")
            table.add_column("Value", style="magenta")
            
            table.add_row("Points Analyzed", str(len(results)))
            table.add_row("Average RQI", f"{avg_rqi:.2f}")
            table.add_row("Best RQI", f"{min(scores):.1f}" if scores else "N/A")
            table.add_row("Worst RQI", f"{max(scores):.1f}" if scores else "N/A")
            table.add_row("RQI 1 (Excellent)", str(sum(1 for s in scores if s == 1)))
            table.add_row("RQI 2 (Good)", str(sum(1 for s in scores if s == 2)))
            table.add_row("RQI 3 (Fair)", str(sum(1 for s in scores if s == 3)))
            table.add_row("RQI 4 (Poor)", str(sum(1 for s in scores if s == 4)))
            table.add_row("RQI 5 (Very Poor)", str(sum(1 for s in scores if s == 5)))
            
            console.print(table)
        elif results:
            # Fallback to results if not saving
            scores = [r.rqi_score for _, r in results]
            avg_rqi = sum(scores) / len(scores)
            
            table = Table(title="Points Analysis Summary")
            table.add_column("Metric", style="cyan")
            table.add_column("Value", style="magenta")
            
            table.add_row("Points Analyzed", str(len(results)))
            table.add_row("Average RQI", f"{avg_rqi:.2f}")
            table.add_row("Best RQI", f"{min(scores):.1f}")
            table.add_row("Worst RQI", f"{max(scores):.1f}")
            table.add_row("RQI 1 (Excellent)", str(sum(1 for s in scores if s == 1)))
            table.add_row("RQI 2 (Good)", str(sum(1 for s in scores if s == 2)))
            table.add_row("RQI 3 (Fair)", str(sum(1 for s in scores if s == 3)))
            table.add_row("RQI 4 (Poor)", str(sum(1 for s in scores if s == 4)))
            table.add_row("RQI 5 (Very Poor)", str(sum(1 for s in scores if s == 5)))
            
            console.print(table)
        
    except Exception as e:
        console.print(f"[bold red]Error: {str(e)}[/bold red]")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    app()
