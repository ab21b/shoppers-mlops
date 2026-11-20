import json
import os
import random
from pathlib import Path

from locust import HttpUser, between, task

GOOD = json.loads((Path(__file__).parent / "good.json").read_text())
SERVICE_HOST = os.getenv("SERVICE_HOST", "shoppers.localhost")
MONTHS = ["Feb", "Mar", "May", "June", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


class Shopper(HttpUser):
    wait_time = between(0.05, 0.2)

    def on_start(self):
        self.client.headers["Host"] = SERVICE_HOST

    @task(20)
    def predict(self):
        row = dict(GOOD)
        row["PageValues"] = round(random.uniform(0, 60), 2)
        row["ProductRelated"] = random.randint(1, 120)
        row["ProductRelated_Duration"] = round(row["ProductRelated"] * random.uniform(10, 60), 1)
        row["Month"] = random.choice(MONTHS)
        row["Weekend"] = random.random() < 0.25
        self.client.post("/v1/predict", json=row, name="/v1/predict")

    @task(1)
    def health(self):
        self.client.get("/health", name="/health")
