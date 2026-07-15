from collections import OrderedDict
import numpy as np
import requests


class Similarity_Cache:

    def __init__(self, cache_size, threshold: float, embedding_model, eviction_policy):
        self.query_db = OrderedDict()
        self.threshold = threshold
        self.embedding_model = embedding_model
        self.eviction_policy = eviction_policy
        self.cache_size = cache_size

    def get(self, key):
        query_embedding = self.embedding_model.encode(key)
        best_score = -1
        best_value = None
        best_key = None

        # Check for zero vector to avoid division by zero
        query_norm = np.linalg.norm(query_embedding)
        if query_norm == 0:
            return None

        for k, item in self.query_db.items():
            item_norm = np.linalg.norm(item["embedding"])
            if item_norm == 0:
                continue  # Skip zero vectors
            score = np.dot(query_embedding, item["embedding"]) / (query_norm * item_norm)
            if score > best_score:
                best_score = score
                best_value = item["value"]
                best_key = k
        if best_key is not None and best_score > self.threshold:
            self.update(best_key)
            return best_value
        else:
            return None

    def put(self, key, value):
        if len(self.query_db) >= self.cache_size:
            self.evict()
        self.query_db[key] = {"embedding": self.embedding_model.encode(key), "value": value}

    def evict(self):
        if self.eviction_policy == "LRU":
            self.query_db.popitem(last=False)

        elif self.eviction_policy == "FIFO":
            pass

        elif self.eviction_policy == "LFU":
            pass

        else:
            raise ValueError("Unknown eviction policy")

    def update(self, key):
        if self.eviction_policy == "LRU":
            self.query_db.move_to_end(key)
        elif self.eviction_policy == "LFU":
            pass
        elif self.eviction_policy == "FIFO":
            pass
