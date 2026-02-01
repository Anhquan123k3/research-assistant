"""
Graph Algorithms Module for Knowledge Graph
Provides advanced graph analysis without requiring AI APIs.
"""

import networkx as nx
from typing import Dict, List, Tuple, Set, Optional
from collections import defaultdict
from sklearn.cluster import KMeans
from sklearn.feature_extraction.text import TfidfVectorizer
import numpy as np


class GraphAnalyzer:
    """Analyzes document relationships and computes graph metrics."""
    
    def __init__(self, nodes: List[dict], links: List[dict]):
        """
        Initialize graph analyzer.
        
        Args:
            nodes: List of document nodes with id, name, tags
            links: List of connections with source, target, value, common_tags
        """
        self.nodes = nodes
        self.links = links
        self.graph = self._build_networkx_graph()
        
    def _build_networkx_graph(self) -> nx.Graph:
        """Build NetworkX graph from nodes and links."""
        G = nx.Graph()
        
        # Add nodes
        for node in self.nodes:
            G.add_node(node['id'], **node)
            
        # Add edges
        for link in self.links:
            G.add_edge(
                link['source'], 
                link['target'], 
                weight=link['value'],
                common_tags=link.get('common_tags', [])
            )
            
        return G
    
    def compute_pagerank(self, damping: float = 0.85) -> Dict[str, float]:
        """
        Compute PageRank for all nodes.
        
        Args:
            damping: Damping factor (default 0.85)
            
        Returns:
            Dictionary mapping node_id to PageRank score
        """
        if len(self.graph.nodes) == 0:
            return {}
            
        try:
            pagerank = nx.pagerank(self.graph, alpha=damping, weight='weight')
            return pagerank
        except:
            # If graph has no edges, return uniform distribution
            num_nodes = len(self.graph.nodes)
            return {node: 1.0/num_nodes for node in self.graph.nodes}
    
    def compute_centrality_metrics(self) -> Dict[str, Dict[str, float]]:
        """
        Compute various centrality metrics.
        
        Returns:
            Dictionary with 'degree', 'betweenness', 'closeness' metrics
        """
        metrics = {
            'degree': {},
            'betweenness': {},
            'closeness': {}
        }
        
        if len(self.graph.nodes) == 0:
            return metrics
        
        # Degree centrality
        metrics['degree'] = nx.degree_centrality(self.graph)
        
        # Betweenness centrality (only if connected)
        if nx.is_connected(self.graph):
            metrics['betweenness'] = nx.betweenness_centrality(self.graph, weight='weight')
            metrics['closeness'] = nx.closeness_centrality(self.graph, distance='weight')
        else:
            # For disconnected graphs, compute per component
            for component in nx.connected_components(self.graph):
                subgraph = self.graph.subgraph(component)
                if len(subgraph.nodes) > 1:
                    between = nx.betweenness_centrality(subgraph, weight='weight')
                    close = nx.closeness_centrality(subgraph, distance='weight')
                    metrics['betweenness'].update(between)
                    metrics['closeness'].update(close)
                else:
                    # Single node component
                    node = list(component)[0]
                    metrics['betweenness'][node] = 0.0
                    metrics['closeness'][node] = 0.0
        
        return metrics
    
    def find_shortest_path(self, source: str, target: str) -> Optional[List[str]]:
        """
        Find shortest path between two nodes.
        
        Args:
            source: Source node ID
            target: Target node ID
            
        Returns:
            List of node IDs forming the path, or None if no path exists
        """
        try:
            path = nx.shortest_path(self.graph, source, target, weight='weight')
            return path
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            return None
    
    def find_all_paths(self, source: str, target: str, cutoff: int = 5) -> List[List[str]]:
        """
        Find all simple paths between two nodes up to a cutoff length.
        
        Args:
            source: Source node ID
            target: Target node ID
            cutoff: Maximum path length
            
        Returns:
            List of paths (each path is a list of node IDs)
        """
        try:
            paths = list(nx.all_simple_paths(self.graph, source, target, cutoff=cutoff))
            return paths
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            return []
    
    def detect_communities(self) -> List[Set[str]]:
        """
        Detect communities/clusters in the graph using Louvain algorithm.
        
        Returns:
            List of communities (each community is a set of node IDs)
        """
        try:
            communities = nx.community.louvain_communities(self.graph, weight='weight')
            return communities
        except:
            # Fallback: each node is its own community
            return [{node} for node in self.graph.nodes]
    
    def compute_network_density(self) -> float:
        """Compute network density (ratio of actual to possible edges)."""
        if len(self.graph.nodes) < 2:
            return 0.0
        return nx.density(self.graph)
    
    def get_top_connected_nodes(self, n: int = 5) -> List[Tuple[str, int]]:
        """
        Get top N most connected nodes.
        
        Args:
            n: Number of top nodes to return
            
        Returns:
            List of (node_id, degree) tuples
        """
        degrees = dict(self.graph.degree())
        sorted_nodes = sorted(degrees.items(), key=lambda x: x[1], reverse=True)
        return sorted_nodes[:n]


class TagIndexer:
    """Manages inverted index for efficient tag-based queries."""
    
    def __init__(self):
        self.tag_to_docs: Dict[str, Set[str]] = defaultdict(set)
        self.doc_to_tags: Dict[str, Set[str]] = defaultdict(set)
        
    def build_index(self, highlights: List[dict]) -> None:
        """
        Build inverted index from highlights.
        
        Args:
            highlights: List of highlight objects with doc_id and tag
        """
        self.tag_to_docs.clear()
        self.doc_to_tags.clear()
        
        for h in highlights:
            doc_id = h.get('doc_id')
            tag = h.get('tag', '')
            
            if not doc_id or not tag:
                continue
                
            # Clean tag (remove "Note: " prefix)
            clean_tag = tag.replace('Note: ', '').strip()
            if not clean_tag:
                continue
                
            self.tag_to_docs[clean_tag].add(doc_id)
            self.doc_to_tags[doc_id].add(clean_tag)
    
    def get_docs_by_tag(self, tag: str) -> Set[str]:
        """Get all document IDs containing a specific tag."""
        return self.tag_to_docs.get(tag, set())
    
    def get_tags_by_doc(self, doc_id: str) -> Set[str]:
        """Get all tags for a specific document."""
        return self.doc_to_tags.get(doc_id, set())
    
    def find_common_tags(self, doc_id1: str, doc_id2: str) -> Set[str]:
        """Find tags common to two documents."""
        tags1 = self.doc_to_tags.get(doc_id1, set())
        tags2 = self.doc_to_tags.get(doc_id2, set())
        return tags1.intersection(tags2)
    
    def compute_tag_frequency(self) -> Dict[str, int]:
        """Compute frequency of each tag across all documents."""
        return {tag: len(docs) for tag, docs in self.tag_to_docs.items()}
    
    def get_all_tags(self) -> List[str]:
        """Get list of all unique tags."""
        return list(self.tag_to_docs.keys())


class TagClusterer:
    """Clusters documents based on tag similarity."""
    
    def __init__(self, indexer: TagIndexer):
        self.indexer = indexer
        
    def cluster_by_dominant_tag(self, nodes: List[dict]) -> List[dict]:
        """
        Cluster nodes by their most frequent tag.
        
        Args:
            nodes: List of node dictionaries with tags
            
        Returns:
            List of cluster dictionaries with id, docs, label, color
        """
        # Count tag frequencies
        tag_freq = self.indexer.compute_tag_frequency()
        
        # Assign each node to cluster based on most frequent tag
        tag_to_nodes = defaultdict(list)
        for node in nodes:
            node_tags = node.get('tags', [])
            if not node_tags:
                tag_to_nodes['Uncategorized'].append(node['id'])
                continue
                
            # Find most frequent tag for this node
            best_tag = max(node_tags, key=lambda t: tag_freq.get(t, 0))
            tag_to_nodes[best_tag].append(node['id'])
        
        # Create cluster objects
        clusters = []
        color_palette = [
            '#3b82f6',  # blue
            '#10b981',  # green
            '#f59e0b',  # amber
            '#ec4899',  # pink
            '#8b5cf6',  # purple
            '#6366f1',  # indigo
            '#ef4444',  # red
            '#14b8a6',  # teal
            '#f97316',  # orange
            '#64748b',  # slate (for uncategorized)
        ]
        
        for idx, (tag, doc_ids) in enumerate(tag_to_nodes.items()):
            clusters.append({
                'id': idx,
                'docs': doc_ids,
                'label': tag,
                'color': color_palette[idx % len(color_palette)],
                'size': len(doc_ids)
            })
        
        return clusters
    
    def cluster_by_kmeans(self, nodes: List[dict], n_clusters: int = 5) -> List[dict]:
        """
        Cluster nodes using K-means on tag vectors.
        
        Args:
            nodes: List of node dictionaries with tags
            n_clusters: Number of clusters to create
            
        Returns:
            List of cluster dictionaries
        """
        if len(nodes) < n_clusters:
            n_clusters = max(1, len(nodes))
        
        # Create tag vectors using TF-IDF
        documents = []
        node_ids = []
        for node in nodes:
            tags = node.get('tags', [])
            if tags:
                documents.append(' '.join(tags))
                node_ids.append(node['id'])
        
        if len(documents) < 2:
            # Not enough data for clustering
            return self.cluster_by_dominant_tag(nodes)
        
        try:
            vectorizer = TfidfVectorizer()
            X = vectorizer.fit_transform(documents)
            
            kmeans = KMeans(n_clusters=min(n_clusters, len(documents)), random_state=42)
            labels = kmeans.fit_predict(X)
            
            # Group nodes by cluster
            cluster_to_nodes = defaultdict(list)
            for node_id, label in zip(node_ids, labels):
                cluster_to_nodes[label].append(node_id)
            
            # Create cluster objects
            clusters = []
            for cluster_id, doc_ids in cluster_to_nodes.items():
                # Find most common tag in cluster
                all_tags = []
                for doc_id in doc_ids:
                    node = next((n for n in nodes if n['id'] == doc_id), None)
                    if node:
                        all_tags.extend(node.get('tags', []))
                
                if all_tags:
                    label = max(set(all_tags), key=all_tags.count)
                else:
                    label = f"Cluster {cluster_id}"
                
                clusters.append({
                    'id': int(cluster_id),
                    'docs': doc_ids,
                    'label': label,
                    'size': len(doc_ids)
                })
            
            return clusters
        except:
            # Fallback to dominant tag clustering
            return self.cluster_by_dominant_tag(nodes)


def optimize_graph_computation(docs: List[dict], highlights: List[dict]) -> Tuple[List[dict], List[dict], TagIndexer]:
    """
    Optimized graph computation using inverted index.
    O(n*m) instead of O(n²) where m = average tags per document.
    
    Args:
        docs: List of document dictionaries
        highlights: List of highlight dictionaries
        
    Returns:
        Tuple of (nodes, links, indexer)
    """
    # Build inverted index
    indexer = TagIndexer()
    indexer.build_index(highlights)
    
    # Create nodes
    nodes = []
    for doc in docs:
        doc_id = doc['id']
        tags = list(indexer.get_tags_by_doc(doc_id))
        nodes.append({
            'id': doc_id,
            'name': doc['filename'],
            'tags': tags
        })
    
    # Create links using inverted index (optimized)
    links = []
    processed_pairs = set()
    
    # For each tag, connect all documents that share it
    for tag, doc_ids in indexer.tag_to_docs.items():
        doc_list = list(doc_ids)
        
        # Connect all pairs within this tag group
        for i in range(len(doc_list)):
            for j in range(i + 1, len(doc_list)):
                doc1, doc2 = doc_list[i], doc_list[j]
                pair = tuple(sorted([doc1, doc2]))
                
                if pair in processed_pairs:
                    # Already have a link, add this tag to common_tags
                    for link in links:
                        if (link['source'], link['target']) == pair or (link['target'], link['source']) == pair:
                            link['common_tags'].append(tag)
                            link['value'] += 1
                            break
                else:
                    # Create new link
                    links.append({
                        'source': doc1,
                        'target': doc2,
                        'value': 1,
                        'common_tags': [tag]
                    })
                    processed_pairs.add(pair)
    
    return nodes, links, indexer
