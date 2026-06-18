from fastapi import FastAPI
from pydantic import BaseModel
from supabase import create_client
from dotenv import load_dotenv
import os

load_dotenv()

app = FastAPI()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)


class SnapshotRequest(BaseModel):
    company_id: str


@app.get("/")
def root():
    return {"status": "MappaOS Agent API running"}


@app.post("/snapshot")
def get_snapshot(request: SnapshotRequest):
    response = (
        supabase
        .table("company_snapshot")
        .select("*")
        .eq("company_id", request.company_id)
        .execute()
    )

    if not response.data:
        return {"error": "Company snapshot not found"}

    return response.data[0]