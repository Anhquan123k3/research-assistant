import os
import json
import fitz # PyMuPDF
from typing import List, Dict

LOCAL_DB_FILE = "local_metadata.json"

def get_library_context(max_chars_per_doc: int = 4000) -> str:
    """
    Trích xuất văn bản từ tất cả các tài liệu trong thư viện để làm ngữ cảnh cho AI.
    """
    if not os.path.exists(LOCAL_DB_FILE):
        return ""

    with open(LOCAL_DB_FILE, "r", encoding="utf-8") as f:
        docs = json.load(f)

    full_context = "Dưới đây là tóm lược thông tin từ thư viện tài liệu của bạn:\n\n"
    
    for doc in docs:
        doc_id = doc.get("id")
        filename = doc.get("filename")
        url = doc.get("url", "")
        
        # Chỉ xử lý file local (trong static/uploads)
        if url.startswith("/static/uploads/"):
            file_path = os.path.join("static", "uploads", url.split("/")[-1])
            if os.path.exists(file_path):
                try:
                    text = extract_text_from_pdf(file_path, max_chars_per_doc)
                    full_context += f"### TÀI LIỆU: {filename} (ID: {doc_id})\n"
                    full_context += f"{text}\n\n"
                except Exception as e:
                    print(f"Lỗi trích xuất {filename}: {e}")
                    
    return full_context

def extract_text_from_pdf(file_path: str, max_chars: int) -> str:
    """Trích xuất một phần văn bản từ PDF để tránh quá tải token."""
    text = ""
    try:
        with fitz.open(file_path) as doc:
            for page in doc:
                text += page.get_text()
                if len(text) > max_chars:
                    break
        return text[:max_chars] + ("..." if len(text) > max_chars else "")
    except Exception as e:
        return f"[Không thể đọc nội dung: {str(e)}]"

if __name__ == "__main__":
    # Test
    print(get_library_context(500))
