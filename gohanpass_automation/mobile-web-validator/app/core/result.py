class TestResult:
    def __init__(self):
        self.results = []

    def add(self, name, status):
        self.results.append((name, status))

    def get(self):
        return self.results