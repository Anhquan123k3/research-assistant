#!/usr/bin/env python3
"""
Fix JavaScript function scoping in index.html
Makes functions globally accessible for onclick handlers
"""

import re


def fix_function_scoping():
    """Add window. prefix to function declarations to expose them globally"""
    
    with open('templates/index.html', 'r', encoding='utf-8') as f:
        content = f.read()
    
    # List of functions that need to be global (used in onclick)
    functions_to_fix = [
        'compareSelected',
       'deleteDoc',
        'createCollection',
        'deleteCollection',
        'filterByCollection',
        'toggleLibraryChat',
        'addLibMessage',
        'sendLibraryChat'
    ]
    
    for func_name in functions_to_fix:
        # Pattern: function funcName( -> window.funcName = function(
        pattern = rf'(\s+)function {func_name}\('
        replacement = rf'\1window.{func_name} = function('
        content = re.sub(pattern, replacement, content)
        
        # Also handle async function
        pattern = rf'(\s+)async function {func_name}\('
        replacement = rf'\1window.{func_name} = async function('
        content = re.sub(pattern, replacement, content)
    
    with open('templates/index.html', 'w', encoding='utf-8') as f:
        f.write(content)
    
    print("✅ Fixed function scoping!")
    print(f"   Exposed {len(functions_to_fix)} functions to window object")
    return True


if __name__ == "__main__":
    print("🔧 Fixing JavaScript function scoping...")
    print("=" * 50)
    
    success = fix_function_scoping()
    
    print("=" * 50)
    if success:
        print("🎉 All functions now globally accessible!")
        print("\n📝 Fixed functions:")
        print("  - compareSelected()")
        print("  - deleteDoc()")
        print("  - createCollection()")
        print("  - deleteCollection()")
        print("  - filterByCollection()")
        print("  - toggleLibraryChat()")
        print("  - sendLibraryChat()")
        print("\n✨ All onclick handlers should now work!")
