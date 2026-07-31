import os
import json
import joblib
import psycopg2
from psycopg2.extras import RealDictCursor
from sklearn.model_selection import train_test_split
from sklearn.tree import DecisionTreeClassifier, export_text
from sklearn.metrics import accuracy_score, classification_report

DATABASE_URL = (
    os.environ.get("DATABASE_URL") or 
    os.environ.get("External_Database_URl") or 
    os.environ.get("External_Database_URL") or 
    os.environ.get("DATABASE URL")
)
LOGS_FILE = "session_logs.json"
MODEL_FILE = "frustration_model.joblib"

def load_data_from_db():
    if not DATABASE_URL:
        print("DATABASE_URL not set. Falling back to JSON files.")
        return []
    try:
        conn = psycopg2.connect(DATABASE_URL)
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT 
                    retry_count, time_taken, tab_switches, 
                    mouse_idle_time, typing_pauses, used_visual_toggle, 
                    frustration_label 
                FROM session_logs 
                WHERE frustration_label IN ('Low', 'Medium', 'High')
            """)
            rows = cur.fetchall()
            return [dict(row) for row in rows]
    except Exception as e:
        print(f"Error loading from database: {e}. Falling back to JSON.")
        return []

def load_data_from_json():
    if os.path.exists(LOGS_FILE):
        try:
            with open(LOGS_FILE, 'r') as f:
                logs = json.load(f)
                return [l for l in logs if l.get("frustration_label") in ['Low', 'Medium', 'High']]
        except Exception as e:
            print(f"Error reading JSON: {e}")
    return []

def main():
    print("Loading training dataset...")
    data = load_data_from_db()
    if not data:
        data = load_data_from_json()
        
    if not data:
        print("ERROR: No labeled telemetry records found in database or JSON. Run synthetic data generator first!")
        return
        
    print(f"Loaded {len(data)} labeled telemetry records.")
    
    # Feature preparation
    X = []
    y = []
    
    label_map = {"Low": 0, "Medium": 1, "High": 2}
    reverse_map = {0: "Low", 1: "Medium", 2: "High"}
    
    for row in data:
        # Map boolean visual toggle to 1 or 0
        used_vt = 1 if row.get("used_visual_toggle") else 0
        
        # Build features array
        features = [
            int(row.get("retry_count", 0)),
            float(row.get("time_taken", 0.0)),
            int(row.get("tab_switches", 0)),
            float(row.get("mouse_idle_time", 0.0)),
            int(row.get("typing_pauses", 0)),
            used_vt
        ]
        
        X.append(features)
        y.append(label_map[row["frustration_label"]])
        
    feature_names = [
        "retry_count", 
        "time_taken", 
        "tab_switches", 
        "mouse_idle_time", 
        "typing_pauses", 
        "used_visual_toggle"
    ]
    
    # Split training and testing sets
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.3, random_state=42)
    
    # Train Decision Tree
    # max_depth=3 keeps the tree simple, robust against noise, and easy to plot for judges
    clf = DecisionTreeClassifier(max_depth=3, random_state=42)
    clf.fit(X_train, y_train)
    
    # Evaluate model
    y_pred = clf.predict(X_test)
    accuracy = accuracy_score(y_test, y_pred)
    
    print("\n==============================================")
    print(f"DECISION TREE TRAINING COMPLETED SUCCESSFUL!")
    print(f"Model Accuracy: {accuracy * 100:.2f}%")
    print("==============================================")
    
    print("\nClassification Report:")
    print(classification_report(y_test, y_pred, target_names=["Low", "Medium", "High"]))
    
    print("\nFeature Importances:")
    for name, importance in zip(feature_names, clf.feature_importances_):
        print(f" - {name}: {importance * 100:.1f}%")
        
    print("\nGenerated Decision Tree Rules (Explainable AI):")
    tree_rules = export_text(clf, feature_names=feature_names)
    print(tree_rules)
    
    # Save the model
    print(f"Saving model to {MODEL_FILE}...")
    joblib.dump(clf, MODEL_FILE)
    print("Model serialized and saved successfully!")

if __name__ == "__main__":
    main()
