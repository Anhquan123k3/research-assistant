#!/usr/bin/env python3
"""
Auto-merge frontend content search update into index.html
Run from research-assistant directory: python update_frontend_search.py
"""

import re


def update_frontend_search():
    """Replace old semantic search with new content search in index.html"""
    
    with open('templates/index.html', 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Check if already updated
    if 'search-content' in content or 'Enhanced Content Search' in content:
        print("ℹ️  Frontend already has content search!")
        return True
    
    # New content search JavaScript
    new_search_code = """    // 6. Enhanced Content Search (searches within highlights, not just titles)
    const searchInput = document.getElementById('semantic-search-input');
    const searchLoading = document.getElementById('search-loading');
    const docRows = document.querySelectorAll('#doc-list tr');

    let searchTimeout;
    searchInput.addEventListener('input', (e) => {
        clearTimeout(searchTimeout);
        const query = e.target.value.trim();

        // Remove existing search summary
        const existingSummary = document.getElementById('search-summary');
        if (existingSummary) existingSummary.remove();

        if (!query) {
            // Show all documents
            docRows.forEach(row => {
                row.style.display = '';
                row.title = '';
                row.classList.remove('bg-yellow-50');
            });
            return;
        }

        searchTimeout = setTimeout(async () => {
            searchLoading.classList.remove('hidden');
            try {
                // Call new content search API
                const res = await fetch(`/api/search-content?query=${encodeURIComponent(query)}&mode=hybrid`);
                const data = await res.json();
                
                if (!data.results) {
                    throw new Error("Invalid response from search API");
                }
                
                const relevantIds = data.results.map(r => r.doc_id);

                // Show/hide document rows
                docRows.forEach(row => {
                    const cb = row.querySelector('.doc-checkbox');
                    if (cb) {
                        const docResult = data.results.find(r => r.doc_id === cb.value);
                        
                        if (docResult) {
                            row.style.display = '';
                            
                            // Build tooltip showing matches
                            const matchInfo = `${docResult.total_matches} kết quả khớp trong nội dung:\\n\\n${docResult.matches.slice(0, 3).map((m, idx) => 
                                `${idx + 1}. [${m.tag}] ${m.snippet.substring(0, 100)}...`
                            ).join('\\n\\n')}`;
                            
                            row.title = matchInfo;
                            
                            // Highlight matched row
                            row.classList.add('bg-yellow-50');
                        } else {
                            row.style.display = 'none';
                            row.classList.remove('bg-yellow-50');
                            row.title = '';
                        }
                    }
                });
                
                // Show search results summary
                if (data.total_documents > 0) {
                    const summary = document.createElement('div');
                    summary.id = 'search-summary';
                    summary.className = 'mb-4 p-3 bg-blue-50 border border-blue-200 rounded-lg flex items-center justify-between';
                    summary.innerHTML = `
                        <div class="flex items-center gap-2 text-sm text-blue-700">
                            <i class="fa-solid fa-search"></i>
                            <span>
                                Tìm thấy <strong>${data.total_matches}</strong> đoạn nội dung khớp
                                trong <strong>${data.total_documents}</strong> tài liệu
                            </span>
                        </div>
                        <button onclick="document.getElementById('semantic-search-input').value = ''; document.getElementById('semantic-search-input').dispatchEvent(new Event('input'));" 
                            class="text-blue-500 hover:text-blue-700 text-xs">
                            <i class="fa-solid fa-xmark mr-1"></i> Xóa
                        </button>
                    `;
                    
                    // Insert before table
                    const tableContainer = document.querySelector('.bg-white.rounded-xl');
                    tableContainer.parentElement.insertBefore(summary, tableContainer);
                } else {
                    // No results found
                    const summary = document.createElement('div');
                    summary.id = 'search-summary';
                    summary.className = 'mb-4 p-3 bg-slate-100 border border-slate-300 rounded-lg text-center text-slate-600 text-sm';
                    summary.innerHTML = `
                        <i class="fa-solid fa-magnifying-glass mr-2"></i>
                        Không tìm thấy kết quả nào cho "<strong>${query}</strong>"
                    `;
                    
                    const tableContainer = document.querySelector('.bg-white.rounded-xl');
                    tableContainer.parentElement.insertBefore(summary, tableContainer);
                }
                
            } catch (err) {
                console.error("Content search failed:", err);
                alert('Lỗi tìm kiếm: ' + err.message);
            } finally {
                searchLoading.classList.add('hidden');
            }
        }, 500);  // 500ms debounce
    });"""
    
    # Pattern to match old semantic search section
    # Find from "// 6. Semantic Search Logic" to the end of searchInput.addEventListener
    pattern = r'// 6\. Semantic Search Logic.*?searchTimeout.*?\}, \d+\);.*?\}\);'
    
    # Replace with new code
    new_content = re.sub(pattern, new_search_code, content, flags=re.DOTALL)
    
    if new_content == content:
        print("❌ Could not find old search code to replace!")
        print("Trying alternative pattern...")
        
        # Alternative: Find by specific markers
        start_marker = "// 6. Semantic Search Logic"
        end_marker = "}, 800);\n    });"
        
        start_idx = content.find(start_marker)
        if start_idx == -1:
            print("❌ Could not find start marker!")
            return False
        
        # Find end from start position
        end_idx = content.find(end_marker, start_idx)
        if end_idx == -1:
            print("❌ Could not find end marker!")
            return False
        
        # Include the end marker
        end_idx += len(end_marker)
        
        # Replace
        new_content = content[:start_idx] + new_search_code + content[end_idx:]
    
    # Write updated file
    with open('templates/index.html', 'w', encoding='utf-8') as f:
        f.write(new_content)
    
    print("✅ Successfully updated frontend search in index.html!")
    return True


if __name__ == "__main__":
    print("🔧 Updating frontend search in index.html...")
    print("=" * 50)
    
    success = update_frontend_search()
    
    print("=" * 50)
    if success:
        print("🎉 Frontend updated successfully!")
        print("\n📝 Next steps:")
        print("  1. Start server: python main.py")
        print("  2. Open http://localhost:8000")
        print("  3. Try searching: 'phương pháp', 'kết quả', etc.")
        print("  4. Should search in CONTENT, not just filenames!")
    else:
        print("⚠️  Update failed - please check manually")
