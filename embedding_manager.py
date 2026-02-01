"""
Embedding Manager for AI-powered Semantic Similarity
Manages document embeddings using Qianwen AI embeddings API.
"""

import json
import os
import hashlib
from typing import Dict, List, Optional, Tuple
from datetime import datetime
import numpy as np


class EmbeddingManager:
    """Manages AI embeddings for documents with local caching."""
    
    def __init__(self, storage_file: str = "local_embeddings.json"):
        self.storage_file = storage_file
        self.embeddings: Dict[str, dict] = {}
        self._load_embeddings()
    
    def _load_embeddings(self):
        """Load embeddings from storage file."""
        if os.path.exists(self.storage_file):
            try:
                with open(self.storage_file, 'r', encoding='utf-8') as f:
                    self.embeddings = json.load(f)
            except Exception as e:
                print(f"Failed to load embeddings: {e}")
                self.embeddings = {}
        else:
            self.embeddings = {}
    
    def _save_embeddings(self):
        """Save embeddings to storage file."""
        try:
            with open(self.storage_file, 'w', encoding='utf-8') as f:
                json.dump(self.embeddings, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"Failed to save embeddings: {e}")
    
    def _compute_content_hash(self, highlights: List[dict]) -> str:
        """Compute hash of highlight contents to detect changes."""
        content = ''.join(sorted([h.get('content', '') for h in highlights]))
        return hashlib.md5(content.encode()).hexdigest()
    
    def needs_embedding(self, doc_id: str, highlights: List[dict]) -> bool:
        """Check if document needs (re-)embedding."""
        if doc_id not in self.embeddings:
            return True
        
        current_hash = self._compute_content_hash(highlights)
        stored_hash = self.embeddings[doc_id].get('highlights_hash', '')
        
        return current_hash != stored_hash
    
    def save_embedding(self, doc_id: str, embedding: List[float], highlights: List[dict]):
        """Save embedding for a document."""
        self.embeddings[doc_id] = {
            'embedding': embedding,
            'highlights_hash': self._compute_content_hash(highlights),
            'updated_at': datetime.now().isoformat(),
            'dimension': len(embedding)
        }
        self._save_embeddings()
    
    def get_embedding(self, doc_id: str) -> Optional[List[float]]:
        """Get embedding for a document."""
        if doc_id in self.embeddings:
            return self.embeddings[doc_id]['embedding']
        return None
    
    def invalidate_embedding(self, doc_id: str):
        """Remove embedding for a document (force regeneration)."""
        if doc_id in self.embeddings:
            del self.embeddings[doc_id]
            self._save_embeddings()
    
    def get_all_embedded_docs(self) -> List[str]:
        """Get list of all document IDs with embeddings."""
        return list(self.embeddings.keys())
    
    def get_embedding_stats(self) -> dict:
        """Get statistics about stored embeddings."""
        total = len(self.embeddings)
        if total == 0:
            return {
                'total': 0,
                'avg_dimension': 0,
                'oldest': None,
                'newest': None
            }
        
        dimensions = [e['dimension'] for e in self.embeddings.values()]
        dates = [e['updated_at'] for e in self.embeddings.values()]
        
        return {
            'total': total,
            'avg_dimension': sum(dimensions) / len(dimensions),
            'oldest': min(dates),
            'newest': max(dates)
        }
    
    @staticmethod
    def cosine_similarity(emb1: List[float], emb2: List[float]) -> float:
        """Compute cosine similarity between two embeddings."""
        arr1 = np.array(emb1)
        arr2 = np.array(emb2)
        
        dot_product = np.dot(arr1, arr2)
        norm1 = np.linalg.norm(arr1)
        norm2 = np.linalg.norm(arr2)
        
        if norm1 == 0 or norm2 == 0:
            return 0.0
        
        return float(dot_product / (norm1 * norm2))
    
    def compute_similarity_matrix(self, doc_ids: List[str]) -> Dict[Tuple[str, str], float]:
        """
        Compute similarity matrix for a list of documents.
        
        Returns:
            Dictionary mapping (doc1, doc2) tuples to similarity scores
        """
        similarity_matrix = {}
        
        for i, doc1 in enumerate(doc_ids):
            emb1 = self.get_embedding(doc1)
            if not emb1:
                continue
                
            for doc2 in doc_ids[i+1:]:
                emb2 = self.get_embedding(doc2)
                if not emb2:
                    continue
                
                similarity = self.cosine_similarity(emb1, emb2)
                similarity_matrix[(doc1, doc2)] = similarity
                similarity_matrix[(doc2, doc1)] = similarity  # Symmetric
        
        return similarity_matrix


async def generate_embedding_from_ai(client, highlights: List[dict]) -> Optional[List[float]]:
    """
    Generate embedding vector using AI from highlights.
    
    Args:
        client: OpenAI client instance
        highlights: List of highlight dictionaries
        
    Returns:
        Embedding vector or None if failed
    """
    if not client or not highlights:
        return None
    
    try:
        # Combine highlight content into single text
        text = ' '.join([h.get('content', '') for h in highlights])
        
        # Limit text length (embeddings have token limits)
        max_chars = 8000  # Safe limit for most embedding models
        if len(text) > max_chars:
            text = text[:max_chars]
        
        # Call AI embedding API
        response = client.embeddings.create(
            model="text-embedding-v3",
            input=text
        )
        
        embedding = response.data[0].embedding
        return embedding
        
    except Exception as e:
        print(f"Failed to generate embedding: {e}")
        return None


class HighlightEmbeddingManager:
    """Manages embeddings for individual highlights (for RAG/semantic search)."""
    
    def __init__(self, storage_file: str = "local_highlight_embeddings.json"):
        self.storage_file = storage_file
        self.embeddings: Dict[str, dict] = {}
        self._load_embeddings()
    
    def _load_embeddings(self):
        """Load highlight embeddings from storage."""
        if os.path.exists(self.storage_file):
            try:
                with open(self.storage_file, 'r', encoding='utf-8') as f:
                    self.embeddings = json.load(f)
            except Exception as e:
                print(f"Failed to load highlight embeddings: {e}")
                self.embeddings = {}
        else:
            self.embeddings = {}
    
    def _save_embeddings(self):
        """Save highlight embeddings to storage."""
        try:
            with open(self.storage_file, 'w', encoding='utf-8') as f:
                json.dump(self.embeddings, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"Failed to save highlight embeddings: {e}")
    
    def _compute_content_hash(self, content: str) -> str:
        """Compute hash of highlight content."""
        return hashlib.md5(content.encode()).hexdigest()
    
    def save_highlight_embedding(self, highlight_id: str, highlight_data: dict, embedding: List[float]):
        """Save embedding for a highlight."""
        self.embeddings[highlight_id] = {
            'embedding': embedding,
            'content': highlight_data.get('content', ''),
            'doc_id': highlight_data.get('doc_id', ''),
            'tag': highlight_data.get('tag', ''),
            'content_hash': self._compute_content_hash(highlight_data.get('content', '')),
            'updated_at': datetime.now().isoformat(),
            'dimension': len(embedding)
        }
        self._save_embeddings()
    
    def get_highlight_embedding(self, highlight_id: str) -> Optional[List[float]]:
        """Get embedding for a highlight."""
        if highlight_id in self.embeddings:
            return self.embeddings[highlight_id]['embedding']
        return None
    
    def needs_embedding(self, highlight_id: str, content: str) -> bool:
        """Check if highlight needs (re-)embedding."""
        if highlight_id not in self.embeddings:
            return True
        
        current_hash = self._compute_content_hash(content)
        stored_hash = self.embeddings[highlight_id].get('content_hash', '')
        
        return current_hash != stored_hash
    
    def get_all_highlight_ids(self) -> List[str]:
        """Get list of all highlight IDs with embeddings."""
        return list(self.embeddings.keys())
    
    def get_highlight_metadata(self, highlight_id: str) -> Optional[dict]:
        """Get metadata for a highlight (without embedding vector)."""
        if highlight_id in self.embeddings:
            data = self.embeddings[highlight_id].copy()
            data.pop('embedding', None)  # Don't return heavy embedding
            return data
        return None
    
    def search_by_similarity(self, query_embedding: List[float], top_k: int = 10, min_similarity: float = 0.3) -> List[dict]:
        """Search highlights by embedding similarity."""
        results = []
        
        for highlight_id, data in self.embeddings.items():
            embedding = data['embedding']
            similarity = EmbeddingManager.cosine_similarity(query_embedding, embedding)
            
            if similarity >= min_similarity:
                results.append({
                    'highlight_id': highlight_id,
                    'content': data['content'],
                    'doc_id': data['doc_id'],
                    'tag': data['tag'],
                    'similarity': similarity,
                    'updated_at': data['updated_at']
                })
        
        # Sort by similarity descending
        results.sort(key=lambda x: x['similarity'], reverse=True)
        
        return results[:top_k]
    
    def get_stats(self) -> dict:
        """Get statistics about highlight embeddings."""
        total = len(self.embeddings)
        if total == 0:
            return {'total': 0, 'avg_dimension': 0}
        
        dimensions = [e['dimension'] for e in self.embeddings.values()]
        return {
            'total': total,
            'avg_dimension': sum(dimensions) / len(dimensions),
            'oldest': min([e['updated_at'] for e in self.embeddings.values()]) if total > 0 else None,
            'newest': max([e['updated_at'] for e in self.embeddings.values()]) if total > 0 else None
        }


def get_highlights_for_doc(doc_id: str, all_highlights: List[dict]) -> List[dict]:
    """Filter highlights for a specific document."""
    return [h for h in all_highlights if h.get('doc_id') == doc_id]


async def generate_embeddings_batch(
    client, 
    docs: List[dict], 
    all_highlights: List[dict],
    embedding_manager: EmbeddingManager,
    force: bool = False
) -> dict:
    """
    Generate embeddings for multiple documents in batch.
    
    Args:
        client: AI client
        docs: List of document dictionaries
        all_highlights: All highlights
        embedding_manager: EmbeddingManager instance
        force: Force regeneration even if exists
        
    Returns:
        Status dictionary with counts
    """
    generated = 0
    skipped = 0
    failed = 0
    
    for doc in docs:
        doc_id = doc['id']
        doc_highlights = get_highlights_for_doc(doc_id, all_highlights)
        
        # Skip if no highlights
        if not doc_highlights:
            skipped += 1
            continue
        
        # Skip if already has valid embedding
        if not force and not embedding_manager.needs_embedding(doc_id, doc_highlights):
            skipped += 1
            continue
        
        # Generate embedding
        embedding = await generate_embedding_from_ai(client, doc_highlights)
        
        if embedding:
            embedding_manager.save_embedding(doc_id, embedding, doc_highlights)
            generated += 1
        else:
            failed += 1
    
    return {
        'total': len(docs),
        'generated': generated,
        'skipped': skipped,
        'failed': failed
    }
