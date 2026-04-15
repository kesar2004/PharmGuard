import os
from neo4j import GraphDatabase
from dotenv import load_dotenv
from src.utils.resolver import get_drug_metadata

load_dotenv()

def sync_demo_drug(drug_name):
    meta = get_drug_metadata(drug_name)
    if not meta: return

    driver = GraphDatabase.driver(os.getenv("NEO4J_URI"), auth=(os.getenv("NEO4J_USERNAME"), os.getenv("NEO4J_PASSWORD")))
    
    with driver.session() as session:
        print(f"🔄 Syncing CID {meta['cid']} to Graph node: {meta['canonical_name']}...")
        
        # This query finds the existing drug node by name and adds the CID anchor
        query = """
        MATCH (d:Drug)
        WHERE d.name =~ '(?i)' + $name
        SET d.cid = $cid, d.canonical_name = $c_name
        RETURN count(d) as updated
        """
        result = session.run(query, name=drug_name, cid=meta['cid'], c_name=meta['canonical_name'])
        summary = result.single()
        print(f"✅ Updated {summary['updated']} nodes for {drug_name}.")
        
    driver.close()

if __name__ == "__main__":
    # Ensure our demo drugs are CID-anchored
    for drug in ["Imatinib", "Lisinopril", "Metformin"]:
        sync_demo_drug(drug)