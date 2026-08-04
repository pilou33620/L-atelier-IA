import pytest
from unittest.mock import patch, MagicMock
from PyQt6.QtCore import QObject

@pytest.fixture
def orchestrator():
    # Création d'un mock pour éviter les initialisations lourdes
    # On simule uniquement ce qui est nécessaire pour execute_tool
    class MockWorker(QObject):
        def __init__(self):
            super().__init__()
            self.sandbox = MagicMock()
            
            # Mocks des signaux PyQt6
            self.agent_action_event = MagicMock()
            self.status_update = MagicMock()
            self.ask_confirmation = MagicMock(return_value=True)
            self.api_key = "test_key"
            
        def execute_tool(self, action, current_agent_id):
            # Copie de la logique de workers.py
            name = action.get("action")
            args = action.get("args", {}) or {}
            
            target = str(
                args.get("path") or 
                args.get("pattern") or 
                args.get("query") or 
                args.get("command") or 
                args.get("agent") or 
                args.get("node") or 
                args.get("node_a") or 
                args.get("question") or 
                ""
            )
            self.agent_action_event.emit(current_agent_id, name, target)
            
            try:
                if name == "list_dir":
                    entries = self.sandbox.list_dir(args.get("path", "."))
                    return "Contenu :\n" + "\n".join(entries)

                if name == "read_file":
                    start_line = args.get("start")
                    end_line = args.get("end")
                    content = self.sandbox.read_file(args["path"], start_line=start_line, end_line=end_line)
                    return f"Contenu de {args['path']} :\n{content}"
                    
                if name == "read_image":
                    path = args.get("path")
                    if not path:
                        return "ERREUR : 'path' est requis pour read_image."
                    abs_path = self.sandbox._safe_path(path, write_mode=False)
                    if not abs_path.exists():
                        return f"ERREUR : Fichier image introuvable : {path}"
                    return f"✅ Image '{path}' chargée avec succès."
                    
                if name == "graphify_query":
                    query = args.get("query")
                    if not query:
                        return "ERREUR : 'query' est requis."
                    if not self.ask_confirmation("msg"):
                        return "ERREUR : L'utilisateur a refusé l'exécution de graphify."
                    return "Graphify (Query) : " + query
                    
            except Exception as e:
                return f"ERREUR lors de l'exécution de l'outil : {str(e)}"
            return f"Outil non reconnu : {name}"

    return MockWorker()

def test_execute_tool_list_dir(orchestrator):
    orchestrator.sandbox.list_dir.return_value = ["file1.txt", "file2.py"]
    
    result = orchestrator.execute_tool({"action": "list_dir", "args": {"path": "."}}, "agent1")
    assert "file1.txt" in result
    assert "file2.py" in result
    orchestrator.agent_action_event.emit.assert_called_with("agent1", "list_dir", ".")

def test_execute_tool_read_file(orchestrator):
    orchestrator.sandbox.read_file.return_value = "def test():\n    pass"
    
    result = orchestrator.execute_tool({"action": "read_file", "args": {"path": "main.py"}}, "agent1")
    assert "def test():" in result
    orchestrator.sandbox.read_file.assert_called_with("main.py", start_line=None, end_line=None)

def test_execute_tool_graphify_query_accepted(orchestrator):
    orchestrator.ask_confirmation.return_value = True
    
    result = orchestrator.execute_tool({"action": "graphify_query", "args": {"query": "how to build"}}, "agent1")
    assert "how to build" in result
    orchestrator.ask_confirmation.assert_called_once()

def test_execute_tool_graphify_query_refused(orchestrator):
    orchestrator.ask_confirmation.return_value = False
    
    result = orchestrator.execute_tool({"action": "graphify_query", "args": {"query": "how to build"}}, "agent1")
    assert "refusé" in result

# --- Nouveaux tests pour le parsing JSON (V4.4.1 helpers) ---

from core.workers import (
    _pair_orphan_backslashes,
    _strip_trailing_commas,
    _find_balanced_end,
    _collect_json_candidates
)

def test_pair_orphan_backslashes():
    # Déjà appairé
    assert _pair_orphan_backslashes(r"C:\\Users") == r"C:\\Users"
    # Orphelin mais valide (JSON)
    assert _pair_orphan_backslashes(r'\"hello\"') == r'\"hello\"'
    assert _pair_orphan_backslashes(r'\n') == r'\n'
    # Orphelin invalide -> réparé
    assert _pair_orphan_backslashes(r"C:\Users\Name") == r"C:\\Users\\Name"

def test_strip_trailing_commas():
    assert _strip_trailing_commas('{"a": 1,}') == '{"a": 1}'
    assert _strip_trailing_commas('["a", ]') == '["a"]'
    assert _strip_trailing_commas('{"a": 1}') == '{"a": 1}'

def test_find_balanced_end():
    text = '{"key": "value"}'
    assert _find_balanced_end(text, 0) == len(text)
    
    # Avec des accolades dans la string
    text2 = '{"key": "val{ue}"} outside'
    end = _find_balanced_end(text2, 0)
    assert text2[:end] == '{"key": "val{ue}"}'

def test_collect_json_candidates():
    # Texte brut sans markdown
    text_raw = 'Bonjour voici le json: {"action": "test"} au revoir.'
    candidates, err = _collect_json_candidates(text_raw)
    assert len(candidates) >= 1
    assert candidates[0][0] == {"action": "test"}
    assert "raw" in candidates[0][1]

    # Markdown JSON
    text_md = '```json\n{"a": 1}\n```'
    candidates_md, err_md = _collect_json_candidates(text_md)
    assert len(candidates_md) >= 1
    assert candidates_md[0][0] == {"a": 1}
    assert "markdown" in candidates_md[0][1]
