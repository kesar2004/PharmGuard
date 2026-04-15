import os
import json
from dotenv import load_dotenv
from typing import TypedDict, List, Optional
from langgraph.graph import StateGraph, START, END
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_huggingface import HuggingFaceEmbeddings
from neo4j import GraphDatabase
from pinecone import Pinecone
from src.utils.resolver import get_drug_metadata

load_dotenv()

# 1. Production State Definition
class AgentState(TypedDict):
    drug_name: str
    drug_name_2: str  
    drug_cid: str
    drug_cid_2: str   
    mechanistic_paths: List[str]  
    clinical_history: List[str]   
    literature_context: List[str] 
    risk_report: str
    is_validated: bool
    validation_notes: str

# 2. Node: Entity Resolver
def resolve_entity(state: AgentState):
    print(f"🔍 1. Resolving CIDs...")
    meta1 = get_drug_metadata(state['drug_name'])
    cid1 = meta1['cid'] if meta1 else "Unknown"
    name1 = meta1['canonical_name'] if meta1 else state['drug_name']
    
    cid2 = ""
    name2 = state.get('drug_name_2', "")
    if name2:
        meta2 = get_drug_metadata(name2)
        cid2 = meta2['cid'] if meta2 else "Unknown"
        name2 = meta2['canonical_name'] if meta2 else name2
        
    return {"drug_cid": cid1, "drug_name": name1, "drug_cid_2": cid2, "drug_name_2": name2}

# 3. Node: Mechanistic Researcher (Neo4j)
def fetch_biological_paths(state: AgentState):
    cids = [state['drug_cid']]
    if state.get('drug_cid_2'):
        cids.append(state['drug_cid_2'])
        
    if cids == ["Unknown"]: return {"mechanistic_paths": []}
    
    print(f"🧬 2. Mapping biological pathways...")
    driver = GraphDatabase.driver(os.getenv("NEO4J_URI"), auth=(os.getenv("NEO4J_USERNAME"), os.getenv("NEO4J_PASSWORD")))
    
    query = """
    MATCH (d:Drug)-[:TARGETS]->(p:Protein)-[:EXPRESSED_IN]->(o:Organ)
    WHERE d.cid IN $cids
    RETURN d.name AS drug, p.name AS protein, o.name AS organ
    """
    paths = []
    with driver.session() as session:
        result = session.run(query, cids=cids)
        paths = [f"Drug {r['drug']} targets {r['protein']}, which is expressed in the {r['organ']}." for r in result]
    
    driver.close()
    return {"mechanistic_paths": paths}

# 4. Node: Clinical Auditor (Neo4j)
def fetch_clinical_history(state: AgentState):
    cids = [state['drug_cid']]
    if state.get('drug_cid_2'):
        cids.append(state['drug_cid_2'])
        
    if cids == ["Unknown"]: return {"clinical_history": []}
    
    print(f"📋 3. Auditing SIDER clinical data...")
    driver = GraphDatabase.driver(os.getenv("NEO4J_URI"), auth=(os.getenv("NEO4J_USERNAME"), os.getenv("NEO4J_PASSWORD")))
    
    query = """
    MATCH (d:Drug)-[:KNOWN_TO_CAUSE]->(s:SideEffect) 
    WHERE d.cid IN $cids
    RETURN d.name AS drug, s.name AS se
    """
    effects = []
    with driver.session() as session:
        result = session.run(query, cids=cids)
        effects = [f"Drug {r['drug']} is known to cause {r['se']}" for r in result]
    
    driver.close()
    return {"clinical_history": effects}

# 5. Node: Literature Searcher (Pinecone)
def fetch_pubmed_context(state: AgentState):
    print(f"📚 4. Retrieving verifiable evidence from Pinecone...")
    embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
    pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
    index = pc.Index("pharmaguard-docs")
    
    context = []
    
    if state['drug_cid'] != "Unknown":
        q1 = embeddings.embed_query(f"Toxicity of {state['drug_name']}")
        res1 = index.query(vector=q1, top_k=5, include_metadata=True, filter={"drug_cid": {"$eq": state['drug_cid']}})
        context.extend([f"[{state['drug_name']}] [PMID: {m.metadata['pmid']}] {m.metadata['text']}" for m in res1.matches])
        
    if state.get('drug_cid_2') and state['drug_cid_2'] != "Unknown":
        q2 = embeddings.embed_query(f"Toxicity of {state['drug_name_2']}")
        res2 = index.query(vector=q2, top_k=5, include_metadata=True, filter={"drug_cid": {"$eq": state['drug_cid_2']}})
        context.extend([f"[{state['drug_name_2']}] [PMID: {m.metadata['pmid']}] {m.metadata['text']}" for m in res2.matches])

    return {"literature_context": context}


# 6. Node: Red-Team Reasoner
def generate_risk_report(state: AgentState):
    print("🧠 5. Synthesizing 'Red-Flag' Report with Citations...")
    llm = ChatGoogleGenerativeAI(model="gemini-flash-latest", temperature=0.0) # Lowered temp to 0.0 for stricter adherence
    
    is_ddi = bool(state.get('drug_name_2'))
    drug_target_str = f"Analyze Drug: {state['drug_name']}"
    if is_ddi:
        drug_target_str += f"\nSecondary Drug for DDI Analysis: {state['drug_name_2']}"
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", """You are an elite Pharmaceutical Safety Auditor. Your goal is a high-density, structured report. Do not use emojis.
        
        CRITICAL STRICT-GROUNDING RULES:
        1. ZERO OUTSIDE KNOWLEDGE: You must ONLY use the provided Neo4j, SIDER, and PubMed text. 
        2. NO ENHANCEMENTS: Do not add CIDs, disease background (e.g., 'Philadelphia chromosome'), or expand acronyms unless they are explicitly written in the provided text. Use the exact text provided.
        3. NO EDITORIALIZING: Do not make interpretive claims (e.g., do not say 'this is a failure in reporting'). Simply state the factual discrepancy between the literature and SIDER.
        4. CITE SOURCES: You MUST use [PMID: XXX] tags for every scientific claim.
        
        REPORT STRUCTURE (Markdown headers):
        ### EXECUTIVE SUMMARY
        ### MECHANISTIC DISCOVERY
        ### EVIDENCE & CITATIONS
        ### ZERO-DAY DISCREPANCY
        """),
        ("human", f"""
        {drug_target_str}
        
        Mechanistic Pathways (Neo4j):
        {{mech}}
        
        Official Clinical Side Effects (SIDER):
        {{clin}}
        
        Scientific Literature (PubMed):
        {{lit}}
        """)
    ])
    
    chain = prompt | llm
    report = chain.invoke({
        "mech": "\n".join(state['mechanistic_paths']),
        "clin": "\n".join(state['clinical_history'][:30]) if state['clinical_history'] else "NONE DOCUMENTED",
        "lit": "\n\n".join(state['literature_context'])
    })
    return {"risk_report": report.content}

# 7. Node: Peer-Review Validator
def validate_report(state: AgentState):
    print("⚖️ 6. Peer-Reviewing Report (Validation Node)...")
    llm = ChatGoogleGenerativeAI(model="gemini-flash-latest", temperature=0)
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", """You are a Senior Pharmaceutical Toxicologist. 
        Review the report against the PROVIDED EVIDENCE.
        
        EVIDENCE SOURCES:
        1. Neo4j Pathways: Contains biological targets and organ expressions.
        2. PubMed Literature: Contains scientific abstracts.
        3. SIDER Database: Contains official clinical side effects.
        
        If the report makes a claim not supported by ANY of these three sources, reject it.
        Respond ONLY with a JSON object: {{"is_validated": bool, "notes": "string"}}. """),
        ("human", "NEO4J PATHWAYS:\n{mech}\n\nLITERATURE EVIDENCE:\n{lit}\n\nSIDER CLINICAL LABELS:\n{clin}\n\nPROPOSED REPORT:\n{report}")
    ])
    
    chain = prompt | llm
    
    try:
        raw_content = chain.invoke({
            "mech": "\n".join(state['mechanistic_paths']) if state['mechanistic_paths'] else "NO PATHWAYS DETECTED",
            "lit": "\n".join(state['literature_context']),
            "clin": "\n".join(state['clinical_history']) if state['clinical_history'] else "NONE DOCUMENTED",
            "report": state['risk_report']
        }).content
        
        if isinstance(raw_content, list):
            response_text = "".join([str(block.get('text', '')) if isinstance(block, dict) else str(block) for block in raw_content])
        else:
            response_text = str(raw_content)
            
        clean_json = response_text.replace('```json', '').replace('```', '').strip()
        result = json.loads(clean_json)
        
        is_valid = result.get('is_validated', False)
        notes = result.get('notes', 'N/A')
    except Exception as e:
        is_valid = False
        notes = f"Validation error: {e}"

    return {"is_validated": is_valid, "validation_notes": notes}

# 8. Build the Production Graph
builder = StateGraph(AgentState)
builder.add_node("resolve", resolve_entity)
builder.add_node("get_paths", fetch_biological_paths)
builder.add_node("get_side_effects", fetch_clinical_history)
builder.add_node("get_pubmed", fetch_pubmed_context)
builder.add_node("reasoner", generate_risk_report)
builder.add_node("validator", validate_report) 

builder.add_edge(START, "resolve")
builder.add_edge("resolve", "get_paths")
builder.add_edge("get_paths", "get_side_effects")
builder.add_edge("get_side_effects", "get_pubmed")
builder.add_edge("get_pubmed", "reasoner")
builder.add_edge("reasoner", "validator") 
builder.add_edge("validator", END) 

app = builder.compile()