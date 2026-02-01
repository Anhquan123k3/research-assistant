"""
RAG Retrieval System for Library Assistant
Provides semantic search over highlights for intelligent Q&A
"""

import json
import os
from typing import List, Dict, Optional
from embedding_manager import HighlightEmbeddingManager, generate_embedding_from_ai


class RAGRetriever:
    """Retrieval-Augmented Generation system for library chat."""
    
    def __init__(self, highlight_emb_mgr: HighlightEmbeddingManager):
        self.highlight_emb_mgr = highlight_emb_mgr
        self.highlights_file = "local_highlights.json"
        self.docs_file = "local_metadata.json"
    
    def _load_highlights(self) -> List[dict]:
        """Load all highlights from storage."""
        if os.path.exists(self.highlights_file):
            with open(self.highlights_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        return []
    
    def _load_docs(self) -> List[dict]:
        """Load all documents metadata."""
        if os.path.exists(self.docs_file):
            with open(self.docs_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        return []
    
    def _get_doc_name(self, doc_id: str) -> str:
        """Get document filename by ID."""
        docs = self._load_docs()
        for doc in docs:
            if doc.get('id') == doc_id:
                return doc.get('filename', doc_id)
        return doc_id
    
    async def search_highlights_by_query(
        self,
        client,
        query: str,
        top_k: int = 10,
        min_similarity: float = 0.3
    ) -> List[dict]:
        """
        Search highlights semantically relevant to the query.
        
        Args:
            client: AI client for embedding generation
            query: User's question
            top_k: Number of results to return
            min_similarity: Minimum similarity threshold
            
        Returns:
            List of relevant highlights with metadata
        """
        # Generate embedding for the query
        query_embedding = await generate_embedding_from_ai(client, [{'content': query}])
        
        if not query_embedding:
            return []
        
        # Search highlights
        results = self.highlight_emb_mgr.search_by_similarity(
            query_embedding,
            top_k=top_k,
            min_similarity=min_similarity
        )
        
        # Enrich with document names
        for result in results:
            result['doc_name'] = self._get_doc_name(result['doc_id'])
        
        return results
    
    def build_rag_context(self, retrieved_highlights: List[dict]) -> str:
        """
        Build formatted context from retrieved highlights for AI.
        
        Args:
            retrieved_highlights: List of highlights from search
            
        Returns:
            Formatted string to use as context in AI prompt
        """
        if not retrieved_highlights:
            return "No relevant information found in your library."
        
        context = "RELEVANT PASSAGES FROM YOUR LIBRARY:\n\n"
        
        for idx, highlight in enumerate(retrieved_highlights, 1):
            context += f"[{idx}] From \"{highlight['doc_name']}\" (Tag: {highlight['tag']})\n"
            context += f"{highlight['content']}\n\n"
        
        return context
    
    def format_sources(self, retrieved_highlights: List[dict], max_sources: int = 5) -> List[dict]:
        """
        Format highlights as source citations for the response.
        
        Args:
            retrieved_highlights: List of highlights from search
            max_sources: Maximum number of sources to include
            
        Returns:
            List of formatted source dictionaries
        """
        sources = []
        
        for highlight in retrieved_highlights[:max_sources]:
            # Truncate content for preview
            content_preview = highlight['content']
            if len(content_preview) > 200:
                content_preview = content_preview[:197] + "..."
            
            sources.append({
                'highlight_id': highlight['highlight_id'],
                'doc_id': highlight['doc_id'],
                'doc_name': highlight['doc_name'],
                'tag': highlight['tag'],
                'content_preview': content_preview,
                'similarity': round(highlight['similarity'] * 100, 1),  # Convert to percentage
                'full_content': highlight['content']  # For expansion
            })
        
        return sources
    
    def get_confidence_level(self, retrieved_highlights: List[dict]) -> dict:
        """
        Determine confidence level based on retrieval results.
        
        Returns:
            {
                'level': 'high'|'medium'|'low',
                'color': 'green'|'yellow'|'red',
                'icon': emoji,
                'message': explanation
            }
        """
        if not retrieved_highlights:
            return {
                'level': 'none',
                'color': 'gray',
                'icon': '❓',
                'message': 'No relevant information found in your library.'
            }
        
        top_similarity = retrieved_highlights[0]['similarity'] if retrieved_highlights else 0
        count = len(retrieved_highlights)
        
        if count >= 3 and top_similarity >= 0.8:
            return {
                'level': 'high',
                'color': 'green',
                'icon': '🟢',
                'message': f'High confidence - Found {count} highly relevant passages.'
            }
        elif count >= 2 and top_similarity >= 0.6:
            return {
                'level': 'medium',
                'color': 'yellow',
                'icon': '🟡',
                'message': f'Medium confidence - Found {count} somewhat relevant passages.'
            }
        else:
            return {
                'level': 'low',
                'color': 'red',
                'icon': '🔴',
                'message': f'Low confidence - Found only {count} weakly relevant passage(s).'
            }


async def generate_highlight_embeddings_batch(
    client,
    highlights: List[dict],
    highlight_emb_mgr: HighlightEmbeddingManager,
    force: bool = False
) -> dict:
    """
    Generate embeddings for multiple highlights in batch.
    
    Args:
        client: AI client
        highlights: List of highlight dictionaries  
        highlight_emb_mgr: HighlightEmbeddingManager instance
        force: Force regeneration even if exists
        
    Returns:
        Status dictionary with counts
    """
    generated = 0
    skipped = 0
    failed = 0
    
    for highlight in highlights:
        highlight_id = highlight.get('id', '')
        content = highlight.get('content', '')
        
        if not highlight_id or not content:
            skipped += 1
            continue
        
        # Skip if already has valid embedding
        if not force and not highlight_emb_mgr.needs_embedding(highlight_id, content):
            skipped += 1
            continue
        
        # Generate embedding
        embedding = await generate_embedding_from_ai(client, [{'content': content}])
        
        if embedding:
            highlight_emb_mgr.save_highlight_embedding(highlight_id, highlight, embedding)
            generated += 1
        else:
            failed += 1
    
    return {
        'total': len(highlights),
        'generated': generated,
        'skipped': skipped,
        'failed': failed
    }
