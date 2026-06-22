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


class KnowledgeRequest(BaseModel):
    category: str
    station: str
    title: str
    content: str
    source: str = "mappa"
    importance: int = 5


class AgentOverrideRequest(BaseModel):
    company_id: str
    agent_name: str
    override_prompt: str = ""
    custom_instructions: str = ""


class SkillOverrideRequest(BaseModel):
    company_id: str
    agent_name: str
    skill_name: str
    override_prompt: str = ""
    is_enabled: bool = True


class JobRequest(BaseModel):
    company_id: str
    name: str
    agent_name: str
    prompt: str
    frequency: str = "manual"
    trigger_type: str = "manual"
    output_type: str = "report"
    destination: str = "agent_output"
    next_run: str = None


@app.post("/skill-override")
def save_skill_override(request: SkillOverrideRequest):
    response = supabase.table("company_agent_skill_overrides").insert({
        "company_id": request.company_id,
        "agent_name": request.agent_name,
        "skill_name": request.skill_name,
        "override_prompt": request.override_prompt,
        "is_enabled": request.is_enabled
    }).execute()

    return {
        "company_id": request.company_id,
        "agent_name": request.agent_name,
        "skill_name": request.skill_name,
        "override": response.data[0] if response.data else None
    }


@app.post("/agent-override")
def save_agent_override(request: AgentOverrideRequest):
    response = supabase.table("company_agent_overrides").insert({
        "company_id": request.company_id,
        "agent_name": request.agent_name,
        "override_prompt": request.override_prompt,
        "custom_instructions": request.custom_instructions,
        "is_active": True
    }).execute()

    return {
        "company_id": request.company_id,
        "agent_name": request.agent_name,
        "override": response.data[0] if response.data else None
    }


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

def get_agent_configuration(company_id: str, agent_name: str):
    skills_response = (
        supabase
        .table("agent_skills")
        .select("*")
        .eq("agent_name", agent_name)
        .execute()
    )

    skill_overrides_response = (
        supabase
        .table("company_agent_skill_overrides")
        .select("*")
        .eq("company_id", company_id)
        .eq("agent_name", agent_name)
        .eq("is_enabled", True)
        .execute()
    )

    agent_override_response = (
        supabase
        .table("company_agent_overrides")
        .select("*")
        .eq("company_id", company_id)
        .eq("agent_name", agent_name)
        .eq("is_active", True)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )

    return {
        "skills": skills_response.data or [],
        "skill_overrides": skill_overrides_response.data or [],
        "agent_override": agent_override_response.data[0] if agent_override_response.data else None
    }


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

    knowledge_response = (
        supabase
        .table("knowledge_base")
        .select("*")
        .order("importance", desc=True)
        .limit(20)
        .execute()
    )

    knowledge = knowledge_response.data
    agent_config = get_agent_configuration(request.company_id, "growth_agent")

    prompt = f"""
Sei il Growth Agent di MappaOS.

Analizza questa azienda sulla base delle 6 direttrici della Mappa della Crescita:
- Mercati Esteri
- Finanziaria
- Industriale
- Penetration
- Product
- Market

CONTESTO AZIENDALE

Assessment:
{snapshot["assessments"]}

Memorie aziendali:
{snapshot["memories"]}

Documenti aziendali:
{snapshot["documents"]}

CONOSCENZA DELLA MAPPA DELLA CRESCITA

{knowledge}

CONFIGURAZIONE GROWTH AGENT

Skill standard MappaOS:
{agent_config["skills"]}

Override skill aziendali:
{agent_config["skill_overrides"]}

Istruzioni specifiche aziendali:
{agent_config["agent_override"]}

REGOLE DI PRIORITÀ

1. Le informazioni aziendali hanno sempre priorità.
2. Assessment, memorie e documenti aziendali sono la fonte primaria.
3. La Knowledge Base della Mappa serve come metodo, benchmark e best practice.
4. Se la conoscenza generale è in contrasto con la realtà aziendale, prevale la realtà aziendale.
5. Quando usi una best practice o un principio della Mappa, rendilo esplicito.

Restituisci esclusivamente un JSON valido seguendo esattamente questa struttura:
{{
  "sintesi": "",
  "punti_di_forza": [],
  "aree_deboli": [],
  "suggerimenti_mappa": [],
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
    agent_config = get_agent_configuration(request.company_id, request.agent_name)

    supabase.table("agent_messages").insert({
        "company_id": request.company_id,
        "agent_name": request.agent_name,
        "role": "user",
        "content": request.message
    }).execute()

    prompt = f"""
{selected_prompt}

CONFIGURAZIONE AGENTE

Skill standard:
{agent_config["skills"]}

Override skill aziendali:
{agent_config["skill_overrides"]}

Istruzioni specifiche aziendali:
{agent_config["agent_override"]}

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


@app.post("/knowledge")
def create_knowledge(request: KnowledgeRequest):

    response = supabase.table("knowledge_base").insert({
        "category": request.category,
        "station": request.station,
        "title": request.title,
        "content": request.content,
        "source": request.source,
        "importance": request.importance
    }).execute()

    return response.data[0]


@app.get("/knowledge")
def get_knowledge():

    response = (
        supabase
        .table("knowledge_base")
        .select("*")
        .order("importance", desc=True)
        .execute()
    )

    return response.data


@app.delete("/memory/{memory_id}")
def delete_memory(memory_id: str):
    response = (
        supabase
        .table("company_memory")
        .delete()
        .eq("id", memory_id)
        .execute()
    )

    return {
        "deleted": True,
        "memory_id": memory_id,
        "data": response.data
    }


@app.delete("/document/{document_id}")
def delete_document(document_id: str):
    response = (
        supabase
        .table("documents")
        .delete()
        .eq("id", document_id)
        .execute()
    )

    return {
        "deleted": True,
        "document_id": document_id,
        "data": response.data
    }

@app.get("/agent-config/{company_id}/{agent_name}")
def get_agent_config(company_id: str, agent_name: str):
    skills_response = (
        supabase
        .table("agent_skills")
        .select("*")
        .eq("agent_name", agent_name)
        .execute()
    )

    overrides_response = (
        supabase
        .table("company_agent_skill_overrides")
        .select("*")
        .eq("company_id", company_id)
        .eq("agent_name", agent_name)
        .execute()
    )

    agent_override_response = (
        supabase
        .table("company_agent_overrides")
        .select("*")
        .eq("company_id", company_id)
        .eq("agent_name", agent_name)
        .eq("is_active", True)
        .execute()
    )

    return {
        "company_id": company_id,
        "agent_name": agent_name,
        "skills": skills_response.data,
        "skill_overrides": overrides_response.data,
        "agent_override": agent_override_response.data[0] if agent_override_response.data else None
    }

@app.post("/run-job/{job_id}")

}

@app.post("/jobs")
def create_job(request: JobRequest):
    response = supabase.table("scheduled_jobs").insert({
        "company_id": request.company_id,
        "name": request.name,
        "agent_name": request.agent_name,
        "prompt": request.prompt,
        "frequency": request.frequency,
        "trigger_type": request.trigger_type,
        "output_type": request.output_type,
        "destination": request.destination,
        "next_run": request.next_run,
        "enabled": True
    }).execute()

    return response.data[0] if response.data else None


@app.get("/jobs/{company_id}")
def list_jobs(company_id: str):
    response = (
        supabase
        .table("scheduled_jobs")
        .select("*")
        .eq("company_id", company_id)
        .order("created_at", desc=True)
        .execute()
    )

    return response.data

@app.post("/run-job/{job_id}")
def run_job(job_id: str):
    job_response = (
        supabase
        .table("scheduled_jobs")
        .select("*")
        .eq("id", job_id)
        .single()
        .execute()
    )

    job = job_response.data

    if not job:
        return {"error": "Job not found"}

    snapshot_response = (
        supabase
        .table("company_snapshot")
        .select("*")
        .eq("company_id", job["company_id"])
        .execute()
    )

    if not snapshot_response.data:
        return {"error": "Company snapshot not found"}

    snapshot = snapshot_response.data[0]

    prompt = f"""
Sei {job["agent_name"]} di MappaOS.

Devi eseguire questa attività programmata:

{job["prompt"]}

Contesto aziendale:
{snapshot}

Restituisci un report operativo in italiano con:
1. Sintesi
2. Evidenze
3. Rischi
4. Azioni consigliate
"""

    completion = client.chat.completions.create(
        timeout=30,
        model=OPENROUTER_MODEL,
        messages=[
            {
                "role": "system",
                "content": "Sei un agente operativo per PMI. Produci output chiari, concreti e utilizzabili."
            },
            {
                "role": "user",
                "content": prompt
            }
        ],
    )

    output = completion.choices[0].message.content

    supabase.table("agent_outputs").insert({
        "company_id": job["company_id"],
        "agent_name": job["agent_name"],
        "output_type": job["output_type"],
        "content": {
            "job_id": job_id,
            "job_name": job["name"],
            "output": output
        }
    }).execute()

    supabase.table("scheduled_jobs").update({
        "last_run": "now()"
    }).eq("id", job_id).execute()

    return {
        "job_id": job_id,
        "company_id": job["company_id"],
        "agent_name": job["agent_name"],
        "output": output
    }