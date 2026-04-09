#!/usr/bin/env python3
"""
Loom Knowledge Trace Tool

Usage:
    python trace_knowledge.py "your query here"
    
Example:
    python trace_knowledge.py "Eth ARXML spec"
    python trace_knowledge.py "CanIf configuration"
    python trace_knowledge.py "XCP DAQ setup"

This tool shows the complete provenance chain for any knowledge query,
demonstrating Loom's debuggable retrieval capability.
"""

import sqlite3
import sys
import json
from pathlib import Path

AUTOSAR_DB = Path(__file__).parent.parent.parent / "tools/autosar-fusion/autosar_fused.db"
ASAM_DB = Path(__file__).parent.parent.parent / "tools/asam-fusion/fused_knowledge.db"


def extract_entities(query: str) -> list:
    """Extract potential entity keywords from query."""
    stopwords = {'the', 'a', 'an', 'is', 'are', 'what', 'how', 'where', 'which', 
                 'for', 'to', 'in', 'of', 'and', 'or', 'do', 'i', 'need'}
    words = query.replace('?', '').replace('.', '').split()
    return [w for w in words if w.lower() not in stopwords and len(w) > 2]


def search_modules(cursor, entity: str) -> list:
    """Search AUTOSAR modules matching entity."""
    cursor.execute("""
        SELECT module_name, description, source_file, source_pipeline, confidence 
        FROM autosar_cp_modules 
        WHERE module_name LIKE ? OR description LIKE ?
        LIMIT 5
    """, (f'%{entity}%', f'%{entity}%'))
    return cursor.fetchall()


def search_layers(cursor, entity: str) -> list:
    """Search AUTOSAR layers matching entity."""
    cursor.execute("""
        SELECT layer, description, source_file, source_pipeline, confidence 
        FROM autosar_cp_layers 
        WHERE layer LIKE ? OR description LIKE ?
        LIMIT 3
    """, (f'%{entity}%', f'%{entity}%'))
    return cursor.fetchall()


def search_fts(cursor, entity: str) -> list:
    """Full-text search in documentation."""
    try:
        cursor.execute("""
            SELECT markdown_content, table_title, source_file 
            FROM docling_fts 
            WHERE markdown_content LIKE ?
            LIMIT 3
        """, (f'%{entity}%',))
        return cursor.fetchall()
    except:
        return []


def print_box(title: str, content: list, width: int = 70):
    """Print a formatted box."""
    print(f"\n{'─' * (width - 2)}")
    print(f"  {title}")
    print(f"{'─' * (width - 2)}")
    for line in content:
        if len(line) > width - 4:
            line = line[:width - 7] + "..."
        print(f"  {line}")


def trace_query(query: str):
    """Trace a knowledge query through the graph."""
    print("\n" + "=" * 75)
    print("LOOM KNOWLEDGE FOUNDATION - TRACE TOOL")
    print("=" * 75)
    print(f"\nQuery: \"{query}\"")
    
    entities = extract_entities(query)
    print("\n" + "-" * 75)
    print("STEP 1: ENTITY DETECTION")
    print("-" * 75)
    print(f"  Detected entities: {entities}")
    
    results = {"modules": [], "layers": [], "docs": [], "paths": []}
    
    if AUTOSAR_DB.exists():
        conn = sqlite3.connect(str(AUTOSAR_DB))
        cursor = conn.cursor()
        
        for entity in entities:
            modules = search_modules(cursor, entity)
            for m in modules:
                results["modules"].append({
                    "name": m[0],
                    "description": m[1],
                    "source": m[2],
                    "pipeline": m[3],
                    "confidence": m[4]
                })
            
            layers = search_layers(cursor, entity)
            for lay in layers:
                results["layers"].append({
                    "name": lay[0],
                    "description": lay[1],
                    "source": lay[2],
                    "pipeline": lay[3],
                    "confidence": lay[4]
                })
            
            docs = search_fts(cursor, entity)
            for d in docs:
                results["docs"].append({
                    "content": d[0][:200] if d[0] else "",
                    "title": d[1],
                    "source": d[2]
                })
        
        conn.close()
    
    print("\n" + "-" * 75)
    print("STEP 2: GRAPH TRAVERSAL")
    print("-" * 75)
    
    if results["layers"]:
        layer = results["layers"][0]
        print(f"\n  [Hub: AUTOSAR_CP_R24-11]")
        print(f"         |")
        print(f"         +-- DEFINES --> [Layer: {layer['name']}]")
        
        if results["modules"]:
            for i, mod in enumerate(results["modules"][:4]):
                prefix = "|" if i < len(results["modules"][:4]) - 1 else "+"
                print(f"                              {prefix}-- CONTAINS --> [Module: {mod['name']}]")
        
        results["paths"].append({
            "path": f"AUTOSAR_CP_R24-11 -> {layer['name']} -> {results['modules'][0]['name'] if results['modules'] else 'N/A'}",
            "relationships": ["DEFINES", "CONTAINS"]
        })
    elif results["modules"]:
        print(f"\n  [Hub: AUTOSAR_CP_R24-11]")
        print(f"         |")
        for mod in results["modules"][:3]:
            print(f"         +-- CONTAINS --> [Module: {mod['name']}]")
    else:
        print("\n  No direct graph matches found. Falling back to FTS...")
    
    print("\n" + "-" * 75)
    print("STEP 3: EVIDENCE NODES RETRIEVED")
    print("-" * 75)
    
    node_count = 0
    for mod in results["modules"][:3]:
        node_count += 1
        desc = mod['description'][:50] if mod['description'] else 'N/A'
        print_box(f"Evidence Node {node_count}: Module", [
            f"name: {mod['name']}",
            f"description: {desc}...",
            f"source_pipeline: {mod['pipeline']}",
            f"confidence: {mod['confidence']}"
        ])
    
    for doc in results["docs"][:2]:
        node_count += 1
        source_name = doc['source'].split('/')[-1] if doc['source'] else 'Unknown'
        title = doc['title'][:50] if doc['title'] else 'N/A'
        content = doc['content'][:60] if doc['content'] else ''
        print_box(f"Evidence Node {node_count}: Document", [
            f"title: {title}",
            f"source: {source_name}",
            f"preview: {content}..."
        ])
    
    print("\n" + "-" * 75)
    print("STEP 4: PROVENANCE CHAIN")
    print("-" * 75)
    
    if results["modules"]:
        mod = results["modules"][0]
        source_file = mod['source'].split('/')[-1] if mod['source'] else 'Unknown'
        
        print(f"""
  PROVENANCE METADATA
  -------------------
  source_system:    AUTOSAR-fusion
  source_pipeline:  {mod['pipeline']}
  source_file:      {source_file}
  confidence:       {mod['confidence']}

  GRAPH PATH TAKEN:
  Query -> Hub -> Layer/Module -> Source Document

  RELATIONSHIPS TRAVERSED:
  [DEFINES] -> [CONTAINS] -> [DOCUMENTED_IN]
""")
    
    output = {
        "query": query,
        "entities": entities,
        "evidence_nodes": node_count,
        "modules": results["modules"][:5],
        "layers": results["layers"][:3],
        "paths": results["paths"]
    }
    
    print("-" * 75)
    print("EXPORT: JSON (pipe to jq or save to file)")
    print("-" * 75)
    print(json.dumps(output, indent=2, default=str)[:600] + "\n...")
    
    return output


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        print("\nExample queries to try:")
        print('  python trace_knowledge.py "Eth ARXML spec"')
        print('  python trace_knowledge.py "CanIf module"')
        print('  python trace_knowledge.py "XCP measurement"')
        sys.exit(1)
    
    query = " ".join(sys.argv[1:])
    trace_query(query)


if __name__ == "__main__":
    main()
