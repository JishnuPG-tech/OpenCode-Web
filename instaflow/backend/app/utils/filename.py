import re

def sanitize_filename(name: str) -> str:
    if not name:
        return "InstaFlow_Media"
    clean = re.sub(r'[\\/*?:"<>|]', "", name).strip()
    clean = re.sub(r"\s+", "_", clean)
    return clean[:100] if clean else "InstaFlow_Media"
