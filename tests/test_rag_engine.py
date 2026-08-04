import pytest
import os
import json
from unittest.mock import patch, MagicMock
from core.rag_engine import GraphRagEngine

@pytest.fixture
def mock_sandbox(tmp_path):
    # Créer un faux graphify-out
    graphify_out = tmp_path / "graphify-out"
    graphify_out.mkdir()
    
    # Créer un faux fichier source
    src_file = tmp_path / "test_src.py"
    src_file.write_text("def my_func():\n    pass\n\ndef my_other_func():\n    return True\n", encoding="utf-8")
    
    # Créer un faux graph.json
    graph_data = {
        "nodes": [
            {
                "id": 1,
                "file_type": "code",
                "source_file": "test_src.py",
                "source_location": "L1",
                "label": "my_func"
            },
            {
                "id": 2,
                "file_type": "code",
                "source_file": "test_src.py",
                "source_location": "L4",
                "label": "my_other_func"
            },
            {
                "id": 3,
                "file_type": "text",
                "label": "ignore_me"
            }
        ]
    }
    
    graph_file = graphify_out / "graph.json"
    with open(graph_file, "w", encoding="utf-8") as f:
        json.dump(graph_data, f)
        
    return tmp_path

@patch("chromadb.PersistentClient")
def test_rag_engine_init(mock_chroma, tmp_path):
    engine = GraphRagEngine(str(tmp_path))
    assert engine.sandbox_root == str(tmp_path)
    mock_chroma.assert_called_once()
    
@patch("chromadb.PersistentClient")
def test_extract_node_content(mock_chroma, mock_sandbox):
    engine = GraphRagEngine(str(mock_sandbox))
    
    with open(mock_sandbox / "graphify-out" / "graph.json", "r", encoding="utf-8") as f:
        graph_data = json.load(f)
        
    nodes = graph_data["nodes"]
    
    # Extrait L1 jusqu'à L3 (parce que L4 commence l'autre noeud)
    content1 = engine._extract_node_content(nodes[0], nodes)
    assert "def my_func():" in content1
    assert "def my_other_func():" not in content1
    
    # Extrait L4 jusqu'à la fin
    content2 = engine._extract_node_content(nodes[1], nodes)
    assert "def my_other_func():" in content2
