/*
Enhanced Content Search - Frontend Update for index.html

INSTRUCTIONS:
1. Open /templates/index.html
2. Find the section "// 6. Semantic Search Logic" (around line 404-442)
3. Replace that entire section with the code below
*/

// 6. Enhanced Content Search (searches within highlights, not just titles)
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
                        const matchInfo = `${docResult.total_matches} kết quả khớp trong nội dung:\n\n${docResult.matches.slice(0, 3).map((m, idx) =>
                            `${idx + 1}. [${m.tag}] ${m.snippet.substring(0, 100)}...`
                        ).join('\n\n')}`;

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
});
