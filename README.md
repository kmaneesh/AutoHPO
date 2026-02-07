# AutoHPO
AutoHPO is a high-performance, minimal-stack solution for clinical researchers and bioinformaticians. It replaces rigid keyword-based HPO searching with an intelligent, agentic RAG (Retrieval-Augmented Generation) pipeline.

By leveraging Agno for agent orchestration and Meilisearch for lightning-fast vector and keyword indexing, AutoHPO understands clinical context. It doesn't just look for words; it understands the medical intent behind a symptom description.

Key Features
🤖 Agentic Search: Powered by Agno, the system uses an LLM agent to interpret complex clinical notes and map them to the most relevant HPO terms.

⚡ Hybrid Search: Uses Meilisearch for high-speed keyword matching and vector-based semantic search.

🛡️ Resilient Architecture: A "Smart Fallback" design—if the local LLM/Agent instance is unavailable, the UI automatically reverts to a direct, high-speed Meilisearch query.

🪶 Minimalist Stack: Built entirely in Python with a Streamlit frontend; no complex Node.js or heavy database overhead required.

🌐 Local-First: Designed to run on local hardware to maintain data privacy for sensitive clinical queries.

The Stack
Orchestration: Agno

Search Engine: Meilisearch

UI: Streamlit

Data Source: Human Phenotype Ontology (HPO)