import os
from neo4j import GraphDatabase
from dotenv import load_dotenv

load_dotenv()

def fix_warfarin_circuit():
    uri = os.getenv("NEO4J_URI")
    user = os.getenv("NEO4J_USERNAME")
    pwd = os.getenv("NEO4J_PASSWORD")
    driver = GraphDatabase.driver(uri, auth=(user, pwd))
    
    query = """
    // 1. Find the VKORC1 protein we extracted earlier
    MATCH (p:Protein {name: 'VKORC1'})
    // 2. Create the Liver Organ node
    MERGE (o:Organ {name: 'Liver'})
    // 3. Link them together
    MERGE (p)-[:EXPRESSED_IN]->(o)
    RETURN p.name, o.name
    """
    
    with driver.session() as session:
        result = session.run(query)
        for record in result:
            print(f"✅ Circuit Closed: {record['p.name']} is now EXPRESSED_IN the {record['o.name']}")
            
    driver.close()

if __name__ == "__main__":
    fix_warfarin_circuit()