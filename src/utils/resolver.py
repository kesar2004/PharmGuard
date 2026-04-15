import pubchempy as pcp
import time

def get_drug_metadata(drug_name):
    """
    Fetches the PubChem CID and Canonical Name for a drug.
    """
    try:
        # Standardize search to find the most relevant compound
        compounds = pcp.get_compounds(drug_name, "name")
        if compounds:
            compound = compounds[0]
            return {
                "cid": str(compound.cid),
                "canonical_name": compound.synonyms[0].capitalize() if compound.synonyms else drug_name.capitalize(),
                "formula": compound.molecular_formula
            }
    except Exception as e:
        print(f"⚠️ PubChem lookup failed for {drug_name}: {e}")
    
    time.sleep(0.2) # Basic rate-limiting safety
    return None