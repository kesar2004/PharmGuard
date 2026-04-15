import os
from dotenv import load_dotenv
from langchain_community.document_loaders import PubMedLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_huggingface import HuggingFaceEmbeddings
from pinecone import Pinecone
from src.utils.resolver import get_drug_metadata

load_dotenv()

def ingest_pubmed_production(drug_name="Imatinib"):
    # 1. Resolve Name to CID to keep Vector DB in sync with Graph DB
    meta = get_drug_metadata(drug_name)
    if not meta:
        print(f"❌ Could not resolve metadata for {drug_name}. Skipping.")
        return

    print(f"📥 Fetching PubMed abstracts for {meta['canonical_name']}...")
    # We search by name but store by CID
    loader = PubMedLoader(query=f"{drug_name} toxicity", load_max_docs=20)
    docs = loader.load()

    # 2. Strategic Chunking (800 chars is the "sweet spot" for abstracts)
    text_splitter = RecursiveCharacterTextSplitter(chunk_size=800, chunk_overlap=150)
    chunks = text_splitter.split_documents(docs)

    embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
    pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
    index = pc.Index("pharmaguard-docs")

    print(f"🚀 Pushing {len(chunks)} vectors with CID and PMID tracking...")
    for i in range(0, len(chunks), 50):
        batch = chunks[i:i + 50]
        texts = [doc.page_content for doc in batch]
        embeds = embeddings.embed_documents(texts)
        
        records = []
        for j, doc in enumerate(batch):
            # CID links to Neo4j; PMID provides the citation link
            pmid = doc.metadata.get('uid', 'N/A')
            record_id = f"CID-{meta['cid']}-PMID-{pmid}-{i+j}"
            
            metadata = {
                "text": doc.page_content,
                "drug_cid": meta['cid'],
                "pmid": pmid,
                "source_url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                "source": "PubMed"
            }
            records.append((record_id, embeds[j], metadata))
        
        index.upsert(vectors=records)
    
    print(f"🎉 SUCCESS: {meta['canonical_name']} literature is now verifiable in Pinecone.")

# ✅ CORRECT
if __name__ == "__main__":
    ingest_pubmed_production("Warfarin")