import os
from dotenv import load_dotenv
# Load environment variables from .env.local
load_dotenv(".env.local")
import shutil
import io
from docx import Document
from docx.shared import Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from typing import List, Optional
import library_chat
from fastapi import FastAPI, Request, UploadFile, File, Form, HTTPException, Query
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
import firebase_admin
from firebase_admin import credentials, firestore, storage
from datetime import datetime
import time

# --- Graph Algorithms Import ---
import graph_algorithms
from graph_algorithms import GraphAnalyzer, TagIndexer, TagClusterer, optimize_graph_computation

# --- Embedding Manager Import ---
import embedding_manager
from embedding_manager import EmbeddingManager, HighlightEmbeddingManager, generate_embedding_from_ai, generate_embeddings_batch, get_highlights_for_doc

# --- RAG Retrieval Import ---
import rag_retrieval
from rag_retrieval import RAGRetriever, generate_highlight_embeddings_batch

# --- Firebase Initialization ---
# NOTE: You must place your 'serviceAccountKey.json' in the root directory.
# If not present, the app will try to initialize with default credentials 
# (which works if deployed on Google Cloud) or mock it for structure demo.

try:
    if os.path.exists("serviceAccountKey.json"):
        cred = credentials.Certificate("serviceAccountKey.json")
        firebase_admin.initialize_app(cred, {
            'storageBucket': 'your-project-id.appspot.com' # Replace with your bucket
        })
    else:
        # Fallback for demo purposes if no key exists yet
        print("WARNING: serviceAccountKey.json not found. Firebase calls will fail.")
        firebase_admin.initialize_app()
    db = firestore.client()
except Exception as e:
    print(f"CRITICAL WARNING: Firebase initialization failed. Error: {e}")
    db = None # Mock or handle None in routes

# --- Simple Local "Database" for metadata if DB is None ---
# This allows the app to work without Firebase
LOCAL_DB_FILE = "local_metadata.json"
LOCAL_HIGHLIGHTS_FILE = "local_highlights.json"
LOCAL_CHAT_FILE = "local_chat_history.json"
import json

# --- Graph Cache ---
GRAPH_CACHE = {
    "data": None,
    "timestamp": 0,
    "ttl": 3600  # 1 hour cache
}

# --- Embedding Manager ---
embedding_mgr = EmbeddingManager()

# --- Highlight Embedding Manager (for RAG) ---
highlight_emb_mgr = HighlightEmbeddingManager()

# --- RAG Retriever ---
rag_retriever = RAGRetriever(highlight_emb_mgr)

def invalidate_graph_cache():
    """Invalidate graph cache when documents or highlights change."""
    global GRAPH_CACHE
    GRAPH_CACHE["data"] = None
    GRAPH_CACHE["timestamp"] = 0

def get_local_docs():
    if os.path.exists(LOCAL_DB_FILE):
        with open(LOCAL_DB_FILE, "r") as f:
            return json.load(f)
    return []

def save_local_doc(doc_data):
    docs = get_local_docs()
    docs.append(doc_data)
    with open(LOCAL_DB_FILE, "w") as f:
        json.dump(docs, f, ensure_ascii=False, indent=2)

def get_local_highlights(doc_id=None):
    if os.path.exists(LOCAL_HIGHLIGHTS_FILE):
        with open(LOCAL_HIGHLIGHTS_FILE, "r") as f:
            data = json.load(f)
            if doc_id:
                return [h for h in data if h['doc_id'] == doc_id]
            return data
    return []

def save_local_highlight(h_data):
    hs = get_local_highlights()
    hs.append(h_data)
    with open(LOCAL_HIGHLIGHTS_FILE, "w") as f:
        json.dump(hs, f, ensure_ascii=False, indent=2)

def get_local_chat():
    if os.path.exists(LOCAL_CHAT_FILE):
        with open(LOCAL_CHAT_FILE, "r") as f:
            return json.load(f)
    return []

def save_local_chat(chat_entry):
    chat = get_local_chat()
    chat.append({
        **chat_entry,
        "timestamp": datetime.now().isoformat()
    })
    with open(LOCAL_CHAT_FILE, "w") as f:
        json.dump(chat, f, ensure_ascii=False, indent=2)

# --- AI Integration (Qianwen) ---
from openai import OpenAI
def get_ai_client():
    api_key = os.getenv("DASHSCOPE_API_KEY")
    if not api_key:
        return None
    return OpenAI(
        api_key=api_key,
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
    )


# --- App Configuration ---
app = FastAPI(title="Research Assistant")

# Create static dir if not exists before mounting
if not os.path.exists("static"):
    os.makedirs("static")

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# --- Global Exception Handlers ---
@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    return JSONResponse(
        status_code=exc.status_code,
        content={"message": exc.detail},
    )

@app.exception_handler(Exception)
async def general_exception_handler(request, exc):
    print(f"CRITICAL ERROR: {exc}")
    return JSONResponse(
        status_code=500,
        content={"message": f"Global Error: {str(exc)}"},
    )

# --- Pydantic Models ---
class ChatRequest(BaseModel):
    text: str
    action: str = "chat"
    history: List[dict] = []
    context: Optional[str] = None

class SemanticSearchRequest(BaseModel):
    query: str

class HighlightRequest(BaseModel):
    doc_id: str
    content: str
    tag: str
    color: str

class CompareRequest(BaseModel):
    doc_ids: List[str]

# --- Routes: Frontend (HTML) ---

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """Màn hình Library Manager"""
    # Fetch docs from Firestore for initial render
    documents = []
    if db:
        try:
            docs_ref = db.collection('documents').order_by('uploaded_at', direction=firestore.Query.DESCENDING).stream()
            documents = [{'id': d.id, **d.to_dict()} for d in docs_ref]
        except Exception as e:
            print(f"Error fetching docs: {e}")
    
    # Merge with local docs if no results or as fallback
    local_docs = get_local_docs()
    # Very basic merging logic
    for ld in local_docs:
        # Handle datetime serialization if needed, here we assume strings or simple types
        documents.append(ld)
        
    return templates.TemplateResponse("index.html", {"request": request, "documents": documents})

@app.get("/api/status")
async def get_status():
    return {"status": "ok", "version": "1.0.3", "timestamp": datetime.now().isoformat()}

@app.get("/reader/{doc_id}", response_class=HTMLResponse)
async def pdf_reader(request: Request, doc_id: str):
    """Màn hình PDF Reader"""
    document = None
    if db:
        try:
            doc_ref = db.collection('documents').document(doc_id).get()
            if doc_ref.exists:
                document = doc_ref.to_dict()
                document['id'] = doc_id
        except Exception as e:
            print(f"Error fetching doc: {e}")

    if not document:
        # Check local docs
        for ld in get_local_docs():
            if ld['id'] == doc_id:
                document = ld
                break

    if not document:
         # Mock data for demo if DB fails
        document = {"id": doc_id, "filename": "Demo.pdf", "url": "https://raw.githubusercontent.com/mozilla/pdf.js/ba2edeae/web/compressed.tracemonkey-pldi-09.pdf"}

    return templates.TemplateResponse("reader.html", {"request": request, "document": document})

@app.get("/compare-view", response_class=HTMLResponse)
async def compare_view(request: Request, ids: str):
    doc_ids = ids.split(",")
    docs = get_local_docs()
    selected = [d for d in docs if d['id'] in doc_ids]
    return templates.TemplateResponse("compare.html", {"request": request, "documents": selected})

@app.get("/graph", response_class=HTMLResponse)
async def graph_view(request: Request):
    return templates.TemplateResponse("graph.html", {"request": request})

# --- Routes: API Endpoints ---

@app.post("/api/upload")
async def upload_pdf(file: UploadFile = File(...)):
    """Upload PDF to Firebase Storage and save meta to Firestore, fallback to local storage"""
    try:
        # 1. Try Firebase Storage
        try:
            bucket = storage.bucket()
            blob = bucket.blob(f"pdfs/{file.filename}")
            blob.upload_from_file(file.file, content_type="application/pdf")
            blob.make_public()
            file_url = blob.public_url
        except Exception as e:
            print(f"Firebase Storage failed, falling back to local: {e}")
            # Reset file pointer
            file.file.seek(0)
            # Save to static/uploads
            local_path = os.path.join("static", "uploads", file.filename)
            with open(local_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
            # Use local URL
            file_url = f"/static/uploads/{file.filename}"
        
        # 2. Save Metadata (Try Firestore, then Local)
        doc_data = {
            "filename": file.filename,
            "uploaded_at": datetime.now().isoformat(),
            "url": file_url
        }
        
        doc_id = f"local_{int(datetime.now().timestamp())}"
        if db:
            try:
                # Convert back to datetime for Firestore if desired
                firestore_data = doc_data.copy()
                firestore_data["uploaded_at"] = datetime.now()
                update_time, doc_ref = db.collection('documents').add(firestore_data)
                doc_id = doc_ref.id
            except Exception as e:
                print(f"Firestore save failed, using local: {e}")
                save_local_doc({**doc_data, "id": doc_id})
        else:
            save_local_doc({**doc_data, "id": doc_id})
        
        # Invalidate graph cache since new document was added
        invalidate_graph_cache()
        
        return {"status": "success", "doc_id": doc_id, "data": doc_data}
    except Exception as e:
        print(f"Everything failed: {e}")
        return JSONResponse(status_code=500, content={"message": str(e)})

# === HIGHLIGHT EMBEDDING ENDPOINTS ===

@app.get("/api/highlight-embeddings/status")
async def get_highlight_embeddings_status():
    """Get status of highlight embeddings for RAG"""
    try:
        highlights = get_local_highlights()
        stats = highlight_emb_mgr.get_stats()
        
        # Check which highlights need embeddings
        needs_embedding = []
        for hl in highlights:
            hl_id = hl.get('id', '')
            content = hl.get('content', '')
            if hl_id and content and highlight_emb_mgr.needs_embedding(hl_id, content):
                needs_embedding.append({
                    'id': hl_id,
                    'doc_id': hl.get('doc_id', ''),
                    'tag': hl.get('tag', '')
                })
        
        total_highlights = len(highlights)
        embedded_count = stats.get('total', 0)
        coverage = (embedded_count / total_highlights * 100) if total_highlights > 0 else 0
        
        return {
            "total_highlights": total_highlights,
            "embedded_highlights": embedded_count,
            "coverage_percent": round(coverage, 1),
            "needs_embedding": needs_embedding[:10],  # First 10 for preview
            "needs_embedding_count": len(needs_embedding),
            "stats": stats
        }
    except Exception as e:
        print(f"Error in highlight embeddings status: {e}")
        return JSONResponse(status_code=500, content={"message": str(e)})


@app.post("/api/highlight-embeddings/generate")
async def generate_highlight_embeddings(force: bool = Query(False, description="Force regenerate all")):
    """Generate embeddings for all highlights"""
    client = get_ai_client()
    if not client:
        return JSONResponse(status_code=500, content={"message": "AI Client not initialized"})
    
    try:
        highlights = get_local_highlights()
        
        result = await generate_highlight_embeddings_batch(
            client,
            highlights,
            highlight_emb_mgr,
            force=force
        )
        
        return {
            "status": "success",
            **result
        }
    except Exception as e:
        print(f"Error generating highlight embeddings: {e}")
        import traceback
        traceback.print_exc()
        return JSONResponse(status_code=500, content={"message": str(e)})


@app.post("/api/library-chat")
async def library_chat_endpoint(req: ChatRequest):
    """Trò chuyện với toàn bộ thư viện sử dụng RAG (Retrieval Augmented Generation)"""
    client = get_ai_client()
    if not client:
        return JSONResponse(status_code=500, content={"message": "AI Client not initialized"})
        
    try:
        # 1. Semantic search for relevant highlights based on user's query
        user_query = req.text
        
        # Retrieve relevant highlights using RAG
        relevant_highlights = await rag_retriever.search_highlights_by_query(
            client,
            user_query,
            top_k=10,
            min_similarity=0.3
        )
        
        # 2. Build context from retrieved highlights
        context = rag_retriever.build_rag_context(relevant_highlights)
        
        # 3. Get confidence level
        confidence = rag_retriever.get_confidence_level(relevant_highlights)
        
        # 4. Format sources for response
        sources = rag_retriever.format_sources(relevant_highlights, max_sources=5)
        
        # 5. Build AI prompt with context
        system_prompt = (
            "Bạn là Trợ lý Thư viện Nghiên cứu thông minh. "
            "Hãy trả lời câu hỏi của người dùng dựa trên các đoạn trích được cung cấp từ thư viện. "
            "Nếu thông tin không có trong các đoạn trích, hãy nói rõ. "
            "Sử dụng tiếng Việt và định dạng Markdown đẹp. "
            "Khi trích dẫn thông tin, hãy dùng [số] để tham chiếu nguồn (ví dụ: 'Theo nghiên cứu [1]...').\\n\\n"
            f"{context}"
        )
        
        messages = [{"role": "system", "content": system_prompt}]
        for msg in req.history:
            messages.append(msg)
        messages.append({"role": "user", "content": req.text})
        
        # 6. Get AI response
        response = client.chat.completions.create(
            model="qwen-plus",
            messages=messages
        )
        reply = response.choices[0].message.content
        
        # 7. Return answer with sources and confidence
        return {
            "reply": reply,
            "sources": sources,
            "confidence": confidence,
            "retrieved_count": len(relevant_highlights)
        }
        
    except Exception as e:
        print(f"Library Chat Error: {e}")
        import traceback
        traceback.print_exc()
        return JSONResponse(status_code=500, content={"message": str(e)})

@app.post("/api/semantic-search")
async def semantic_search_endpoint(req: SemanticSearchRequest):
    """Tìm kiếm tài liệu dựa trên ngữ nghĩa của câu hỏi"""
    client = get_ai_client()
    if not client:
        return JSONResponse(status_code=500, content={"message": "AI Client not initialized"})
        
    docs = get_local_docs()
    if not docs:
        return {"results": []}
        
    # Chuẩn bị danh sách tài liệu để AI phân tích
    lib_meta = []
    for d in docs:
        lib_meta.append({"id": d["id"], "name": d["filename"]})
        
    system_prompt = (
        "Bạn là một chuyên gia tìm kiếm tài liệu. Dưới đây là danh sách các tài liệu trong thư viện:\n"
        f"{json.dumps(lib_meta, ensure_ascii=False)}\n\n"
        "Người dùng đang tìm kiếm: '{query}'\n"
        "Hãy xác định những tài liệu nào CÓ KHẢ NĂNG LIÊN QUAN NHẤT đến ý nghĩa của câu hỏi này. "
        "Trả về kết quả dưới dạng JSON liệt kê các ID tài liệu và lý do ngắn gọn. "
        "Định dạng: {\"results\": [{\"id\": \"id1\", \"reason\": \"...\"}, ...]}"
    )
    
    try:
        response = client.chat.completions.create(
            model="qwen-plus",
            messages=[{"role": "user", "content": system_prompt.format(query=req.query)}]
        )
        content = response.choices[0].message.content
        # Extract JSON if AI surrounds it with markdown
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()
            
        return json.loads(content)
    except Exception as e:
        print(f"Semantic Search Error: {e}")
        # Fallback to simple name match if AI fails
        filtered = [d["id"] for d in docs if req.query.lower() in d["filename"].lower()]
        return {"results": [{"id": fid, "reason": "Khớp tên file"} for fid in filtered]}


# === HELPER FUNCTIONS FOR CONTENT SEARCH ===

def extract_snippet(content: str, query: str, context_chars: int = 100) -> str:
    """Extract a snippet around the first match"""
    idx = content.lower().find(query.lower())
    if idx == -1:
        return content[:200] + ("..." if len(content) > 200 else "")
    
    start = max(0, idx - context_chars)
    end = min(len(content), idx + len(query) + context_chars)
    
    snippet = content[start:end]
    if start > 0:
        snippet = "..." + snippet
    if end < len(content):
        snippet = snippet + "..."
    
    return snippet


def calculate_keyword_score(content: str, query: str) -> float:
    """Simple scoring based on occurrence frequency"""
    content_lower = content.lower()
    query_lower = query.lower()
    
    count = content_lower.count(query_lower)
    # Normalize: more occurrences = higher score, cap at 1.0
    score = min(1.0, count / 5)  # 5 occurrences = 100%
    
    # Bonus for exact phrase match
    if query_lower in content_lower:
        score = min(1.0, score + 0.2)
    
    return score


# === CONTENT SEARCH ENDPOINT ===

@app.get("/api/search-content")
async def search_content(
    query: str = Query(..., description="Search query"),
    mode: str = Query("hybrid", description="Search mode: keyword, semantic, or hybrid")
):
    """
    Search documents by content (highlights), not just titles.
    Supports keyword matching and semantic search.
    """
    try:
        highlights = get_local_highlights()
        docs = get_local_docs()
        results = []
        
        # 1. Keyword search in highlights
        if mode in ["keyword", "hybrid"]:
            for hl in highlights:
                content = hl.get('content', '')
                if query.lower() in content.lower():
                    results.append({
                        'doc_id': hl.get('doc_id', ''),
                        'highlight_id': hl.get('id', ''),
                        'snippet': extract_snippet(content, query),
                        'tag': hl.get('tag', ''),
                        'score': calculate_keyword_score(content, query),
                        'match_type': 'keyword'
                    })
        
        # 2. Semantic search using highlight embeddings (if available)
        if mode in ["semantic", "hybrid"]:
            # Check if highlight embeddings exist
            stats = highlight_emb_mgr.get_stats()
            if stats.get('total', 0) > 0:
                client = get_ai_client()
                if client:
                    semantic_results = await rag_retriever.search_highlights_by_query(
                        client,
                        query,
                        top_k=15,
                        min_similarity=0.4
                    )
                    
                    for sr in semantic_results:
                        # Avoid duplicates from keyword search
                        if not any(r['highlight_id'] == sr['highlight_id'] for r in results):
                            results.append({
                                'doc_id': sr['doc_id'],
                                'highlight_id': sr['highlight_id'],
                                'snippet': sr['content'][:200] + ("..." if len(sr['content']) > 200 else ""),
                                'tag': sr['tag'],
                                'score': sr['similarity'],
                                'match_type': 'semantic'
                            })
        
        # 3. Group by document and aggregate scores
        doc_scores = {}
        for r in results:
            doc_id = r['doc_id']
            if doc_id not in doc_scores:
                doc_scores[doc_id] = {
                    'doc_id': doc_id,
                    'max_score': 0,
                    'matches': [],
                    'total_matches': 0
                }
            
            doc_scores[doc_id]['matches'].append(r)
            doc_scores[doc_id]['max_score'] = max(doc_scores[doc_id]['max_score'], r['score'])
            doc_scores[doc_id]['total_matches'] += 1
        
        # 4. Sort by score and add document metadata
        ranked_docs = sorted(doc_scores.values(), key=lambda x: x['max_score'], reverse=True)
        
        for doc in ranked_docs:
            doc_meta = next((d for d in docs if d.get('id') == doc['doc_id']), None)
            if doc_meta:
                doc['doc_name'] = doc_meta.get('filename', 'Unknown')
                doc['doc_url'] = doc_meta.get('url', '')
        
        return {
            'query': query,
            'mode': mode,
            'total_documents': len(ranked_docs),
            'total_matches': sum(d['total_matches'] for d in ranked_docs),
            'results': ranked_docs[:20]  # Top 20 documents
        }
        
    except Exception as e:
        print(f"Content search error: {e}")
        import traceback
        traceback.print_exc()
        return JSONResponse(status_code=500, content={"message": str(e)})

@app.get("/api/export-report")
async def export_report(ids: str = Query(...)):
    """Xuất báo cáo so sánh ra file Word (.docx)"""
    doc_ids = ids.split(",")
    all_docs = get_local_docs()
    selected_docs = [d for d in all_docs if d["id"] in doc_ids]
    
    # Lấy dữ liệu matrix (tương tự endpoint /api/compare)
    highlights = []
    if os.path.exists("local_highlights.json"):
        with open("local_highlights.json", "r", encoding="utf-8") as f:
            highlights = json.load(f)
            
    matrix = {}
    tags_found = set()
    for doc in selected_docs:
        did = doc["id"]
        matrix[did] = {}
        doc_highlights = [h for h in highlights if h["doc_id"] == did]
        for h in doc_highlights:
            tag = h.get("tag", "Chưa phân loại").replace("Note: ", "").strip()
            if not tag: tag = "Chưa phân loại"
            tags_found.add(tag)
            if tag not in matrix[did]:
                matrix[did][tag] = []
            matrix[did][tag].append(h["content"])

    # Tạo file Word
    doc = Document()
    title = doc.add_heading('BÁO CÁO TỔNG HỢP & SO SÁNH TÀI LIỆU', 0)
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    
    doc.add_paragraph(f"Ngày tạo: {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    doc.add_paragraph(f"Số lượng tài liệu phân tích: {len(selected_docs)}")
    
    doc.add_heading('1. Danh sách tài liệu', level=1)
    for i, d in enumerate(selected_docs, 1):
        doc.add_paragraph(f"{i}. {d['filename']}", style='List Bullet')
        
    doc.add_heading('2. Ma trận So sánh', level=1)
    
    # Tạo bảng: Cột 1 là Tiêu chí (Tag), các cột sau là tài liệu
    table = doc.add_table(rows=1, cols=len(selected_docs) + 1)
    table.style = 'Table Grid'
    hdr_cells = table.rows[0].cells
    hdr_cells[0].text = 'Tiêu chí / Tài liệu'
    for i, d in enumerate(selected_docs):
        hdr_cells[i+1].text = d['filename']
        
    sorted_tags = sorted(list(tags_found))
    for tag in sorted_tags:
        row_cells = table.add_row().cells
        row_cells[0].text = tag
        for i, d in enumerate(selected_docs):
            content_list = matrix[d["id"]].get(tag, [])
            if content_list:
                row_cells[i+1].text = "\n".join([f"• {c}" for c in content_list])
            else:
                row_cells[i+1].text = "-"
                
    doc.add_paragraph("\n--- Kết thúc báo cáo ---")
    
    # Lưu vào buffer
    file_stream = io.BytesIO()
    doc.save(file_stream)
    file_stream.seek(0)
    
    return StreamingResponse(
        file_stream,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f"attachment; filename=Bao_cao_nghien_cuu_{datetime.now().strftime('%Y%m%d')}.docx"}
    )

@app.get("/api/knowledge-graph")
async def get_knowledge_graph(
    tags: Optional[str] = Query(None, description="Filter by tags (comma-separated)"),
    search: Optional[str] = Query(None, description="Search documents by name"),
    use_embeddings: bool = Query(True, description="Use AI embeddings for similarity"),
    similarity_threshold: float = Query(0.3, description="Minimum similarity (0-1) for embedding-based links")
):
    """
    Tạo dữ liệu cho sơ đồ tri thức với AI embeddings hoặc tag-based similarity.
    Embeddings provide semantic similarity, tags provide topic-based grouping.
    """
    # Check cache first (cache key includes use_embeddings and threshold)
    cache_key = f"emb_{use_embeddings}_th_{similarity_threshold}"
    current_time = time.time()
    
    if GRAPH_CACHE.get(cache_key) and (current_time - GRAPH_CACHE.get(f"{cache_key}_timestamp", 0)) < GRAPH_CACHE["ttl"]:
        cached_data = GRAPH_CACHE[cache_key]
    else:
        # Rebuild cache
        docs = get_local_docs()
        highlights = []
        if os.path.exists("local_highlights.json"):
            with open("local_highlights.json", "r", encoding="utf-8") as f:
                highlights = json.load(f)
        
        # Use optimized computation with inverted index (for tags)
        nodes, tag_links, indexer = optimize_graph_computation(docs, highlights)
        
        # Decide which links to use
        links = []
        
        if use_embeddings:
            # Use embedding-based similarity
            doc_ids = [d["id"] for d in docs]
            embedded_ids = set(embedding_mgr.get_all_embedded_docs())
            
            # Compute similarity matrix
            similarity_matrix = embedding_mgr.compute_similarity_matrix(doc_ids)
            
            # Create links based on similarity threshold
            for (doc1, doc2), similarity in similarity_matrix.items():
                if similarity >= similarity_threshold:
                    # Find common tags for additional context
                    tags1 = set(next((n["tags"] for n in nodes if n["id"] == doc1), []))
                    tags2 = set(next((n["tags"] for n in nodes if n["id"] == doc2), []))
                    common_tags = list(tags1.intersection(tags2))
                    
                    links.append({
                        "source": doc1,
                        "target": doc2,
                        "value": int(similarity * 10),  # Scale to 1-10
                        "similarity": float(similarity),
                        "common_tags": common_tags,
                        "type": "embedding"
                    })
            
            # Add metadata about embedding coverage
            embedding_coverage = len(embedded_ids) / len(docs) if docs else 0
        else:
            # Fall back to tag-based links
            links = tag_links
            for link in links:
                link["type"] = "tag"
            embedding_coverage = 0
        
        # Compute clusters
        clusterer = TagClusterer(indexer)
        clusters = clusterer.cluster_by_dominant_tag(nodes)
        
        # Compute metrics
        analyzer = GraphAnalyzer(nodes, links)
        pagerank = analyzer.compute_pagerank()
        centrality = analyzer.compute_centrality_metrics()
        density = analyzer.compute_network_density()
        top_nodes = analyzer.get_top_connected_nodes(n=5)
        
        cached_data = {
            "nodes": nodes,
            "links": links,
            "clusters": clusters,
            "metrics": {
                "pagerank": pagerank,
                "degree": centrality["degree"],
                "betweenness": centrality["betweenness"],
                "closeness": centrality["closeness"],
                "density": density,
                "top_connected": [{"id": nid, "degree": deg} for nid, deg in top_nodes]
            },
            "all_tags": indexer.get_all_tags(),
            "embedding_coverage": embedding_coverage if use_embeddings else None,
            "similarity_mode": "embedding" if use_embeddings else "tag"
        }
        
        # Update cache
        GRAPH_CACHE[cache_key] = cached_data
        GRAPH_CACHE[f"{cache_key}_timestamp"] = current_time
    
    # Apply filters if provided
    filtered_data = cached_data.copy()
    
    if tags:
        tag_list = [t.strip() for t in tags.split(",")]
        filtered_nodes = [n for n in cached_data["nodes"] if any(tag in n["tags"] for tag in tag_list)]
        filtered_node_ids = {n["id"] for n in filtered_nodes}
        filtered_links = [l for l in cached_data["links"] if l["source"] in filtered_node_ids and l["target"] in filtered_node_ids]
        filtered_data["nodes"] = filtered_nodes
        filtered_data["links"] = filtered_links
    
    if search:
        search_lower = search.lower()
        filtered_nodes = [n for n in filtered_data["nodes"] if search_lower in n["name"].lower()]
        filtered_node_ids = {n["id"] for n in filtered_nodes}
        filtered_links = [l for l in filtered_data["links"] if l["source"] in filtered_node_ids and l["target"] in filtered_node_ids]
        filtered_data["nodes"] = filtered_nodes
        filtered_data["links"] = filtered_links
    
    return filtered_data

@app.get("/api/embeddings/status")
async def get_embedding_status():
    """
    Get status of embeddings: how many docs have embeddings, coverage, etc.
    """
    docs = get_local_docs()
    total_docs = len(docs)
    embedded_docs = embedding_mgr.get_all_embedded_docs()
    embedded_count = len(embedded_docs)
    
    stats = embedding_mgr.get_embedding_stats()
    
    # Find docs that need embedding
    highlights = []
    if os.path.exists("local_highlights.json"):
        with open("local_highlights.json", "r", encoding="utf-8") as f:
            highlights = json.load(f)
    
    needs_embedding = []
    for doc in docs:
        doc_id = doc["id"]
        doc_highlights = get_highlights_for_doc(doc_id, highlights)
        if doc_highlights and embedding_mgr.needs_embedding(doc_id, doc_highlights):
            needs_embedding.append({"id": doc_id, "name": doc["filename"]})
    
    return {
        "total_documents": total_docs,
        "embedded_documents": embedded_count,
        "coverage_percent": (embedded_count / total_docs * 100) if total_docs > 0 else 0,
        "needs_embedding": needs_embedding,
        "needs_embedding_count": len(needs_embedding),
        "stats": stats
    }

@app.post("/api/embeddings/generate")
async def generate_embeddings_endpoint(
    force: bool = Query(False, description="Force regenerate all embeddings")
):
    """
    Generate embeddings for all documents (or regenerate if force=true).
    """
    client = get_ai_client()
    if not client:
        return JSONResponse(
            status_code=500, 
            content={"error": "AI client not configured. Set DASHSCOPE_API_KEY."}
        )
    
    docs = get_local_docs()
    highlights = []
    if os.path.exists("local_highlights.json"):
        with open("local_highlights.json", "r", encoding="utf-8") as f:
            highlights = json.load(f)
    
    result = await generate_embeddings_batch(
        client, 
        docs, 
        highlights, 
        embedding_mgr, 
        force=force
    )
    
    # Invalidate graph cache since embeddings changed
    invalidate_graph_cache()
    
    return {
        "status": "success",
        **result
    }

@app.get("/api/knowledge-graph/metrics")
async def get_graph_metrics():
    """
    Get pre-computed graph metrics including PageRank and centrality measures.
    """
    # Ensure cache is populated
    data = await get_knowledge_graph()
    
    return {
        "metrics": data.get("metrics", {}),
        "clusters": data.get("clusters", []),
        "total_nodes": len(data.get("nodes", [])),
        "total_links": len(data.get("links", [])),
        "embedding_coverage": data.get("embedding_coverage"),
        "similarity_mode": data.get("similarity_mode")
    }

@app.get("/api/knowledge-graph/path")
async def find_node_path(
    source: str = Query(..., description="Source document ID"),
    target: str = Query(..., description="Target document ID")
):
    """
    Find shortest path between two documents in the knowledge graph.
    """
    # Ensure cache is populated
    data = await get_knowledge_graph()
    
    nodes = data.get("nodes", [])
    links = data.get("links", [])
    
    if not nodes or not links:
        return {"error": "No graph data available"}
    
    analyzer = GraphAnalyzer(nodes, links)
    path = analyzer.find_shortest_path(source, target)
    
    if path:
        # Get document names for the path
        path_with_names = []
        for node_id in path:
            node = next((n for n in nodes if n["id"] == node_id), None)
            if node:
                path_with_names.append({"id": node_id, "name": node["name"]})
        
        return {
            "path": path,
            "path_with_names": path_with_names,
            "length": len(path) - 1
        }
    else:
        return {
            "path": None,
            "message": "No path found between these documents"
        }

@app.get("/api/knowledge-graph/search")
async def search_graph(
    query: str = Query(..., description="Search query")
):
    """
    Search for documents in the knowledge graph by name or tags.
    """
    # Ensure cache is populated
    data = await get_knowledge_graph()
    
    nodes = data.get("nodes", [])
    if not nodes:
        return {"results": []}
    
    query_lower = query.lower()
    
    results = []
    for node in nodes:
        # Search in name
        if query_lower in node["name"].lower():
            results.append({
                "id": node["id"],
                "name": node["name"],
                "match_type": "name",
                "tags": node["tags"]
            })
        # Search in tags
        elif any(query_lower in tag.lower() for tag in node["tags"]):
            matching_tags = [tag for tag in node["tags"] if query_lower in tag.lower()]
            results.append({
                "id": node["id"],
                "name": node["name"],
                "match_type": "tags",
                "matching_tags": matching_tags,
                "tags": node["tags"]
            })
    
    return {"results": results, "count": len(results)}

@app.post("/api/save-highlight")
async def save_highlight(data: HighlightRequest):
    """Lưu highlight vào Firestore hoặc máy cục bộ"""
    try:
        highlight_data = {
            "doc_id": data.doc_id,
            "content": data.content,
            "tag": data.tag,
            "color": data.color,
            "created_at": datetime.now().isoformat()
        }
        
        if db:
            try:
                firestore_data = highlight_data.copy()
                firestore_data["created_at"] = datetime.now()
                db.collection('highlights').add(firestore_data)
            except Exception as e:
                print(f"Firestore highlight save failed, using local: {e}")
                save_local_highlight(highlight_data)
        else:
            save_local_highlight(highlight_data)
        
        # Invalidate embedding for this document (needs regeneration)
        embedding_mgr.invalidate_embedding(data.doc_id)
        
        # Invalidate graph cache since highlights changed
        invalidate_graph_cache()
            
        return {"status": "success"}
    except Exception as e:
        return JSONResponse(status_code=500, content={"message": str(e)})

@app.get("/api/get-highlights")
async def get_all_highlights(doc_id: str):
    """Lấy highlights của 1 doc cụ thể"""
    results = []
    if db:
        try:
            hs = db.collection('highlights').where('doc_id', '==', doc_id).stream()
            results = [{"id": h.id, **h.to_dict()} for h in hs]
        except Exception as e:
            print(f"Firestore get highlights failed: {e}")
    
    # Merge with local
    local_hs = get_local_highlights(doc_id)
    results.extend(local_hs)
    
    return results

@app.post("/api/ai-chat")
async def ai_chat(req: ChatRequest):
    """Xử lý yêu cầu AI với Qianwen (hỗ trợ đối thoại)"""
    client = get_ai_client()
    if not client:
        return JSONResponse(status_code=500, content={"message": "Chưa cấu hình DASHSCOPE_API_KEY"})
    
    try:
        messages = []
        system_prompt = "Bạn là một trợ lý nghiên cứu khoa học tận tâm. Hãy trả lời bằng tiếng Việt, định dạng Markdown rõ ràng."
        
        if req.action == "summarize":
            if req.context:
                # Limit context to avoid exceeding token limits, 15000 characters is a rough estimate
                system_prompt += f"\nDưới đây là toàn bộ nội dung của tài liệu:\n{req.context[:15000]}\n\nHãy đọc kỹ và tóm tắt các ý chính (Mục tiêu, Phương pháp, Kết quả, Kết luận) của tài liệu này."
            else:
                system_prompt += "\nHãy tóm tắt nội dung chính của tài liệu này dựa trên các trao đổi trước đó."
        elif req.action == "explain":
            system_prompt += "\nHãy giải thích đoạn văn sau một cách dễ hiểu, đặt trong ngữ cảnh nghiên cứu khoa học."
        elif req.action == "translate":
            system_prompt += "\nHãy dịch đoạn văn sau sang tiếng Việt mượt mà, chuyên nghiệp."

        messages.append({"role": "system", "content": system_prompt})
        
        # Add history if available
        for msg in req.history:
            messages.append(msg)
            
        # Add current user message
        messages.append({"role": "user", "content": req.text})
        
        response = client.chat.completions.create(
            model="qwen-plus",
            messages=messages
        )
        reply = response.choices[0].message.content
        
        # Save to local knowledge base (don't let this block the response)
        try:
            save_local_chat({
                "query": req.text,
                "reply": reply,
                "action": req.action
            })
        except Exception as save_err:
            print(f"Warning: Failed to save chat history: {save_err}")
        
        return {"reply": reply}
    except Exception as e:
        return JSONResponse(status_code=500, content={"message": str(e)})

@app.get("/api/recollect")
async def recollect(text: str = Query(...)):
    """Tìm kiếm nội dung liên quan trong quá khứ (Fuzzy search đơn giản)"""
    text = text.lower().strip()
    if len(text) < 3: return []
    
    matches = []
    
    # Check Highlights
    hs = get_local_highlights()
    for h in hs:
        content = h.get('content', '').lower()
        if text in content or content in text:
            matches.append({
                "type": "note",
                "content": h.get('content'),
                "tag": h.get('tag'),
                "doc_id": h.get('doc_id')
            })
            if len(matches) > 3: break
            
    # Check Chat History
    chats = get_local_chat()
    for c in chats:
        query = c.get('query', '').lower()
        reply = c.get('reply', '').lower()
        if text in query or text in reply:
            matches.append({
                "type": "chat",
                "query": c.get('query'),
                "reply": c.get('reply')[:100] + "..." if len(c.get('reply', '')) > 100 else c.get('reply')
            })
            if len(matches) > 5: break
            
    return matches

@app.post("/api/synthesize-knowledge")
async def synthesize_knowledge(payload: dict):
    """Sử dụng AI để kết nối kiến thức cũ và nội dung hiện tại"""
    client = get_ai_client()
    if not client:
        return JSONResponse(status_code=500, content={"message": "Chưa cấu hình API Key"})
    
    try:
        current_text = payload.get("current_text", "")
        past_knowledge = payload.get("past_knowledge", "") # Chuỗi mô tả các note/chat cũ
        
        prompt = f"""
Bạn là một trợ lý nghiên cứu có trí nhớ siêu việt. 
Hãy giúp tôi kết nối nội dung tôi ĐANG ĐỌC với KIẾN THỨC CŨ tôi đã từng lưu lại.

[NỘI DUNG ĐANG ĐỌC]:
"{current_text}"

[KIẾN THỨC CŨ TRONG QUÁ KHỨ]:
{past_knowledge}

Hãy viết một bản tổng hợp ngắn gọn (khoảng 3-4 câu) trong một ô nhỏ, giải thích:
1. Sự liên quan giữa hai nội dung này là gì?
2. Kiến thức cũ giúp gì cho việc hiểu nội dung mới này?
3. Có điểm gì mâu thuẫn hoặc bổ sung cho nhau không?

Yêu cầu: Viết giọng văn hỗ trợ, súc tích, trình bày rõ ràng.
"""
        
        response = client.chat.completions.create(
            model="qwen-plus",
            messages=[
                {"role": "system", "content": "You are a helpful research assistant specializing in knowledge synthesis."},
                {"role": "user", "content": prompt}
            ]
        )
        return {"synthesis": response.choices[0].message.content}
    except Exception as e:
        return JSONResponse(status_code=500, content={"message": str(e)})

@app.post("/api/compare")
async def get_comparison_data(payload: CompareRequest):
    """Lấy dữ liệu highlights cho ma trận so sánh (Hỗ trợ Firestore + Local)"""
    try:
        doc_ids = payload.doc_ids
        if not doc_ids:
            return {"documents": [], "matrix": {}, "tags": []}

        docs_data = []
        matrix = {}
        
        # 1. Lấy thông tin Documents
        # Từ Firestore
        if db:
            try:
                for doc_id in doc_ids:
                    if doc_id.startswith("local_"): continue # Bỏ qua IDs local khi check Firestore
                    d = db.collection('documents').document(doc_id).get()
                    if d.exists:
                        data = d.to_dict()
                        data['id'] = d.id
                        docs_data.append(data)
            except Exception as e:
                print(f"Firestore docs fetch failed: {e}")

        # Từ Local
        local_docs = get_local_docs()
        for ld in local_docs:
            if ld['id'] in doc_ids and not any(d['id'] == ld['id'] for d in docs_data):
                docs_data.append(ld)

        # 2. Lấy Highlights và xây dựng Matrix
        matrix = {d['id']: {} for d in docs_data}
        
        # Từ Firestore
        if db:
            try:
                # Firestore 'in' query supports up to 10 items
                remote_ids = [did for did in doc_ids if not did.startswith("local_")]
                if remote_ids:
                    highlights_ref = db.collection('highlights').where('doc_id', 'in', remote_ids).stream()
                    for h in highlights_ref:
                        h_data = h.to_dict()
                        d_id = h_data['doc_id']
                        tag = h_data['tag']
                        content = h_data['content']
                        if d_id in matrix:
                            if tag not in matrix[d_id]: matrix[d_id][tag] = []
                            matrix[d_id][tag].append(content)
            except Exception as e:
                print(f"Firestore highlights fetch failed: {e}")

        # Từ Local
        all_local_hs = get_local_highlights()
        for h in all_local_hs:
            d_id = h.get('doc_id')
            tag = h.get('tag')
            content = h.get('content')
            if d_id in doc_ids and d_id in matrix:
                if tag not in matrix[d_id]: matrix[d_id][tag] = []
                # Tránh trùng lặp nếu đã có từ Firestore (hiếm nhưng vẫn check)
                if content not in matrix[d_id][tag]:
                    matrix[d_id][tag].append(content)

        return {
            "documents": docs_data,
            "matrix": matrix,
            "tags": ["Tiêu đề", "MỤC TIÊU", "NGHIÊN CỨU", "VẬT LIỆU", "PHƯƠNG PHÁP", "KẾT QUẢ", "KẾT LUẬN", "Hạn chế"]
        }
    except Exception as e:
        print(f"Comparison Matrix Error: {e}")
        return JSONResponse(status_code=500, content={"message": str(e)})

@app.delete("/api/delete-doc/")
async def delete_document_missing_id():
    raise HTTPException(status_code=400, detail="Thiếu ID tài liệu để xóa.")

@app.delete("/api/delete-doc/{doc_id}")
async def delete_document(doc_id: str):
    """Xóa tài liệu và toàn bộ dữ liệu liên quan"""
    print(f"DEBUG: Attempting to delete doc_id: {doc_id}")
    try:
        # 1. Xóa khỏi Firestore (nếu có)
        if db:
            try:
                print(f"DEBUG: Deleting from Firestore...")
                # Xóa document
                db.collection('documents').document(doc_id).delete()
                # Xóa highlights liên quan
                print(f"DEBUG: Deleting highlights for {doc_id}...")
                hs = list(db.collection('highlights').where('doc_id', '==', doc_id).stream())
                for h in hs:
                    h.reference.delete()
                print(f"DEBUG: Firestore cleanup done.")
            except Exception as e:
                print(f"DEBUG: Firestore delete failed: {e}")

        # 2. Xóa khỏi Local Storage
        print(f"DEBUG: Deleting from Local Storage...")
        # Metadata
        docs = get_local_docs()
        doc_to_delete = next((d for d in docs if d['id'] == doc_id), None)
        if doc_to_delete:
            print(f"DEBUG: Found in local metadata. Removing...")
            new_docs = [d for d in docs if d['id'] != doc_id]
            with open(LOCAL_DB_FILE, "w") as f:
                json.dump(new_docs, f, ensure_ascii=False, indent=2)
            
            # Xóa file vật lý nếu là local upload
            if doc_to_delete.get('url', '').startswith('/static/uploads/'):
                filename = doc_to_delete['url'].split('/')[-1]
                file_path = os.path.join("static", "uploads", filename)
                if os.path.exists(file_path):
                    print(f"DEBUG: Removing physical file: {file_path}")
                    os.remove(file_path)
                else:
                    print(f"DEBUG: Physical file not found at {file_path}")

        # Highlights
        try:
            if os.path.exists(LOCAL_HIGHLIGHTS_FILE):
                print(f"DEBUG: Cleaning local highlights...")
                with open(LOCAL_HIGHLIGHTS_FILE, "r") as f:
                    hs = json.load(f)
                new_hs = [h for h in hs if h.get('doc_id') != doc_id]
                with open(LOCAL_HIGHLIGHTS_FILE, "w") as f:
                    json.dump(new_hs, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"DEBUG: Local highlight cleanup failed: {e}")

        print(f"DEBUG: Deletion successful for {doc_id}")
        return {"status": "success", "message": f"Đã xóa tài liệu {doc_id} thành công"}
    except Exception as e:
        print(f"DEBUG: Delete crashed: {e}")
        return JSONResponse(status_code=500, content={"message": f"Server Error (API): {str(e)}"})

if __name__ == "__main__":
    import uvicorn
    # Create static dir if not exists
    if not os.path.exists("static"):
        os.makedirs("static")
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
