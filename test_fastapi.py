from fastapi import FastAPI
from fastapi.testclient import TestClient

app = FastAPI()

@app.get("/stream/{type}/{id}.json")
def get_stream(type: str, id: str):
    return {"type": type, "id": id}

client = TestClient(app)
print(client.get("/stream/series/tt123%3A1%3A2.json").json())
