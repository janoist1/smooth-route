
from sqlalchemy import Column, Integer, String, Float, DateTime, JSON
from sqlalchemy.ext.declarative import declarative_base
from geoalchemy2 import Geometry
from datetime import datetime

Base = declarative_base()

class StreetViewImage(Base):
    """
    Point-based storage: Each image represents a unique road point.
    Defined by location (lat, lng) + heading (direction).
    
    Routes are NOT stored - they are only tools to collect points.
    When planning a route later, we query existing points.
    """
    __tablename__ = "street_view_images"

    id = Column(Integer, primary_key=True, index=True)
    latitude = Column(Float, index=True)
    longitude = Column(Float, index=True)
    heading = Column(Float, index=True)
    pitch = Column(Float)
    image_url = Column(String) # Can be URL or local path
    location = Column(Geometry("POINT", srid=4326), index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # AI Analysis results
    rqi_score = Column(Float, nullable=True, index=True)
    damage_count = Column(Integer, default=0)
    damage_types = Column(JSON, nullable=True)

