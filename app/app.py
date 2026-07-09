import os
import time
import logging
import psycopg2
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware

# Configure logger
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("web-app")

app = FastAPI(title="Project 1")

# Read Database connection details from Environment Variables
DB_HOST = os.getenv("DB_HOST", "db")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "postgres")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "secret")
DB_AUTH_MODE = os.getenv("DB_AUTH_MODE", "sql-auth").lower()

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

def get_db_connection():
    logger.info("Using standard username/password (SQL Auth) credentials")
    db_password = DB_PASSWORD
    
    try:
        # Establish PostgreSQL connection
        conn = psycopg2.connect(
            host=DB_HOST,
            port=DB_PORT,
            database=DB_NAME,
            user=DB_USER,
            password=db_password,
            # For Azure SQL/PostgreSQL, SSL is typically required
            sslmode="require" if DB_AUTH_MODE == "azure-ad" else "prefer",
            connect_timeout=5 # 5 seconds connection timeout
        )
        logger.info("Database connection successfully established")
        return conn
    except psycopg2.OperationalError as e:
        logger.error(f"Database connection error: {str(e)}")
        raise e

@app.middleware("http")
async def log_request_execution_latency(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    logger.info(f"HTTP {request.method} {request.url.path} processed in {time.time() - start_time:.4f}s")
    return response

@app.get("/")
def read_root():
    return{
        "status": "Online",
        "configuration": {
            "db_host": DB_HOST,
            "db_port": DB_PORT,
            "db_name": DB_NAME,
            "db_user": DB_USER,
            "auth_mode": DB_AUTH_MODE,
        },
        "description": "lorem Ipsum"
    }

@app.post("/register")
def register():
    pass

@app.post("/login")
def login():
    pass

@app.get("/login-check")
def login_check():
    pass

@app.get("/health")
def health_check():
    return  {"status": "healthy"}

@app.get("/db-check")
def db_check():
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT version();")
        db_version = cursor.fetchone()
        cursor.close()

        return {
            "database_connection": "SUCCESS",
            "postgres_version": db_version[0],
            "auth_method_used": DB_AUTH_MODE
        }
    except Exception as e:
        logger.error(f"Failed database connectivity verification: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail={
                "database_connection": "FAILED",
                "reason": str(e)
            }
        )
    finally:
        if conn:
            conn.close()