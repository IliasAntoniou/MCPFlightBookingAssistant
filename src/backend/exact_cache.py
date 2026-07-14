from collections import OrderedDict


class Exact_Cache:

    def __init__(self, cache_size, eviction_policy):
        self.query_db = OrderedDict()
        self.eviction_policy = eviction_policy
        self.cache_size = cache_size

    def get(self, key):     
        if key in self.query_db:
            self.update(key)
            return self.query_db[key]["value"]
        return None

    def put(self, key, value):
        if key in self.query_db:
            self.update(key)
        if len(self.query_db) >= self.cache_size:
            self.evict()
        self.query_db[key] = {"value": value}
    
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