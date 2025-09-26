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
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://fastapi_user:fastapi_password@localhost:5432/fastapi_db")
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

@app.get("/analytics/items-summary")
async def get_items_analytics_raw_sql(db: Session = Depends(get_db)):
    """Analytics query using raw SQL for complex aggregations"""
    try:
        sql = text("""
            WITH monthly_stats AS (
                SELECT 
                    DATE_TRUNC('month', created_at) as month,
                    COUNT(*) as items_created,
                    AVG(LENGTH(name)) as avg_name_length
                FROM items 
                GROUP BY DATE_TRUNC('month', created_at)
            ),
            total_stats AS (
                SELECT 
                    COUNT(*) as total_items,
                    MIN(created_at) as first_item_date,
                    MAX(created_at) as last_item_date
                FROM items
            )
            SELECT 
                json_build_object(
                    'total_items', ts.total_items,
                    'first_item_date', ts.first_item_date,
                    'last_item_date', ts.last_item_date,
                    'monthly_breakdown', json_agg(
                        json_build_object(
                            'month', ms.month,
                            'items_created', ms.items_created,
                            'avg_name_length', ROUND(ms.avg_name_length, 2)
                        ) ORDER BY ms.month DESC
                    )
                ) as analytics
            FROM total_stats ts
            CROSS JOIN monthly_stats ms
            GROUP BY ts.total_items, ts.first_item_date, ts.last_item_date
        """)
        
        result = db.execute(sql).fetchone()
        return result.analytics if result else {}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/items/bulk-create")
async def bulk_create_items_raw_sql(items: List[ItemCreate], db: Session = Depends(get_db)):
    """Bulk insert using raw SQL for better performance"""
    if not items or len(items) > 1000:  # Limit bulk operations
        raise HTTPException(status_code=400, detail="Invalid item count (max 1000)")
    
    try:
        # Using PostgreSQL's efficient bulk insert
        values = []
        for item in items:
            values.append({
                "name": item.name,
                "description": item.description or None
            })
        
        sql = text("""
            INSERT INTO items (name, description, created_at)
            SELECT 
                unnest(:names),
                unnest(:descriptions),
                NOW()
            RETURNING id, name, description, created_at
        """)
        
        result = db.execute(sql, {
            "names": [item.name for item in items],
            "descriptions": [item.description for item in items]
        })
        
        db.commit()
        
        created_items = []
        for row in result:
            created_items.append({
                "id": row.id,
                "name": row.name,
                "description": row.description,
                "created_at": row.created_at
            })
        
        return {
            "message": f"Created {len(created_items)} items",
            "items": created_items
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

# ========================================
# HYBRID APPROACH (ORM + Raw SQL)
# ========================================

@app.get("/users/{user_id}/items")
async def get_user_items_hybrid(user_id: int, db: Session = Depends(get_db)):
    """Hybrid: Use ORM for simple checks, raw SQL for complex queries"""
    
    # First, check if user exists using ORM (simple and clear)
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Then use raw SQL for complex aggregation
    sql = text("""
        SELECT 
            i.*,
            COUNT(*) OVER() as total_count,
            ROW_NUMBER() OVER(ORDER BY i.created_at DESC) as row_num
        FROM items i
        WHERE i.id IN (
            -- Assume we had a user_items relationship table
            SELECT item_id FROM user_items WHERE user_id = :user_id
        )
        ORDER BY i.created_at DESC
    """)
    
    try:
        result = db.execute(sql, {"user_id": user_id})
        items = [dict(row) for row in result]
        
        return {
            "user": {
                "id": user.id,
                "username": user.username,
                "email": user.email
            },
            "items": items,
            "total_count": len(items)
        }
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
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)