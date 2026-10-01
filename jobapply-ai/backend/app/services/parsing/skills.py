"""Skill taxonomy: canonical names, aliases, categories and similarity families.

Used by CV parsing, job parsing and the matching engine so all three agree on what a "skill" is.
"""
from __future__ import annotations

import re
from functools import lru_cache

# category -> {canonical: [aliases...]}
TAXONOMY: dict[str, dict[str, list[str]]] = {
    "language": {
        "Python": ["python3", "python 3"], "Java": [], "JavaScript": ["js", "ecmascript", "es6"], "TypeScript": ["ts"],
        "C++": ["cpp", "c plus plus"], "C#": ["c sharp", "csharp"], "C": [], "Go": ["golang"], "Rust": [], "PHP": [],
        "Ruby": [], "Kotlin": [], "Swift": [], "Scala": [], "R": ["r programming", "rstudio"], "MATLAB": [], "SQL": [],
        "Bash": ["shell scripting", "shell"], "Dart": [], "Perl": [], "Julia": [], "HTML": ["html5"], "CSS": ["css3"],
        "Solidity": [], "Haskell": [], "Lua": [], "Objective-C": [],
    },
    "framework": {
        "Django": [], "Flask": [], "FastAPI": ["fast api"], "Spring Boot": ["springboot", "spring"], "React": ["react.js", "reactjs"],
        "Next.js": ["nextjs", "next js"], "Vue": ["vue.js", "vuejs"], "Angular": ["angularjs"], "Node.js": ["nodejs", "node js", "node"],
        "Express": ["express.js", "expressjs"], "NestJS": ["nest.js"], "Laravel": [], "Rails": ["ruby on rails"], ".NET": ["dotnet", "asp.net", ".net core"],
        "Flutter": [], "React Native": [], "Svelte": [], "Tailwind CSS": ["tailwind"], "Bootstrap": [], "jQuery": [], "GraphQL": [],
        "REST APIs": ["rest api", "restful", "restful api", "restful apis", "rest"], "gRPC": [], "Hibernate": [], "Android": [],
    },
    "ai_ml": {
        "Machine Learning": ["ml"], "Deep Learning": ["dl"], "NLP": ["natural language processing"], "Computer Vision": ["cv model", "image processing"],
        "PyTorch": ["torch"], "TensorFlow": ["tf"], "Keras": [], "scikit-learn": ["sklearn", "scikit learn"], "XGBoost": [], "LightGBM": [],
        "Hugging Face": ["huggingface", "transformers"], "LLMs": ["llm", "large language models", "large language model"], "RAG": ["retrieval augmented generation", "retrieval-augmented generation"],
        "LangChain": [], "OpenCV": [], "Pandas": [], "NumPy": [], "SciPy": [], "Matplotlib": [], "Seaborn": [], "Plotly": [],
        "CNN": ["convolutional neural network", "convolutional neural networks"], "Transformers": ["vision transformer", "vit"],
        "Reinforcement Learning": ["rl"], "Generative AI": ["genai", "gen ai"], "MLOps": [], "Feature Engineering": [], "Time Series": ["time-series", "forecasting"],
        "Data Mining": [], "Explainable AI": ["xai", "shap", "lime", "grad-cam"], "Statistics": ["statistical analysis"], "Data Analysis": ["data analytics"],
        "Data Visualization": ["data visualisation"], "Power BI": ["powerbi"], "Tableau": [], "Excel": ["ms excel", "microsoft excel"], "Spark": ["pyspark", "apache spark"],
        "Kaggle": [], "Jupyter": ["jupyter notebook"], "ETL": [], "Data Warehousing": ["data warehouse"], "Prompt Engineering": [],
    },
    "database": {
        "PostgreSQL": ["postgres", "postgresql"], "MySQL": [], "MongoDB": ["mongo"], "SQLite": [], "Redis": [], "Elasticsearch": ["elastic search"],
        "Oracle": ["oracle db"], "SQL Server": ["mssql", "ms sql", "microsoft sql server"], "Firebase": [], "DynamoDB": [], "Cassandra": [],
        "Neo4j": [], "MariaDB": [], "Snowflake": [], "BigQuery": [], "Pinecone": [], "FAISS": [],
    },
    "cloud": {
        "AWS": ["amazon web services", "ec2", "s3", "lambda"], "Azure": ["microsoft azure"], "GCP": ["google cloud", "google cloud platform"],
        "Docker": ["containerization", "containers"], "Kubernetes": ["k8s"], "Terraform": [], "Ansible": [], "Jenkins": [],
        "GitHub Actions": [], "GitLab CI": ["gitlab ci/cd"], "CI/CD": ["cicd", "ci cd", "continuous integration"], "Linux": ["ubuntu"],
        "Nginx": [], "Vercel": [], "Heroku": [], "Serverless": [], "Microservices": ["micro-services", "microservice"],
    },
    "tool": {
        "Git": [], "GitHub": [], "GitLab": [], "Jira": [], "Postman": [], "Figma": [], "VS Code": ["vscode", "visual studio code"],
        "Selenium": [], "JUnit": [], "Pytest": [], "Cypress": [], "Agile": ["scrum"], "Celery": [], "RabbitMQ": [], "Kafka": ["apache kafka"],
        "Streamlit": [], "Gradio": [], "LaTeX": [], "Unit Testing": ["unit tests", "tdd", "test driven development"], "System Design": [],
        "OOP": ["object oriented programming", "object-oriented programming", "object oriented"], "Data Structures": ["dsa", "algorithms", "data structures and algorithms"],
        "Web Scraping": ["scrapy", "beautifulsoup"], "Computer Networks": ["networking"], "Cybersecurity": ["information security"],
    },
    "soft": {
        "Communication": [], "Teamwork": ["team work", "collaboration", "team player"], "Leadership": [], "Problem Solving": ["problem-solving"],
        "Time Management": [], "Critical Thinking": [], "Adaptability": [], "Presentation": ["public speaking"], "Research": [], "Technical Writing": [],
    },
}

# Families give partial credit between near-substitutes (similarity weight in matching).
FAMILIES: dict[str, set[str]] = {
    "sql_db": {"PostgreSQL", "MySQL", "SQLite", "SQL Server", "Oracle", "MariaDB", "SQL"},
    "nosql_db": {"MongoDB", "DynamoDB", "Cassandra", "Firebase", "Redis"},
    "dl_framework": {"PyTorch", "TensorFlow", "Keras"},
    "classic_ml": {"scikit-learn", "XGBoost", "LightGBM"},
    "py_web": {"Django", "Flask", "FastAPI"},
    "js_ui": {"React", "Vue", "Angular", "Svelte", "Next.js"},
    "js_backend": {"Node.js", "Express", "NestJS"},
    "cloud": {"AWS", "Azure", "GCP"},
    "orchestration": {"Docker", "Kubernetes"},
    "ci": {"Jenkins", "GitHub Actions", "GitLab CI", "CI/CD"},
    "bi": {"Power BI", "Tableau", "Data Visualization", "Matplotlib", "Seaborn", "Plotly"},
    "ml_general": {"Machine Learning", "Deep Learning", "Generative AI", "LLMs", "NLP", "Computer Vision", "RAG", "Data Mining", "Reinforcement Learning"},
    "data_lib": {"Pandas", "NumPy", "SciPy", "Spark", "Data Analysis"},
    "jvm": {"Java", "Kotlin", "Scala", "Spring Boot"},
    "queue": {"Kafka", "RabbitMQ", "Celery"},
    "mobile": {"Flutter", "React Native", "Android", "Swift", "Kotlin"},
    "scm": {"Git", "GitHub", "GitLab"},
}

_CANON_TO_CAT: dict[str, str] = {}
_ALIAS_TO_CANON: dict[str, str] = {}
for _cat, _items in TAXONOMY.items():
    for _canon, _aliases in _items.items():
        _CANON_TO_CAT[_canon] = _cat
        _ALIAS_TO_CANON[_canon.lower()] = _canon
        for _a in _aliases:
            _ALIAS_TO_CANON[_a.lower()] = _canon

# Short/ambiguous tokens that must not match as free text (only via explicit skill lists).
_AMBIGUOUS = {"c", "r", "go", "swift", "rest", "node", "spring", "shell", "ts", "js", "cv model", "oracle", "research", "presentation", "ml", "dl", "rl", "tf", "lime", "vit"}


def canonicalize(name: str) -> str:
    n = re.sub(r"\s+", " ", name.strip().strip("•·-–,;:.")).strip()
    return _ALIAS_TO_CANON.get(n.lower(), n)


def category_of(canonical: str) -> str:
    return _CANON_TO_CAT.get(canonical, "technical")


@lru_cache(maxsize=1)
def _pattern() -> re.Pattern[str]:
    terms = sorted((t for t in _ALIAS_TO_CANON if t not in _AMBIGUOUS), key=len, reverse=True)
    alt = "|".join(re.escape(t) for t in terms)
    return re.compile(rf"(?<![A-Za-z0-9+#.])(?:{alt})(?![A-Za-z0-9+#]|\.[A-Za-z0-9])", re.IGNORECASE)


def find_skills(text: str, include_ambiguous_tokens: bool = False) -> list[str]:
    """Return canonical skills mentioned in free text, in order of first appearance."""
    found: list[str] = []
    for m in _pattern().finditer(text):
        canon = _ALIAS_TO_CANON[m.group(0).lower()]
        if canon not in found:
            found.append(canon)
    if include_ambiguous_tokens:
        # Used for explicit skill lists ("Languages: Python, C, R, Go")
        for tok in re.split(r"[,;/|•·\n]+", text):
            t = tok.strip().strip(".").lower()
            if t in _AMBIGUOUS and t in _ALIAS_TO_CANON:
                canon = _ALIAS_TO_CANON[t]
                if canon not in found:
                    found.append(canon)
    return found


def family_of(canonical: str) -> set[str]:
    fam: set[str] = set()
    for members in FAMILIES.values():
        if canonical in members:
            fam |= members
    fam.discard(canonical)
    return fam


def similarity(required: str, have: set[str]) -> float:
    """1.0 exact, 0.5 same family, 0.0 none."""
    if required in have:
        return 1.0
    if family_of(required) & have:
        return 0.5
    return 0.0
