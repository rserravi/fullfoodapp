import json
from api.main import app

def main():
    schema = app.openapi()
    with open("openapi.json", "w", encoding="utf-8") as f:
        json.dump(schema, f, ensure_ascii=False, indent=2)
    print("✅ openapi.json escrito en el repo raíz")

if __name__ == "__main__":
    main()
