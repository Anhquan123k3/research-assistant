#!/usr/bin/env python3
"""
Fix script for main.py - repairs broken library_chat_endpoint that has merge conflicts
Run this from the research-assistant directory: python fix_main_py.py
"""

import re


def fix_main_py():
    """Fix the broken library_chat_endpoint in main.py"""
    
    with open('main.py', 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Find the broken endpoint (starts at line 299, ends at line 353)
    # Pattern: Find @app.post("/api/library-chat") ... up to @app.post("/api/semantic-search")
    pattern = r'@app\.post\("/api/library-chat"\).*?(?=@app\.post\("/api/semantic-search"\))'
    
    # Replacement code
    replacement = '''@app.post("/api/library-chat")
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

'''
    
    # Replace
    new_content = re.sub(pattern, replacement, content, flags=re.DOTALL)
    
    # Check if replacement happened
    if new_content == content:
        print("❌ No changes made - pattern not found!")
        print("Trying alternative fix method...")
        
        # Alternative: find exact line numbers
        lines = content.split('\n')
        
        # Find @app.post("/api/library-chat")
        start_idx = None
        for i, line in enumerate(lines):
            if '@app.post("/api/library-chat")' in line:
                start_idx = i
                break
        
        if start_idx is None:
            print("❌ Could not find library-chat endpoint!")
            return False
        
        # Find @app.post("/api/semantic-search")
        end_idx = None
        for i in range(start_idx + 1, len(lines)):
            if '@app.post("/api/semantic-search")' in lines[i]:
                end_idx = i
                break
        
        if end_idx is None:
            print("❌ Could not find semantic-search endpoint!")
            return False
        
        print(f"Found broken code from line {start_idx + 1} to line {end_idx}")
        
        # Replace lines
        new_lines = lines[:start_idx] + replacement.split('\n') + lines[end_idx:]
        new_content = '\n'.join(new_lines)
    
    # Write fixed file
    with open('main.py', 'w', encoding='utf-8') as f:
        f.write(new_content)
    
    print("✅ Successfully fixed main.py!")
    print("✅ library_chat_endpoint now uses RAG")
    return True


def add_new_endpoints():
    """Add new highlight embedding endpoints to main.py""" 
    
    with open('main.py', 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Check if endpoints already exist
    if '/api/highlight-embeddings/status' in content:
        print("ℹ️  Highlight embedding endpoints already exist")
        return True
    
    # Find where to insert (before @app.post("/api/library-chat"))
    pattern = r'(@app\.post\("/api/library-chat"\))'
    
    new_endpoints = '''# === HIGHLIGHT EMBEDDING ENDPOINTS ===

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


'''
    
    # Insert before library-chat endpoint
    new_content = re.sub(pattern, new_endpoints + r'\1', content)
    
    if new_content == content:
        print("❌ Could not insert new endpoints - pattern not found!")
        return False
    
    with open('main.py', 'w', encoding='utf-8') as f:
        f.write(new_content)
    
    print("✅ Successfully added highlight embedding endpoints!")
    return True


if __name__ == "__main__":
    print("🔧 Fixing main.py...")
    print("=" * 50)
    
    success1 = fix_main_py()
    print()
    success2 = add_new_endpoints()
    
    print()
    print("=" * 50)
    if success1 and success2:
        print("🎉 All fixes applied successfully!")
        print("📝 Next steps:")
        print("  1. Test the API: python main.py")
        print("  2. Generate highlight embeddings via UI")
        print("  3. Try asking library assistant questions")
    else:
        print("⚠️  Some fixes failed - please review manually")
