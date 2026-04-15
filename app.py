import streamlit as st
import streamlit.components.v1 as components
from pyvis.network import Network
from neo4j import GraphDatabase
import os
import re
from dotenv import load_dotenv

# Import the updated multi-hop agent
from scripts.risk_agent import app as risk_agent_app

load_dotenv()

# --- UTILS ---
def format_citations_as_links(text):
    """Converts [PMID: 12345] into clickable PubMed links."""
    if isinstance(text, list):
        text = "".join([str(block.get('text', '')) if isinstance(block, dict) else str(block) for block in text])
    elif not isinstance(text, str):
        text = str(text)
        
    pmid_pattern = r"\[PMID:\s*(\d+)\]"
    return re.sub(pmid_pattern, r"[[PMID: \1](https://pubmed.ncbi.nlm.nih.gov/\1/)]", text)

def render_toxicity_graph(drug1, drug2=None):
    """Renders the causal chain and highlights 'Collisions' if two drugs are selected."""
    uri = os.getenv("NEO4J_URI")
    user = os.getenv("NEO4J_USERNAME")
    pwd = os.getenv("NEO4J_PASSWORD")
    driver = GraphDatabase.driver(uri, auth=(user, pwd))
    
    # Classic Dark Grey Background (IDE Style)
    net = Network(height="550px", width="100%", bgcolor="#121212", font_color="#E0E0E0")
    
    query = """
    MATCH (d:Drug)
    WHERE d.name =~ '(?i).*' + $d1 + '.*' OR ($d2 IS NOT NULL AND d.name =~ '(?i).*' + $d2 + '.*')
    OPTIONAL MATCH (d)-[:TARGETS]->(p:Protein)
    OPTIONAL MATCH (p)-[:EXPRESSED_IN]->(o:Organ)
    RETURN d.name AS drug, p.name AS protein, o.name AS organ
    LIMIT 40
    """
    
    with driver.session() as session:
        result = list(session.run(query, d1=drug1, d2=drug2))
        
        protein_map = {} 
        for r in result:
            if r['protein']:
                protein_map.setdefault(r['protein'], set()).add(r['drug'])

        for record in result:
            d_name = record['drug']
            p_name = record['protein']
            o_name = record['organ']
            
            # 1. Add Drug Node (Muted Rose/Red)
            net.add_node(d_name, label=d_name, title="Drug", color="#E11D48", shape="diamond")
            
            # 2. Add Protein Node
            if p_name:
                is_collision = len(protein_map.get(p_name, set())) > 1
                p_color = "#D97706" if is_collision else "#2563EB" # Amber for collision, Blue for targets
                
                net.add_node(p_name, label=p_name, title="Protein Target", color=p_color)
                net.add_edge(d_name, p_name, color="#404040", label="TARGETS")
                
                # 3. Add Organ Node (Emerald)
                if o_name:
                    net.add_node(o_name, label=o_name, title="Organ Expression", color="#059669", shape="dot")
                    net.add_edge(p_name, o_name, color="#404040", label="EXPRESSED_IN")

    # Stable Physics
    net.set_options("""
    var options = {
      "physics": {
        "forceAtlas2Based": { "gravitationalConstant": -50, "centralGravity": 0.01, "springLength": 100, "springConstant": 0.08 },
        "maxVelocity": 50,
        "solver": "forceAtlas2Based",
        "timestep": 0.35,
        "stabilization": { "iterations": 150 }
      },
      "edges": { "smooth": { "type": "continuous" } }
    }
    """)
            
    driver.close()
    path = "graph.html"
    net.save_graph(path)
    with open(path, "r", encoding="utf-8") as f:
        return f.read()

# --- UI LAYOUT ---
st.set_page_config(page_title="PharmaGuard", layout="wide", initial_sidebar_state="expanded")

# --- ENTERPRISE CSS INJECTION ---
st.markdown("""
    <style>
    /* Import Inter font for a clean, modern look */
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Inter', sans-serif;
    }
    
    /* Main background - Classic Dark Grey */
    .stApp { background-color: #121212; color: #E0E0E0; }
    
    /* Custom App Header */
    .app-header {
        font-size: 2.2rem;
        font-weight: 700;
        color: #F8FAFC;
        margin-bottom: 4px;
        letter-spacing: -0.02em;
    }
    .app-subtitle {
        color: #94A3B8;
        font-size: 1.05rem;
        font-weight: 400;
        margin-bottom: 24px;
        border-bottom: 1px solid #333333;
        padding-bottom: 20px;
    }
    
    /* Custom Card Styling - Slightly lighter grey for depth */
    .report-card {
        background-color: #1E1E1E;
        border: 1px solid #333333;
        border-left: 4px solid #3B82F6; /* Professional Blue Accent */
        padding: 24px;
        border-radius: 6px;
        color: #D1D5DB;
        line-height: 1.6;
        font-size: 0.95rem;
    }
    
    /* Primary Button Styling */
    .stButton>button {
        background-color: #2563EB;
        color: white;
        border-radius: 6px;
        border: 1px solid #1D4ED8;
        width: 100%;
        font-weight: 600;
        height: 2.8em;
        transition: all 0.2s ease-in-out;
    }
    .stButton>button:hover {
        background-color: #1D4ED8;
        border-color: #1E40AF;
    }
    
    /* Sidebar text colors */
    .stSelectbox label, .stCheckbox label, .stToggle label { 
        color: #E0E0E0 !important; 
        font-weight: 500;
    }
    
    /* Hide Streamlit default UI elements */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    </style>
""", unsafe_allow_html=True)

# Clean Hero Header
st.markdown("<div class='app-header'>PharmaGuard</div>", unsafe_allow_html=True)
st.markdown("<div class='app-subtitle'>Agentic GraphRAG • Causal Discovery & Regulatory Risk Intelligence</div>", unsafe_allow_html=True)

with st.sidebar:
    st.markdown("### Configuration")
    
    demo_drugs = ["Imatinib", "Warfarin", "Amiodarone", "Metformin", "Lisinopril"]
    target_drug = st.selectbox("Primary Drug", options=demo_drugs, index=0)
    
    with st.expander("Advanced Analysis Settings", expanded=False):
        use_ddi = st.checkbox("Drug-Drug Interaction (DDI)")
        discovery_mode = st.toggle("Zero-Day Discovery Mode", value=True)
        st.caption("Cross-references PubMed against SIDER to find clinical blind spots.")
    
    target_drug_2 = ""
    if use_ddi:
        available_second_drugs = [d for d in demo_drugs if d != target_drug]
        target_drug_2 = st.selectbox("Comparison Drug", options=available_second_drugs, index=0)
    
    st.markdown("---")
    st.caption("System Status: Connected to Neo4j & Pinecone Cluster")
    
    analyze_btn = st.button("Run Analysis")

if analyze_btn:
    col_graph, col_report = st.columns([1.2, 1])
    
    with st.spinner("Executing agentic traversal and peer review..."):
        # 1. Run Agent
        payload = {"drug_name": target_drug, "drug_name_2": target_drug_2}
        agent_output = risk_agent_app.invoke(payload)
        
        # 2. Graph Column
        with col_graph:
            st.markdown("### Causal Pathway")
            graph_html = render_toxicity_graph(target_drug, target_drug_2 if use_ddi else None)
            components.html(graph_html, height=565)
            
        # 3. Report Column
        with col_report:
            st.markdown("### Risk Report")
            
            if agent_output.get("is_validated"):
                st.success(f"Peer-Reviewed & Validated: {agent_output.get('validation_notes', 'Evidence supports claims.')}")
            else:
                st.error(f"Validation Failed: {agent_output.get('validation_notes', 'Potential hallucination detected.')}")
            
            formatted_report = format_citations_as_links(agent_output["risk_report"])
            st.markdown(f'<div class="report-card">{formatted_report}</div>', unsafe_allow_html=True)
            
            if agent_output.get("literature_context"):
                with st.expander("View Supporting Literature"):
                    for lit in agent_output["literature_context"]:
                        st.caption(format_citations_as_links(lit))