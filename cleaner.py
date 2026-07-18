import sqlite3
import time
import os

print("OpenCode Self-Healing Daemon: started", flush=True)

# All possible database locations — check them all every loop
DB_PATHS = [
    "/projects/.opencode/share/opencode/opencode.db",
    "/data/share/opencode/opencode.db",
    "/root/.local/share/opencode/opencode.db",
    "/home/opencode/.local/share/opencode/opencode.db",
]

def is_corrupted(s):
    return s and ("\ufffd" in s or "??#y" in s or "\xef\xbf\xbd" in s)

while True:
    time.sleep(3)
    
    for db_path in DB_PATHS:
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
                
            # 1. Fix directory and path columns in session table
            cursor.execute("SELECT id, directory, path FROM session")
            for row_id, directory, path in cursor.fetchall():
                need_update = False
                new_directory = directory
                new_path = path
                
                if is_corrupted(directory):
                    new_directory = "/projects/default"
                    need_update = True
                
                if is_corrupted(path):
                    new_path = None
                    need_update = True
                    
                if need_update:
                    print(f"[Healed] Session '{row_id}': dir={directory!r} -> {new_directory!r}, path={path!r} -> {new_path!r}", flush=True)
                    cursor.execute(
                        "UPDATE session SET directory = ?, path = ? WHERE id = ?",
                        (new_directory, new_path, row_id)
                    )
                    conn.commit()
                    
            # 2. Fix project_directory table
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='project_directory'")
            if cursor.fetchone():
                cursor.execute("SELECT project_id, directory FROM project_directory")
                for p_id, directory in cursor.fetchall():
                    if is_corrupted(directory):
                        print(f"[Healed] project_directory '{p_id}': deleting corrupted dir={directory!r}", flush=True)
                        cursor.execute(
                            "DELETE FROM project_directory WHERE project_id = ? AND directory = ?",
                            (p_id, directory)
                        )
                        conn.commit()
                        
            conn.close()
        except sqlite3.OperationalError:
            pass  # DB might be locked by opencode, skip this cycle
        except Exception as e:
            print(f"[Healer Error] {db_path}: {e}", flush=True)
