import json

def extract_gemini_response(stdout: str) -> str:
    try:
        start = stdout.find("{")
        end = stdout.rfind("}")
        
        if start != -1 and end != -1 and end > start:
            json_str = stdout[start:end+1]
            try:
                data = json.loads(json_str)
                if "response" in data:
                    return str(data["response"]).strip()
            except json.JSONDecodeError as e:
                pass
                
        lines = stdout.strip().splitlines()
        json_str = ""
        for i in range(len(lines)):
            if lines[i].strip().startswith("{"):
                json_str = "\n".join(lines[i:])
                break
        
        if not json_str:
            return ""
            
        data = json.loads(json_str)
        return str(data.get("response") or "").strip()
    except (json.JSONDecodeError, KeyError, IndexError):
        return ""

stdout = """      MCP issues detected. Run /mcp list for status.{
        "session_id": "2b4fbf92-47b4-4878-b0b3-ffcf3306ce68",
        "response": "The requirement has been clarified.",
        "stats": {}
      }ClearcutLogger: Flush already in progress, marking pending flush."""

print(extract_gemini_response(stdout))
