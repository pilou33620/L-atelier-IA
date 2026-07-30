import os
import json
import logging
import chromadb
from chromadb.utils import embedding_functions

logger = logging.getLogger(__name__)

class GraphRagEngine:
    def __init__(self, sandbox_root, db_path=None):
        self.sandbox_root = sandbox_root
        self.db_path = db_path or os.path.join(sandbox_root, "graphify-out", "chroma_db")
        
        # S'assurer que le dossier existe
        os.makedirs(self.db_path, exist_ok=True)
        
        # Initialiser ChromaDB
        self.chroma_client = chromadb.PersistentClient(path=self.db_path)
        
        # Utiliser fastembed (léger, CPU-only)
        try:
            from fastembed import TextEmbedding
            class CustomFastEmbedFunction:
                def __init__(self):
                    self.model = TextEmbedding("BAAI/bge-small-en-v1.5")
                def __call__(self, input):
                    # Génère les embeddings sous forme de générateurs, on convertit en listes
                    return [list(e) for e in self.model.embed(input)]
                def name(self) -> str:
                    return "custom_fastembed"
            
            self.embedding_fn = CustomFastEmbedFunction()
        except Exception as e:
            logger.warning(f"FastEmbed introuvable ou erreur ({e}), utilisation du modèle par défaut de Chroma.")
            self.embedding_fn = embedding_functions.DefaultEmbeddingFunction()
            
        try:
            self.collection = self.chroma_client.get_or_create_collection(
                name="codebase_rag",
                embedding_function=self.embedding_fn
            )
        except ValueError as e:
            if "embedding function" in str(e).lower() and "conflict" in str(e).lower():
                logger.warning(f"Conflit d'embedding détecté, recréation de la collection ChromaDB: {e}")
                try:
                    self.chroma_client.delete_collection(name="codebase_rag")
                except Exception:
                    pass
                self.collection = self.chroma_client.create_collection(
                    name="codebase_rag",
                    embedding_function=self.embedding_fn
                )
            else:
                raise

    def _extract_node_content(self, node, all_nodes):
        """
        Extrait le contenu du code source pour un nœud donné.
        Dans graph.json, source_location est souvent "L14" (début).
        Nous devons trouver la fin du bloc en regardant le nœud suivant dans le même fichier.
        """
        source_file = node.get("source_file")
        if not source_file:
            return ""
            
        loc = node.get("source_location", "")
        if not loc.startswith("L"):
            return ""
            
        try:
            start_line = int(loc[1:])
        except ValueError:
            return ""
            
        file_path = os.path.join(self.sandbox_root, source_file)
        if not os.path.exists(file_path):
            return ""
            
        # Trouver le prochain nœud dans le même fichier pour déduire la ligne de fin
        file_nodes = [n for n in all_nodes if n.get("source_file") == source_file]
        
        # Extraire les numéros de ligne
        lines = []
        for n in file_nodes:
            nl = n.get("source_location", "")
            if nl.startswith("L"):
                try:
                    lines.append(int(nl[1:]))
                except:
                    pass
        
        lines.sort()
        end_line = None
        for l in lines:
            if l > start_line:
                end_line = l - 1 # Le bloc se termine juste avant le nœud suivant
                break
                
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.readlines()
            
        # Lines in python are 0-indexed for lists, but start_line is 1-indexed
        start_idx = max(0, start_line - 1)
        
        if end_line:
            end_idx = min(len(content), end_line)
        else:
            # S'il n'y a pas d'autre nœud après, on limite à ~200 lignes
            end_idx = min(len(content), start_idx + 200)
            
        snippet = "".join(content[start_idx:end_idx])
        return snippet.strip()

    def build_index(self):
        """Lit graph.json et vectorise les nœuds de code."""
        graph_path = os.path.join(self.sandbox_root, "graphify-out", "graph.json")
        if not os.path.exists(graph_path):
            raise FileNotFoundError(f"Le fichier {graph_path} est introuvable. Lancez Graphify d'abord.")
            
        with open(graph_path, "r", encoding="utf-8") as f:
            graph_data = json.load(f)
            
        nodes = graph_data.get("nodes", [])
        code_nodes = [n for n in nodes if n.get("file_type") == "code"]
        
        ids = []
        documents = []
        metadatas = []
        
        for node in code_nodes:
            content = self._extract_node_content(node, code_nodes)
            if not content or len(content) < 10:
                continue # Ignorer les blocs trop petits ou vides
                
            node_id = str(node.get("id"))
            label = node.get("label", "")
            
            # Enrichir le document avec des métadonnées
            doc_text = f"File: {node.get('source_file')}\nSymbol: {label}\nCode:\n{content}"
            
            ids.append(node_id)
            documents.append(doc_text)
            metadatas.append({
                "label": label,
                "source_file": node.get("source_file", ""),
                "source_location": node.get("source_location", "")
            })
            
        if ids:
            batch_size = 100
            for i in range(0, len(ids), batch_size):
                self.collection.upsert(
                    ids=ids[i:i+batch_size],
                    documents=documents[i:i+batch_size],
                    metadatas=metadatas[i:i+batch_size]
                )
            
        return len(ids)

    def search(self, query: str, top_k: int = 3):
        """Recherche hybride (Sémantique) + Expansion de graphe"""
        results = self.collection.query(
            query_texts=[query],
            n_results=top_k
        )
        
        if not results or not results['ids'] or not results['ids'][0]:
            return []
            
        found_ids = results['ids'][0]
        found_docs = results['documents'][0]
        found_metas = results['metadatas'][0]
        
        # Load graph to find neighbors
        graph_path = os.path.join(self.sandbox_root, "graphify-out", "graph.json")
        neighbors_info = {}
        if os.path.exists(graph_path):
            with open(graph_path, "r", encoding="utf-8") as f:
                graph_data = json.load(f)
                links = graph_data.get("links", [])
                nodes_dict = {str(n.get("id")): n for n in graph_data.get("nodes", [])}
                
                for node_id in found_ids:
                    related = []
                    for link in links:
                        if str(link.get("source")) == node_id:
                            target_id = str(link.get("target"))
                            if target_id in nodes_dict:
                                related.append(f"Calls: {nodes_dict[target_id].get('label')}")
                        elif str(link.get("target")) == node_id:
                            source_id = str(link.get("source"))
                            if source_id in nodes_dict:
                                related.append(f"Called by: {nodes_dict[source_id].get('label')}")
                    neighbors_info[node_id] = related

        formatted_results = []
        for i, (node_id, doc, meta) in enumerate(zip(found_ids, found_docs, found_metas)):
            entry = {
                "id": node_id,
                "label": meta.get("label"),
                "file": meta.get("source_file"),
                "location": meta.get("source_location"),
                "content": doc,
                "graph_context": neighbors_info.get(node_id, [])
            }
            formatted_results.append(entry)
            
        return formatted_results
