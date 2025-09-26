from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import create_engine, Column, Integer, String, DateTime, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from pydantic import BaseModel
import os
from datetime import datetime
from typing import List, Optional, Dict, Any
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Database configuration
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:w4qu+0sj@localhost:5432/postgres")
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")

# Create SQLAlchemy engine
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Database Models (ORM)
class Item(Base):
    __tablename__ = "items"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    description = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    email = Column(String, unique=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)

# Pydantic models
class ItemCreate(BaseModel):
    name: str
    description: Optional[str] = None

class ItemResponse(BaseModel):
    id: int
    name: str
    description: Optional[str]
    created_at: datetime
    
    class Config:
        from_attributes = True

class UserCreate(BaseModel):
    username: str
    email: str

class UserResponse(BaseModel):
    id: int
    username: str
    email: str
    created_at: datetime
    
    class Config:
        from_attributes = True

# FastAPI app
app = FastAPI(title="Hybrid ORM + Raw SQL Example")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Create tables on startup
@app.on_event("startup")
async def startup_event():
    Base.metadata.create_all(bind=engine)

# Dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Health check
@app.get("/health")
async def health_check(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
        return {"status": "healthy", "environment": ENVIRONMENT}
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))

# ========================================
# ORM-BASED CRUD (Simple operations)
# ========================================

@app.post("/items/", response_model=ItemResponse)
async def create_item_orm(item: ItemCreate, db: Session = Depends(get_db)):
    """Simple create using ORM - fast development"""
    try:
        db_item = Item(**item.dict())
        db.add(db_item)
        db.commit()
        db.refresh(db_item)
        return db_item
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/items/", response_model=List[ItemResponse])
async def list_items_orm(skip: int = 0, limit: int = 10, db: Session = Depends(get_db)):
    """Simple list using ORM"""
    items = db.query(Item).offset(skip).limit(limit).all()
    return items

@app.get("/items/{item_id}", response_model=ItemResponse)
async def get_item_orm(item_id: int, db: Session = Depends(get_db)):
    """Simple get using ORM"""
    item = db.query(Item).filter(Item.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    return item

# ========================================
# RAW SQL (Complex/Performance operations)
# ========================================

@app.get("/items/search/{query}")
async def search_items_raw_sql(query: str, db: Session = Depends(get_db)):
    """Complex search using raw SQL for better performance"""
    try:
        # Use PostgreSQL full-text search features
        sql = text("""
            SELECT id, name, description, created_at,
                   ts_rank(to_tsvector('english', name || ' ' || COALESCE(description, '')), 
                          plainto_tsquery('english', :query)) as rank
            FROM items 
            WHERE to_tsvector('english', name || ' ' || COALESCE(description, '')) 
                  @@ plainto_tsquery('english', :query)
            ORDER BY rank DESC, created_at DESC
            LIMIT 20
        """)
        
        result = db.execute(sql, {"query": query})
        items = []
        for row in result:
            items.append({
                "id": row.id,
                "name": row.name,
                "description": row.description,
                "created_at": row.created_at,
                "relevance_score": float(row.rank)
            })
        return {"query": query, "results": items}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
# ========================================
# UTILITY FUNCTIONS
# ========================================

def execute_raw_query(db: Session, query: str, params: Dict[str, Any] = None) -> List[Dict]:
    """Helper function for executing raw SQL queries safely"""
    try:
        result = db.execute(text(query), params or {})
        return [dict(row) for row in result]
    except Exception as e:
        logger.error(f"Raw query failed: {e}")
        raise

@app.get("/debug/query")
async def debug_raw_query(query: str, db: Session = Depends(get_db)):
    """Debug endpoint for testing raw SQL queries (remove in production!)"""
    if ENVIRONMENT != "development":
        raise HTTPException(status_code=403, detail="Debug endpoint disabled in production")
    
    try:
        # Only allow SELECT queries for safety
        if not query.strip().lower().startswith('select'):
            raise HTTPException(status_code=400, detail="Only SELECT queries allowed")
        
        result = execute_raw_query(db, query)
        return {"query": query, "result": result}
    except Exception as e:        raise HTTPException(status_code=400, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)