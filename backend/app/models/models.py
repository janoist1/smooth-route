from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declarative_base
from geoalchemy2 import Geometry
from datetime import datetime

Base = declarative_base()

class Route(Base):
    __tablename__ = "routes"

    id = Column(Integer, primary_key=True, index=True)
    origin = Column(String, nullable=False)
    destination = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Geometry: LineString representing the route
    path = Column(Geometry('LINESTRING', srid=4326))
    
    images = relationship("StreetViewImage", back_populates="route")

class StreetViewImage(Base):
    __tablename__ = "street_view_images"

    id = Column(Integer, primary_key=True, index=True)
    route_id = Column(Integer, ForeignKey("routes.id"))
    
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    heading = Column(Float, nullable=False)
    pitch = Column(Float, default=0.0)
    
    image_url = Column(String) # URL or path to stored image
    captured_at = Column(DateTime, default=datetime.utcnow)
    
    # Metadata for Phase 2 (Road Quality)
    rqi_score = Column(Float, nullable=True) # 1-5 scale
    
    # Geometry: Point
    location = Column(Geometry('POINT', srid=4326))
    
    route = relationship("Route", back_populates="images")
