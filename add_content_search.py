#!/usr/bin/env python3
"""
Add content search endpoint to main.py
Run from research-assistant directory: python add_content_search.py
"""

import re


def add_content_search_to_main():
    """Add content search helper functions and endpoint to main.py"""
    
    with open('main.py', 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Check if already added
    if 'search-content' in content or 'extract_snippet' in content:
        print("ℹ️  Content search already exists in main.py")
        return True
    
    # Find where to insert (after semantic-search endpoint, before export-report)
    pattern = r'(@app\.get\("/api/export-report"\))'
    
    content_search_code = '''
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

'''
    
    # Insert before export-report endpoint
    new_content = re.sub(pattern, content_search_code + r'\1', content)
    
    if new_content == content:
        print("❌ Could not find insertion point!")
        return False
    
    with open('main.py', 'w', encoding='utf-8') as f:
        f.write(new_content)
    
    print("✅ Added content search endpoint to main.py!")
    return True


if __name__ == "__main__":
    print("🔧 Adding content search to main.py...")
    print("=" * 50)
    
    success = add_content_search_to_main()
    
    print("=" * 50)
    if success:
        print("🎉 Content search endpoint added successfully!")
        print("\n📝 Next steps:")
        print("  1. Update frontend in index.html")
        print("  2. Test: /api/search-content?query=test&mode=hybrid")
    else:
        print("⚠️  Failed to add content search")
