"""
Migration Script: SQLite to Firestore
Migrates existing documents and files to Firebase
"""

import sqlite3
import os
from firestore_manager import get_firestore_manager
from storage_manager import get_storage_manager


def migrate_database():
    """Migrate all data from SQLite to Firestore"""
    
    print("🚀 Starting migration from SQLite to Firestore...")
    
    # Initialize managers
    db_manager = get_firestore_manager()
    storage_manager = get_storage_manager()
    
    # Connect to SQLite
    sqlite_db_path = 'research_library.db'
    
    if not os.path.exists(sqlite_db_path):
        print(f"❌ SQLite database not found at {sqlite_db_path}")
        return
    
    conn = sqlite3.connect(sqlite_db_path)
    cursor = conn.cursor()
    
    # Get table names to check if they exist
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = [row[0] for row in cursor.fetchall()]
    print(f"📋 Found tables: {tables}")
    
    # ==================== Migrate Collections ====================
    if 'collections' in tables:
        print("\n📁 Migrating collections...")
        cursor.execute("SELECT name FROM collections")
        collections = cursor.fetchall()
        
        for (collection_name,) in collections:
            try:
                db_manager.create_collection(collection_name)
                print(f"  ✅ Migrated collection: {collection_name}")
            except Exception as e:
                print(f"  ⚠️  Error migrating collection {collection_name}: {e}")
    
    # ==================== Migrate Documents ====================
    if 'documents' in tables:
        print("\n📄 Migrating documents...")
        cursor.execute("SELECT id, title, file_path, collection FROM documents")
        documents = cursor.fetchall()
        
        total_docs = len(documents)
        print(f"Found {total_docs} documents to migrate")
        
        for idx, (doc_id, title, file_path, collection) in enumerate(documents, 1):
            print(f"\n[{idx}/{total_docs}] Migrating: {title}")
            
            try:
                # Check if file exists locally
                if file_path and os.path.exists(file_path):
                    # Upload file to Firebase Storage
                    storage_path = f"uploads/{os.path.basename(file_path)}"
                    print(f"  📤 Uploading file to Firebase Storage: {storage_path}")
                    storage_manager.upload_file(file_path, storage_path)
                    print(f"  ✅ File uploaded successfully")
                    
                    # Add document to Firestore  
                    firestore_doc_id = db_manager.add_document(
                        title=title,
                        file_path=storage_path,
                        collection=collection or ''
                    )
                    print(f"  ✅ Document added to Firestore with ID: {firestore_doc_id}")
                else:
                    print(f"  ⚠️  File not found: {file_path}")
                    # Still add document metadata without file
                    firestore_doc_id = db_manager.add_document(
                        title=title,
                        file_path='',
                        collection=collection or ''
                    )
                    print(f"  ✅ Document metadata added (no file)")
                    
            except Exception as e:
                print(f"  ❌ Error migrating document {title}: {e}")
    
    conn.close()
    
    print("\n\n✅ Migration completed!")
    print("\n📊 Summary:")
    print(f"  - Collections: {len(db_manager.get_collections())}")
    print(f"  - Documents: {len(db_manager.get_documents())}")
    print("\n🎉 You can now deploy to Cloud Run!")


if __name__ == "__main__":
    migrate_database()
