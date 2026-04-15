import os
import time
from typing import List
from pydantic import BaseModel, Field
from langchain_google_genai import ChatGoogleGenerativeAI
from neo4j import GraphDatabase
from dotenv import load_dotenv
from src.utils.resolver import get_drug_metadata

load_dotenv()

# --- SCHEMA ---
class BiologicalRelationship(BaseModel):
    target_name: str = Field(description="The gene symbol of the protein target (e.g., PDGFRA)")
    relationship_type: str = Field(description="The action (e.g., INHIBITS, TARGETS, BINDS_TO)")

class ExtractionSchema(BaseModel):
    drug_name: str
    targets: List[BiologicalRelationship]

# --- PRODUCTION RETRY WRAPPER ---
def safe_extract(structured_llm, prompt, max_retries=3):
    """Retries the API call if it hits a rate limit or temporary error."""
    for attempt in range(max_retries):
        try:
            return structured_llm.invoke(prompt)
        except Exception as e:
            if "429" in str(e) or "503" in str(e):
                wait_time = (attempt + 1) * 30  # Wait 30, 60, then 90 seconds
                print(f"⚠️ Rate limited. Sleeping {wait_time}s before retry {attempt + 1}/{max_retries}...")
                time.sleep(wait_time)
            else:
                raise e
    return None

def extract_and_sync_targets(drug_input):
    meta = get_drug_metadata(drug_input)
    if not meta: return

    print(f"🧠 Extracting targets for {meta['canonical_name']}...")
    
    llm = ChatGoogleGenerativeAI(model="gemini-flash-latest", temperature=0)
    structured_llm = llm.with_structured_output(ExtractionSchema)
    
    prompt = f"Identify the primary biological protein targets for the drug {meta['canonical_name']}."
    
    # Use the safety wrapper
    extraction = safe_extract(structured_llm, prompt)
    
    if not extraction:
        print(f"❌ Failed to extract data for {meta['canonical_name']} after retries.")
        return

    driver = GraphDatabase.driver(os.getenv("NEO4J_URI"), auth=(os.getenv("NEO4J_USERNAME"), os.getenv("NEO4J_PASSWORD")))
    with driver.session() as session:
        for t in extraction.targets:
            query = """
            MERGE (d:Drug {cid: $cid})
            SET d.name = $drug_name
            MERGE (p:Protein {name: $p_name})
            MERGE (d)-[:TARGETS]->(p)
            """
            session.run(query, cid=meta['cid'], drug_name=meta['canonical_name'], p_name=t.target_name.upper())
            print(f"✅ Linked {meta['canonical_name']} -> {t.target_name.upper()}")
    driver.close()

if __name__ == "__main__":
    demo_drugs = ["Imatinib", "Metformin", "Amiodarone", "Warfarin"]
    for drug in demo_drugs:
        extract_and_sync_targets(drug)
        time.sleep(10) # Small delay between DIFFERENT drugs to avoid hitting the daily limit too fast