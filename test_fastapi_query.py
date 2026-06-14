from fastapi import FastAPI
from fastapi.testclient import TestClient

app = FastAPI()

@app.get("/play")
def play(content_id: str | None = None):
    return {"content_id": content_id}

client = TestClient(app)
print(client.get("/play?content_id=tt123%3A1%3A2").json())
