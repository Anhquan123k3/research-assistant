"""
NEW RAG LIBRARY CHAT ENDPOINTS
Copy this content to main.py to replace the broken library_chat_endpoint function (lines 299-353)
"""

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


# === ENHANCED LIBRARY CHAT WITH RAG ===

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
