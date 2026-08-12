#!/usr/bin/env python3
import os
import sys

def fix_migrations(root_dir="/omniroute"):
    print("[FIX] Checking OmniRoute migrations for version collisions...")
    if not os.path.exists(root_dir):
        print(f"[FIX] Path {root_dir} does not exist, skipping.")
        return

    count = 0
    for dirpath, dirnames, filenames in os.walk(root_dir):
        if os.path.basename(dirpath) == "migrations":
            version_map = {}
            for fname in sorted(filenames):
                if fname.endswith((".ts", ".js", ".sql", ".mjs")):
                    parts = fname.split("_", 1)
                    if len(parts) > 1 and parts[0].isdigit():
                        ver = int(parts[0])
                        version_map.setdefault(ver, []).append(fname)
            
            if not version_map:
                continue

            highest_ver = max(version_map.keys())
            for ver, f_list in sorted(version_map.items()):
                if len(f_list) > 1:
                    print(f"[FIX] Found collision at version {ver} in {dirpath}: {f_list}")
                    # Keep first, rename subsequent colliding files
                    for extra_f in f_list[1:]:
                        highest_ver += 1
                        old_p = os.path.join(dirpath, extra_f)
                        suffix = extra_f.split("_", 1)[1]
                        new_fname = f"{highest_ver:03d}_{suffix}"
                        new_p = os.path.join(dirpath, new_fname)
                        os.rename(old_p, new_p)
                        print(f"[FIX] Successfully renamed {extra_f} -> {new_fname}")
                        count += 1

    print(f"[FIX] Migration check complete. Resolved {count} version collision(s).")

if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "/omniroute"
    fix_migrations(target)
