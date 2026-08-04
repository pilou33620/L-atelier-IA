import pytest
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QPointF
from core.nodal_graph import NodeItem, EdgeItem

@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app

def test_node_item_creation(qapp):
    node = NodeItem(node_id="test_node", label="Test Label", graph_widget=None)
    
    assert node.node_id == "test_node"
    assert node.label == "Test Label"
    assert node.state == "idle"
    assert len(node.edges) == 0

def test_edge_item_creation(qapp):
    node_a = NodeItem(node_id="node_a", label="A", graph_widget=None)
    node_b = NodeItem(node_id="node_b", label="B", graph_widget=None)
    
    edge = EdgeItem(source_node=node_a, dest_node=node_b)
    
    assert edge.source_node == node_a
    assert edge.dest_node == node_b
    assert edge in node_a.edges
    assert edge in node_b.edges

def test_node_item_add_edge(qapp):
    node_a = NodeItem(node_id="node_a", label="A", graph_widget=None)
    node_b = NodeItem(node_id="node_b", label="B", graph_widget=None)
    
    edge = EdgeItem(source_node=node_a, dest_node=node_b)
    
    assert edge in node_a.edges
