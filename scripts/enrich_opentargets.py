import os
import requests
from neo4j import GraphDatabase
from dotenv import load_dotenv

load_dotenv()

def query_opentargets(symbol):
    """Fetches high-level organ expression for a gene symbol."""
    endpoint = "https://api.platform.opentargets.org/api/v4/graphql"
    query = """
    query targetExpression($symbol: String!) {
      search(querystring: $symbol, entityNames: ["target"], size: 1) {
        hits {
          id
          entity
          ... on Target {
            expressions {
              tissue { label organs }
            }
          }
        }
      }
    }
    """
    response = requests.post(endpoint, json={'query': query, 'variables': {'symbol': symbol}})
    if response.status_code == 200:
        data = response.json()
        try:
            # Extract distinct organs where the protein is expressed
            expressions = data['data']['search']['hits'][0]['expressions']
            organs = set()
            for exp in expressions:
                for organ in exp['tissue']['organs']:
                    organs.add(organ.capitalize())
            return list(organs)
        except (KeyError, IndexError): return []
    return []

def enrich_graph_with_organs():
    driver = GraphDatabase.driver(os.getenv("NEO4J_URI"), auth=(os.getenv("NEO4J_USERNAME"), os.getenv("NEO4J_PASSWORD")))
    
    with driver.session() as session:
        # 1. Get all Protein nodes currently in the graph
        result = session.run("MATCH (p:Entity) WHERE p.name CONTAINS 'protein' OR p.name IN ['ABL1', 'PDGFRA', 'KIT'] RETURN p.name AS name")
        proteins = [record["name"] for record in result]
        
        for protein in proteins:
            print(f"🧬 Enriching {protein}...")
            # Clean name for API (e.g., 'PDGFRA protein' -> 'PDGFRA')
            clean_name = protein.replace(" protein", "").strip()
            organs = query_opentargets(clean_name)
            
            for organ in organs:
                session.run("""
                    MERGE (o:Organ {name: $organ})
                    MATCH (p:Entity {name: $p_name})
                    MERGE (p)-[:EXPRESSED_IN]->(o)
                """, organ=organ, p_name=protein)
                
    driver.close()
    print("✅ Graph Enrichment Complete: Proteins mapped to Organs.")

if __name__ == "__main__":
    enrich_graph_with_organs()