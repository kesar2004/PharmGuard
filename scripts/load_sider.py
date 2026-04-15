import os
import pandas as pd
from neo4j import GraphDatabase
from dotenv import load_dotenv
from src.utils.resolver import get_drug_metadata

load_dotenv()

def load_sider_production():
    file_path = "data/meddra_all_se.tsv"
    if not os.path.exists(file_path):
        print("❌ SIDER file missing in data folder.")
        return

    # Load data
    df = pd.read_csv(file_path, sep='\t', header=None, usecols=[2, 5], names=["drug", "se"])
    
    # We'll process the first 50 unique drugs to verify the CID logic works
    unique_drugs = df['drug'].unique()[:50] 
    
    driver = GraphDatabase.driver(
        os.getenv("NEO4J_URI"), 
        auth=(os.getenv("NEO4J_USERNAME"), os.getenv("NEO4J_PASSWORD"))
    )
    
    with driver.session() as session:
        for drug_name in unique_drugs:
            # 1. Resolve Name to CID
            meta = get_drug_metadata(drug_name)
            if not meta:
                continue
            
            print(f"🚀 Processing: {meta['canonical_name']} (CID: {meta['cid']})")
            side_effects = df[df['drug'] == drug_name]['se'].tolist()
            
            # 2. Production-Grade Cypher: Merge on CID, not Name
            query = """
            MERGE (d:Drug {cid: $cid})
            SET d.name = $name, d.formula = $formula
            WITH d
            UNWIND $se_list AS se_name
            MERGE (s:SideEffect {name: se_name})
            MERGE (d)-[:KNOWN_TO_CAUSE]->(s)
            """
            session.run(query, cid=meta['cid'], name=meta['canonical_name'], 
                        formula=meta['formula'], se_list=side_effects)
            
    driver.close()
    print("✅ SIDER Production Ingestion Complete.")

if __name__ == "__main__":
    load_sider_production()