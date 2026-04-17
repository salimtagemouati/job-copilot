# Sample JD fixtures for testing
# Used by tests to avoid real LLM calls

MOROCCO_AI_JD = """
Company: Atlas Intelligence
Location: Casablanca, Morocco (Hybrid)

Poste: Ingénieur IA Junior

Nous cherchons un ingénieur IA junior passionné pour rejoindre notre équipe en croissance.

Responsabilités:
- Développer et déployer des pipelines RAG pour nos clients enterprise
- Intégrer des LLMs (OpenAI, Anthropic, Google Gemini) dans des applications métier
- Construire des APIs REST avec FastAPI
- Travailler avec des bases de données vectorielles (FAISS, Chroma)

Requis:
- Python 3.10+ (maîtrise requise)
- Expérience avec les LLMs et prompt engineering
- FastAPI ou Flask
- SQL (PostgreSQL ou SQLite)
- 0-2 ans d'expérience
- Diplôme en informatique, data science ou équivalent

Atouts:
- Connaissance de Docker
- React ou Vue.js pour des dashboards simples
- Expérience avec Supabase ou Firebase

Salaire: 8 000 – 12 000 MAD / mois
Langue de travail: Français / Arabe
"""

GERMANY_ENGLISH_JD = """
Company: Personio
Location: Munich, Germany (Hybrid)

Junior Machine Learning Engineer

About the team:
We're building HR software used by 10,000+ companies. Our ML team works fully in English.
We are an international team of engineers from 30+ countries.
English is the working language.

What you'll do:
- Build and maintain ML models for HR analytics
- Work with Python, scikit-learn, and PyTorch
- Design APIs for model serving with FastAPI
- Collaborate with product teams on AI feature development

Requirements:
- Python (strong)
- Experience with ML frameworks (scikit-learn, PyTorch, or TensorFlow)
- FastAPI or Flask for model serving
- 0-2 years experience
- English fluency

Nice to have:
- Docker and Kubernetes basics
- MLflow for experiment tracking
- AWS or GCP basics

Salary: €45,000 – €60,000/year
Visa sponsorship available. Relocation support provided.
"""

GERMANY_REJECTED_JD = """
Unternehmen: TechFirma GmbH
Ort: Berlin, Deutschland

Wir suchen einen KI-Ingenieur für unser Team.

Anforderungen:
- Deutschkenntnisse erforderlich (C1 oder besser)
- Python, TensorFlow
- Muttersprachler bevorzugt
- 2-4 Jahre Erfahrung

Bitte bewerben Sie sich nur wenn Sie fließend Deutsch sprechen.
"""

REMOTE_JD = """
Company: Hugging Face
Location: Remote — Worldwide

Junior Developer Advocate / ML Engineer

We're open to international contractors worldwide.

About the role:
Join our ecosystem team to help developers build with transformers, diffusers, and PEFT.

Requirements:
- Python (strong)
- Familiarity with transformer architectures
- FastAPI or Flask for demos and integrations
- Strong written English
- 0-3 years experience

Nice to have:
- PyTorch training experience
- Gradio or Streamlit for ML demos
- Open source contributions

Compensation: $60,000 – $80,000 USD/year
Remote: Yes (worldwide, open to international contractors)
"""

SENIOR_JD_SHOULD_SKIP = """
Company: DeepMind
Location: London, UK / Remote EU

Senior ML Research Engineer

Requirements:
- PhD in Machine Learning, Computer Science, or related field
- 7+ years of production ML experience
- PyTorch, JAX, and distributed training at scale
- Published research in top venues (NeurIPS, ICML, ICLR)
- MLOps: Kubernetes, Vertex AI, or SageMaker at scale
- Google Cloud certifications strongly preferred

We require 5+ years minimum hands-on ML engineering.
"""

# Pre-built ParsedJob dicts for unit testing (no LLM needed)
PARSED_JOB_MOROCCO = {
    "company": "Atlas Intelligence",
    "role": "Ingénieur IA Junior",
    "location": "Casablanca, Morocco",
    "market": "morocco",
    "remote_ok": True,
    "language_required": "French",
    "jd_language": "French",
    "requirements": ["Python 3.10+", "LLMs", "FastAPI", "SQL", "0-2 ans expérience"],
    "nice_to_have": ["Docker", "React", "Supabase"],
    "tech_stack": ["Python", "FastAPI", "FAISS", "PostgreSQL"],
    "seniority": "junior",
    "visa_sponsorship": None,
    "salary_range": "8 000 – 12 000 MAD / mois",
    "raw_text": MOROCCO_AI_JD,
    "source_url": None,
}

PARSED_JOB_GERMANY = {
    "company": "Personio",
    "role": "Junior Machine Learning Engineer",
    "location": "Munich, Germany",
    "market": "germany",
    "remote_ok": True,
    "language_required": "English",
    "jd_language": "English",
    "requirements": ["Python", "ML frameworks", "FastAPI", "0-2 years experience"],
    "nice_to_have": ["Docker", "MLflow", "AWS"],
    "tech_stack": ["Python", "PyTorch", "scikit-learn", "FastAPI"],
    "seniority": "junior",
    "visa_sponsorship": True,
    "salary_range": "€45,000 – €60,000/year",
    "raw_text": GERMANY_ENGLISH_JD,
    "source_url": None,
}

PARSED_JOB_SENIOR = {
    "company": "DeepMind",
    "role": "Senior ML Research Engineer",
    "location": "London, UK",
    "market": "remote",
    "remote_ok": True,
    "language_required": "English",
    "jd_language": "English",
    "requirements": [
        "PhD preferred",
        "7+ years production ML experience",
        "PyTorch, JAX",
        "Published research",
        "Google Cloud certs",
    ],
    "nice_to_have": [],
    "tech_stack": ["Python", "PyTorch", "JAX", "Kubernetes", "Vertex AI"],
    "seniority": "senior",
    "visa_sponsorship": None,
    "salary_range": None,
    "raw_text": SENIOR_JD_SHOULD_SKIP,
    "source_url": None,
}
