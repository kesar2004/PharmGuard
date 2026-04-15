import os
from pinecone import Pinecone
from dotenv import load_dotenv
import json

load_dotenv()

def check_pinecone_stats():
    print("🔍 Connecting to Pinecone...")
    
    # Initialize Pinecone with your API key
    pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
    
    # Connect to your specific index
    index_name = "pharmaguard-docs"
    index = pc.Index(index_name)
    
    # Fetch the statistics
    stats = index.describe_index_stats()
    
    print("\n📊 --- PINECONE INDEX STATS ---")
    print(f"Total Vectors (Chunks): {stats.total_vector_count}")
    print(f"Index Fullness: {stats.index_fullness * 100}%")
    print(f"Vector Dimension: {stats.dimension}")
    
    # Check what metadata is currently stored (if namespaces/namespaces are used)
    if 'namespaces' in stats and stats.namespaces:
        print("\nNamespace Breakdown:")
        for namespace, ns_stats in stats.namespaces.items():
            name = namespace if namespace else 'Default Namespace'
            print(f" - {name}: {ns_stats.vector_count} vectors")
            
    print("------------------------------\n")

if __name__ == "__main__":
    check_pinecone_stats()