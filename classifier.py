import joblib

class SpamClassifier:
    def __init__(self, model_path="spam_model.joblib", vectorizer_path="vectorizer.joblib"):
        self.model      = joblib.load(model_path)
        self.vectorizer = joblib.load(vectorizer_path)

    def classify(self, text):
        X     = self.vectorizer.transform([text])
        pred  = int(self.model.predict(X)[0])
        score = float(self.model.predict_proba(X)[0][1])
        return "spam" if pred == 1 else "normal", score