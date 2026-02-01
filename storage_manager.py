"""
Firebase Storage Manager
Handles file uploads and downloads to Firebase Storage
"""

import os
from typing import Optional
from firebase_admin import storage
from werkzeug.utils import secure_filename


class StorageManager:
    def __init__(self, bucket_name: Optional[str] = None):
        """
        Initialize Firebase Storage
        
        Args:
            bucket_name: Optional custom bucket name. If not provided,
                        uses the default bucket from Firebase config
        """
        if bucket_name:
            self.bucket = storage.bucket(bucket_name)
        else:
            self.bucket = storage.bucket()
    
    def upload_file(self, local_file_path: str, storage_path: str) -> str:
        """
        Upload a file to Firebase Storage
        
        Args:
            local_file_path: Path to the local file
            storage_path: Destination path in Firebase Storage (e.g., 'uploads/file.pdf')
        
        Returns:
            The storage path of the uploaded file
        """
        blob = self.bucket.blob(storage_path)
        blob.upload_from_filename(local_file_path)
        
        # Make the file publicly accessible (adjust based on security requirements)
        # blob.make_public()
        
        return storage_path
    
    def download_file(self, storage_path: str, local_file_path: str) -> str:
        """
        Download a file from Firebase Storage
        
        Args:
            storage_path: Path in Firebase Storage
            local_file_path: Where to save the file locally
        
        Returns:
            Local file path
        """
        blob = self.bucket.blob(storage_path)
        blob.download_to_filename(local_file_path)
        return local_file_path
    
    def delete_file(self, storage_path: str) -> bool:
        """Delete a file from Firebase Storage"""
        blob = self.bucket.blob(storage_path)
        blob.delete()
        return True
    
    def get_signed_url(self, storage_path: str, expiration_minutes: int = 60) -> str:
        """
        Generate a temporary signed URL for file access
        
        Args:
            storage_path: Path in Firebase Storage
            expiration_minutes: How long the URL should be valid
        
        Returns:
            Signed URL string
        """
        from datetime import timedelta
        
        blob = self.bucket.blob(storage_path)
        url = blob.generate_signed_url(
            expiration=timedelta(minutes=expiration_minutes),
            version='v4'
        )
        return url
    
    def file_exists(self, storage_path: str) -> bool:
        """Check if a file exists in Firebase Storage"""
        blob = self.bucket.blob(storage_path)
        return blob.exists()
    
    def get_file_metadata(self, storage_path: str) -> dict:
        """Get metadata for a file"""
        blob = self.bucket.blob(storage_path)
        blob.reload()
        
        return {
            'name': blob.name,
            'size': blob.size,
            'content_type': blob.content_type,
            'created': blob.time_created,
            'updated': blob.updated,
        }


# Singleton instance
_storage_manager = None


def get_storage_manager() -> StorageManager:
    """Get or create StorageManager instance"""
    global _storage_manager
    if _storage_manager is None:
        _storage_manager = StorageManager()
    return _storage_manager
