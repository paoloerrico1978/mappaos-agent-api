from fastapi import FastAPI, UploadFile, File, Form
from pydantic import BaseModel
from supabase import create_client
from dotenv import load_dotenv
from openai import OpenAI
import fitz
import os

load_dotenv()

app = FastAPI()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "openai/gpt-4o-mini")

supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)

client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=OPENROUTER_API_KEY,
)


class SnapshotRequest(BaseModel):
    company_id: str


class MemoryRequest(BaseModel):
    company_id: str
    memory_type: str
    title: str
    content: str
    category: str = "general"
    source: str = "manual"
    confidence: str = "medium"
    importance: int = 5


class DocumentRequest(BaseModel):
    company_id: str
    title: str
    document_type: str
    content: str
    source: str = "manual"


class AssessmentRequest(BaseModel):
    company_id: str
    category: str
    score: int
    priority: int = 5
    maturity_level: str = ""
    notes: str = ""


class AgentChatRequest(BaseModel):
    company_id: str
    message: str
    agent_name: str = "growth_agent"


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

    documents = (
    supabase
    .table("documents")
    .select("""
        title,
        document_type,
        content,
        source
    """)
    .eq("company_id", request.company_id)
    .execute()
)


@app.post("/growth-analysis")
def growth_analysis(request: SnapshotRequest):
    response = (
        supabase
        .table("company_snapshot")
        .select("*")
        .eq("company_id", request.company_id)
        .execute()
    )

    if not response.data:
        return {"error": "Company snapshot not found"}

    snapshot = response.data[0]

    prompt = f"""
Sei il Growth Agent di MappaOS.

Analizza questa azienda sulla base delle 6 direttrici della Mappa della Crescita:
- Mercati Esteri
- Finanziaria
- Industriale
- Penetration
- Product
- Market

Dati azienda:
{snapshot}

Restituisci esclusivamente un JSON valido seguendo esattamente questa struttura:
{{
  "sintesi": "",
  "punti_di_forza": [],
  "aree_deboli": [],
  "priorita_operative": [],
  "prossime_azioni": [],
  "rischi": []
}}
"""

    completion = client.chat.completions.create(
        timeout=30,
        model=OPENROUTER_MODEL,
        messages=[
            {
                "role": "system",
                "content": """
Sei il Growth Agent di MappaOS.

Rispondi esclusivamente con JSON valido.

Regole:
- NON usare markdown
- NON usare ```json
- NON usare ```
- NON aggiungere testo prima del JSON
- NON aggiungere testo dopo il JSON
- Restituisci solo un oggetto JSON valido
"""
            },
            {
                "role": "user",
                "content": prompt
            }
        ],
    )

    analysis = completion.choices[0].message.content

    supabase.table("agent_outputs").insert({
        "company_id": request.company_id,
        "agent_name": "growth_agent",
        "output_type": "analysis",
        "content": {
            "analysis": analysis
        }
    }).execute()

    return {
        "company_id": request.company_id,
        "analysis": analysis
    }


@app.get("/company-history/{company_id}")
def company_history(company_id: str):
    response = (
        supabase
        .table("agent_outputs")
        .select("*")
        .eq("company_id", company_id)
        .order("created_at", desc=True)
        .limit(10)
        .execute()
    )

    return {
        "company_id": company_id,
        "history": response.data
    }


@app.post("/memory")
def create_memory(request: MemoryRequest):
    response = supabase.table("company_memory").insert({
        "company_id": request.company_id,
        "memory_type": request.memory_type,
        "title": request.title,
        "content": request.content,
        "category": request.category,
        "source": request.source,
        "confidence": request.confidence,
        "importance": request.importance,
        "status": "active"
    }).execute()

    return {
        "company_id": request.company_id,
        "memory": response.data[0] if response.data else None
    }


@app.post("/document")
def create_document(request: DocumentRequest):
    response = supabase.table("documents").insert({
        "company_id": request.company_id,
        "title": request.title,
        "document_type": request.document_type,
        "content": request.content,
        "source": request.source,
        "status": "active"
    }).execute()

    return {
        "company_id": request.company_id,
        "document": response.data[0] if response.data else None
    }


@app.post("/assessment")
def create_assessment(request: AssessmentRequest):
    response = supabase.table("assessments").insert({
        "company_id": request.company_id,
        "assessment_name": "Manual update",
        "category": request.category,
        "score": request.score,
        "priority": request.priority,
        "maturity_level": request.maturity_level,
        "notes": request.notes
    }).execute()

    return {
        "company_id": request.company_id,
        "assessment": response.data[0] if response.data else None
    }


@app.post("/upload-pdf")
async def upload_pdf(
    company_id: str = Form(...),
    document_type: str = Form("pdf"),
    source: str = Form("upload"),
    file: UploadFile = File(...)
):
    pdf_bytes = await file.read()

    pdf_doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    extracted_text = ""

    for page in pdf_doc:
        extracted_text += page.get_text()

    response = supabase.table("documents").insert({
        "company_id": company_id,
        "file_name": file.filename,
        "title": file.filename,
        "document_type": document_type,
        "content": extracted_text[:50000],
        "source": source,
        "status": "processed"
    }).execute()

    return {
        "company_id": company_id,
        "file_name": file.filename,
        "characters_extracted": len(extracted_text),
        "document": response.data[0] if response.data else None
    }


@app.post("/agent-chat")
def agent_chat(request: AgentChatRequest):
    response = (
        supabase
        .table("company_snapshot")
        .select("*")
        .eq("company_id", request.company_id)
        .execute()
    )

    if not response.data:
        return {"error": "Company snapshot not found"}

    snapshot = response.data[0]

    agent_prompts = {
        "growth_agent": "Sei il Growth Agent. Ti occupi di crescita complessiva, priorità strategiche e roadmap.",
        "cfo_agent": "Sei il CFO Agent. Ti occupi di finanza, marginalità, cassa, PFN, sostenibilità economica e rischi finanziari.",
        "export_agent": "Sei l'Export Agent. Ti occupi di mercati esteri, internazionalizzazione, canali distributivi e priorità paese.",
        "hr_agent": "Sei l'HR Agent. Ti occupi di persone, organizzazione, competenze, ruoli, leadership e struttura.",
        "sales_agent": "Sei il Sales Agent. Ti occupi di vendite, pipeline, conversione, clienti, pricing e go-to-market.",
        "operations_agent": "Sei l'Operations Agent. Ti occupi di processi, produzione, efficienza, qualità e capacità operativa.",
        "esg_agent": "Sei l'ESG Agent. Ti occupi di sostenibilità, compliance ESG, impatti ambientali, sociali e governance.",
        "legal_agent": "Sei il Legal Agent. Ti occupi di rischi legali, contratti, compliance e governance."
    }

    selected_prompt = agent_prompts.get(request.agent_name, agent_prompts["growth_agent"])

    supabase.table("agent_messages").insert({
        "company_id": request.company_id,
        "agent_name": request.agent_name,
        "role": "user",
        "content": request.message
    }).execute()

    prompt = f"""
{selected_prompt}

Contesto aziendale:
Assessment:
{snapshot["assessments"]}

Memorie:
{snapshot["memories"]}

Documenti:
{snapshot["documents"]}

Domanda utente:
{request.message}

Rispondi in italiano, come consulente professionale.
Struttura la risposta in:
1. Analisi
2. Criticità
3. Azioni consigliate
"""

    completion = client.chat.completions.create(
        timeout=30,
        model=OPENROUTER_MODEL,
        messages=[
            {
                "role": "system",
                "content": "Sei un agente consulenziale specializzato per PMI. Usa solo il contesto disponibile e dichiara le incertezze."
            },
            {
                "role": "user",
                "content": prompt
            }
        ],
    )

    answer = completion.choices[0].message.content

    supabase.table("agent_messages").insert({
        "company_id": request.company_id,
        "agent_name": request.agent_name,
        "role": "assistant",
        "content": answer
    }).execute()

    return {
        "company_id": request.company_id,
        "agent_name": request.agent_name,
        "message": request.message,
        "answer": answer
    }