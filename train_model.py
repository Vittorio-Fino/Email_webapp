import joblib
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.neural_network import MLPClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, classification_report

df = pd.read_csv("spam_ham_dataset.csv")
X = df["text"]
y = df["label"].map({"spam": 1, "ham": 0})

X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

vectorizer = TfidfVectorizer(stop_words="english", max_features=10_000, ngram_range=(1, 2))
X_train_vec = vectorizer.fit_transform(X_train.astype(str))
X_test_vec  = vectorizer.transform(X_test.astype(str))

model = MLPClassifier(
    hidden_layer_sizes=(128, 64),
    max_iter=50,
    early_stopping=True,
    validation_fraction=0.1,
    random_state=42
)
model.fit(X_train_vec, y_train)

preds = model.predict(X_test_vec)
print(f"Accuracy: {accuracy_score(y_test, preds):.2%}")
print(classification_report(y_test, preds, target_names=["normal", "spam"]))

joblib.dump(vectorizer, "vectorizer.joblib")
joblib.dump(model,      "spam_model.joblib")
print("Done.")