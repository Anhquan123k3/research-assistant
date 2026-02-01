"""
Firestore Database Manager
Replaces SQLite operations with Google Cloud Firestore
"""

import os
from datetime import datetime
from typing import List, Dict, Optional
from google.cloud import firestore
import firebase_admin
from firebase_admin import credentials, firestore as admin_firestore


class FirestoreManager:
    def __init__(self):
        """Initialize Firestore client"""
        # Initialize Firebase Admin SDK if not already initialized
        if not firebase_admin._apps:
            # In Cloud Run, Application Default Credentials are used automatically
            firebase_admin.initialize_app()
        
        self.db = firestore.Client()
        self.documents_collection = self.db.collection('documents')
        self.collections_collection = self.db.collection('collections')
    
    # ==================== Documents ====================
    
    def add_document(self, title: str, file_path: str, collection: str = '') -> str:
        """
        Add a new document to Firestore
        Returns: document ID
        """
        doc_data = {
            'title': title,
            'file_path': file_path,  # This will be Firebase Storage path
            'collection': collection,
            'created_at': firestore.SERVER_TIMESTAMP,
            'updated_at': firestore.SERVER_TIMESTAMP
        }
        
        doc_ref = self.documents_collection.add(doc_data)
        return doc_ref[1].id
    
    def get_documents(self, collection: Optional[str] = None) -> List[Dict]:
        """
        Get all documents, optionally filtered by collection
        """
        query = self.documents_collection
        
        if collection:
            query = query.where('collection', '==', collection)
        
        query = query.order_by('created_at', direction=firestore.Query.DESCENDING)
        
        docs = []
        for doc in query.stream():
            doc_dict = doc.to_dict()
            doc_dict['id'] = doc.id
            docs.append(doc_dict)
        
        return docs
    
    def get_document_by_id(self, doc_id: str) -> Optional[Dict]:
        """Get a single document by ID"""
        doc_ref = self.documents_collection.document(doc_id)
        doc = doc_ref.get()
        
        if doc.exists:
            doc_dict = doc.to_dict()
            doc_dict['id'] = doc.id
            return doc_dict
        return None
    
    def update_document(self, doc_id: str, **kwargs) -> bool:
        """Update document fields"""
        doc_ref = self.documents_collection.document(doc_id)
        
        update_data = {**kwargs}
        update_data['updated_at'] = firestore.SERVER_TIMESTAMP
        
        doc_ref.update(update_data)
        return True
    
    def delete_document(self, doc_id: str) -> bool:
        """Delete a document"""
        doc_ref = self.documents_collection.document(doc_id)
        doc_ref.delete()
        return True
    
    def search_documents(self, query: str) -> List[Dict]:
        """
        Search documents by title
        Note: Firestore doesn't have full-text search, so we filter client-side
        For production, consider using Algolia or Elasticsearch
        """
        all_docs = self.get_documents()
        
        query_lower = query.lower()
        results = [
            doc for doc in all_docs
            if query_lower in doc.get('title', '').lower()
        ]
        
        return results
    
    # ==================== Collections ====================
    
    def get_collections(self) -> List[str]:
        """Get list of all collection names"""
        collections_ref = self.collections_collection.stream()
        return [col.id for col in collections_ref]
    
    def create_collection(self, name: str) -> bool:
        """Create a new collection"""
        collection_ref = self.collections_collection.document(name)
        collection_ref.set({
            'name': name,
            'created_at': firestore.SERVER_TIMESTAMP
        })
        return True
    
    def delete_collection(self, name: str) -> bool:
        """Delete a collection and update all documents in it"""
        # Delete collection document
        collection_ref = self.collections_collection.document(name)
        collection_ref.delete()
        
        # Update all documents in this collection to have empty collection
        docs_in_collection = self.documents_collection.where('collection', '==', name).stream()
        
        for doc in docs_in_collection:
            doc.reference.update({'collection': '', 'updated_at': firestore.SERVER_TIMESTAMP})
        
        return True
    
    def move_document_to_collection(self, doc_id: str, collection_name: str) -> bool:
        """Move a document to a different collection"""
        return self.update_document(doc_id, collection=collection_name)


# Singleton instance
_firestore_manager = None


def get_firestore_manager() -> FirestoreManager:
    """Get or create FirestoreManager instance"""
    global _firestore_manager
    if _firestore_manager is None:
        _firestore_manager = FirestoreManager()
    return _firestore_manager
