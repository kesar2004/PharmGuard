import os
from neo4j import GraphDatabase
from dotenv import load_dotenv

load_dotenv()

def seed_imatinib_targets():
    uri = os.getenv("NEO4J_URI")
    user = os.getenv("NEO4J_USERNAME")
    pwd = os.getenv("NEO4J_PASSWORD")
    driver = GraphDatabase.driver(uri, auth=(user, pwd))
    
    targets = ["ABL1", "PDGFRA", "KIT", "CSF1R"]
    
    with driver.session() as session:
        print("🌱 Seeding Imatinib targets into Neo4j...")
        
        # 1. Clean up the 'Protein/SideEffect' collision
        session.run("MATCH (n:Protein) REMOVE n:SideEffect, n:Entity")
        
        # 2. Force create the Imatinib -> Protein links
        for target in targets:
            session.run("""
                MERGE (d:Drug {name: 'Imatinib'})
                MERGE (p:Protein {name: $p_name})
                MERGE (d)-[:TARGETS]->(p)
            """, p_name=target)
            
    driver.close()
    print("✅ Biological skeleton seeded.")

if __name__ == "__main__":
    seed_imatinib_targets()