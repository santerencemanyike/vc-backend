# MVP backend for Running the Virtual Closet

## 1. Clone the Repository

Clone the repo from GitHub:

```bash
git clone git@github.com:santerencemanyike/vc-backend.git
cd yourrepo
```

## 2. Create and Activate Virtual Environment

```bash
python3.12 -m venv venv
source venv/bin/activate  # On Windows use: venv\Scripts\activate
```

## 3. Install Requirements

```bash
pip install -r requirements.txt
```

## 4. Run your fastapi

uvicorn main:app --reload --host 0.0.0.0 --port 8000
