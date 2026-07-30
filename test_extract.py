import json
import re

def extract_action(text):
    candidates = []
    last_error = None

    for m in re.finditer(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL):
        try:
            candidates.append((json.loads(m.group(1), strict=False), "markdown"))
        except json.JSONDecodeError as e:
            last_error = str(e)

    decoder = json.JSONDecoder(strict=False)
    idx = 0
    while True:
        start = text.find('{', idx)
        if start == -1:
            break
        try:
            obj, offset = decoder.raw_decode(text[start:])
            candidates.append((obj, "raw"))
            idx = start + offset
        except json.JSONDecodeError as e:
            if not last_error:
                last_error = str(e)
            idx = start + 1

    actions = [(obj, origin) for (obj, origin) in candidates
                if isinstance(obj, dict) and "action" in obj]
    if not actions:
        if last_error:
            return None, f"error: {last_error}"
        if candidates:
            return None, "error: JSON valide trouvé mais la clé 'action' est manquante. Format attendu : {\"action\": \"nom_de_l_action\", \"args\": {...}}"
        return None, "error"

    seen = {}
    for obj, origin in actions:
        key = json.dumps(obj, sort_keys=True, ensure_ascii=False)
        if key not in seen:
            seen[key] = origin

    if len(seen) > 1:
        return None, "ambiguous"

    only_key = next(iter(seen))
    obj = json.loads(only_key, strict=False)
    status = "success_markdown" if seen[only_key] == "markdown" else "fallback_raw"
    return obj, status

test_cases = [
    # 1. Normal markdown JSON
    "Hello\n```json\n{\"action\": \"test\"}\n```",
    # 2. Raw JSON
    "Hello\n{\"action\": \"test\"}",
    # 3. Invalid JSON (unescaped newline)
    "```json\n{\"action\": \"test\", \"args\": {\"msg\": \"line1\nline2\"}}\n```",
    # 4. Invalid JSON (trailing comma)
    "```json\n{\"action\": \"test\", \"args\": {},}\n```",
    # 5. Multiple JSONs (ambiguous)
    "```json\n{\"action\": \"a\"}\n``` ```json\n{\"action\": \"b\"}\n```",
    # 6. JSON with internal markdown
    "```json\n{\"action\": \"reply\", \"content\": \"```python\\nprint(1)\\n```\"}\n```"
]

for i, tc in enumerate(test_cases):
    print(f"Test {i+1}:")
    try:
        res, status = extract_action(tc)
        print(f"  Result: {res}")
        print(f"  Status: {status}")
    except Exception as e:
        print(f"  Exception: {e}")
