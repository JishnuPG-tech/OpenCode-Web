import sqlite3
import time
import os

db_paths = [
    "/data/share/opencode/opencode.db",
    "/root/.local/share/opencode/opencode.db",
    "/home/opencode/.local/share/opencode/opencode.db",
]

# Find the active database file
db_path = None
for path in db_paths:
    if os.path.exists(path):
        db_path = path
        break

if not db_path:
    db_path = os.path.expanduser("~/.local/share/opencode/opencode.db")

print(f"OpenCode Self-Healing Daemon: watching database {db_path}...", flush=True)

while True:
    time.sleep(3)  # check every 3 seconds for faster recovery
    if not os.path.exists(db_path):
        continue
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Check if session table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='session'")
        if not cursor.fetchone():
            conn.close()
            continue
            
        # 1. Update directory and path if they contain invalid characters
        cursor.execute("SELECT id, directory, path FROM session")
        rows = cursor.fetchall()
        for row_id, directory, path in rows:
            need_update = False
            new_directory = directory
            new_path = path
            
            if directory and ("\ufffd" in directory or "\xef\xbf\xbd" in directory or "??#y" in directory):
                new_directory = "/projects/default"
                need_update = True
            
            if path and ("\ufffd" in path or "\xef\xbf\xbd" in path or "??#y" in path):
                new_path = "projects/default"
                need_update = True
                
            if need_update:
                print(f"[Self-Healing] Session '{row_id}' has corrupted path/directory. Fixing directory='{new_directory}', path='{new_path}'...", flush=True)
                cursor.execute(
                    "UPDATE session SET directory = ?, path = ? WHERE id = ?",
                    (new_directory, new_path, row_id)
                )
                conn.commit()
                
        # 2. Clean up project_directory table if it exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='project_directory'")
        if cursor.fetchone():
            cursor.execute("SELECT project_id, directory FROM project_directory")
            p_rows = cursor.fetchall()
            for p_id, directory in p_rows:
                if directory and ("\ufffd" in directory or "\xef\xbf\xbd" in directory or "??#y" in directory):
                    print(f"[Self-Healing] Found corrupted directory '{directory}' in project_directory '{p_id}'. Deleting...", flush=True)
                    cursor.execute(
                        "DELETE FROM project_directory WHERE project_id = ? AND directory = ?",
                        (p_id, directory)
                    )
                    conn.commit()
                    
        conn.close()
    except Exception as e:
        print("[Self-Healing Error]:", e, flush=True)
