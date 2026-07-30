import re

text = '```json\n{"action": "reply", "content": "```\\ncode\\n```"}\n```'
match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
print("Regex match:", repr(match.group(1)) if match else "No match")
