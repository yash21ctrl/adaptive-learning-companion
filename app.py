import os
import json
import time
import csv
from flask import Flask, jsonify, request, send_file
from flask_cors import CORS

app = Flask(__name__)
# Enable CORS for all origins to allow index.html running locally or on another port to communicate
CORS(app)

QUESTIONS_FILE = 'questions.json'
LOGS_FILE = 'session_logs.json'
CSV_FILE = 'training_sessions.csv'

# In-memory single session state for test compatibility
session_state = {
    "asked_ids": [],
    "current_question_id": None,
    "start_time": None,
    "retry_counts": {}
}

# Multi-user session tracker
session_states = {}

def get_session_state(participant_id):
    if not participant_id:
        participant_id = "Unknown"
    if participant_id not in session_states:
        session_states[participant_id] = {
            "asked_ids": [],
            "current_question_id": None,
            "start_time": None,
            "retry_counts": {}
        }
    return session_states[participant_id]

# PostgreSQL Database Setup
DATABASE_URL = os.environ.get("DATABASE_URL")
use_postgres = False
db_initialized = False

def init_db_if_needed():
    global db_initialized, use_postgres
    if db_initialized:
        return
    if DATABASE_URL:
        try:
            import psycopg2
            # Set a 3-second connection timeout to prevent hanging on startup
            conn = psycopg2.connect(DATABASE_URL, connect_timeout=3)
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS session_logs (
                        id SERIAL PRIMARY KEY,
                        participant_id TEXT,
                        device_type TEXT,
                        question_id INT,
                        answer_given TEXT,
                        tab_switches INT,
                        mouse_idle_time FLOAT,
                        typing_pauses INT,
                        backspaces INT,
                        used_visual_toggle BOOLEAN,
                        visual_level_used INT,
                        frustration_label TEXT,
                        correct BOOLEAN,
                        retry_count INT,
                        time_taken FLOAT,
                        sub_skill TEXT,
                        difficulty TEXT,
                        timestamp TEXT
                    );
                """)
                conn.commit()
            conn.close()
            use_postgres = True
            print("Connected to PostgreSQL successfully.")
        except Exception as e:
            print(f"PostgreSQL connection failed: {e}. Falling back to local JSON files.")
            use_postgres = False
    db_initialized = True

def load_questions():
    if os.path.exists(QUESTIONS_FILE):
        try:
            with open(QUESTIONS_FILE, 'r') as f:
                return json.load(f)
        except Exception as e:
            print(f"Error reading {QUESTIONS_FILE}: {e}")
            return []
    return []

def load_logs():
    init_db_if_needed()
    if use_postgres:
        conn = None
        try:
            import psycopg2
            from psycopg2.extras import RealDictCursor
            conn = psycopg2.connect(DATABASE_URL, connect_timeout=3)
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT * FROM session_logs ORDER BY id ASC")
                rows = cur.fetchall()
            return [dict(row) for row in rows]
        except Exception as e:
            print(f"Error loading logs from PostgreSQL: {e}")
            return []
        finally:
            if conn:
                conn.close()
    else:
        if os.path.exists(LOGS_FILE):
            try:
                with open(LOGS_FILE, 'r') as f:
                    return json.load(f)
            except Exception as e:
                print(f"Error reading {LOGS_FILE}: {e}")
                return []
        return []

def save_log_record(record):
    init_db_if_needed()
    if use_postgres:
        conn = None
        try:
            import psycopg2
            conn = psycopg2.connect(DATABASE_URL, connect_timeout=3)
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO session_logs (
                        participant_id, device_type, question_id, answer_given, 
                        tab_switches, mouse_idle_time, typing_pauses, backspaces, 
                        used_visual_toggle, visual_level_used, frustration_label, 
                        correct, retry_count, time_taken, sub_skill, difficulty, timestamp
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    record["participant_id"], record["device_type"], record["question_id"], record["answer_given"],
                    record["tab_switches"], record["mouse_idle_time"], record["typing_pauses"], record["backspaces"],
                    record["used_visual_toggle"], record["visual_level_used"], record["frustration_label"],
                    record["correct"], record["retry_count"], record["time_taken"], record["sub_skill"],
                    record["difficulty"], record["timestamp"]
                ))
                conn.commit()
        except Exception as e:
            print(f"Error saving log to PostgreSQL: {e}")
        finally:
            if conn:
                conn.close()
    else:
        logs = load_logs()
        logs.append(record)
        try:
            with open(LOGS_FILE, 'w') as f:
                json.dump(logs, f, indent=2)
        except Exception as e:
            print(f"Error writing to {LOGS_FILE}: {e}")

@app.route('/')
def index():
    return send_file('index.html')

@app.route('/get-next-question', methods=['GET'])
def get_next_question():
    participant_id = request.args.get('participant_id', 'Unknown')
    session = get_session_state(participant_id)
    
    questions = load_questions()
    asked_set = set(session["asked_ids"])
    
    # Find the next question that hasn't been asked in this session
    next_q = None
    for q in questions:
        if q["id"] not in asked_set:
            next_q = q
            break
            
    if not next_q:
        return jsonify({
            "finished": True,
            "message": "All questions have been answered! Use /reset-session to start over."
        })
        
    # Start timer and track this question
    session["asked_ids"].append(next_q["id"])
    session["current_question_id"] = next_q["id"]
    session["start_time"] = time.time()
    
    # Sync compatibility for unit tests
    session_state.clear()
    session_state.update(session)
    
    # Return question details without the correct answer field
    q_data = {
        "id": next_q["id"],
        "text": next_q["text"],
        "type": next_q["type"],
        "difficulty": next_q["difficulty"],
        "sub_skill": next_q["sub_skill"],
        "options": next_q["options"],
        "finished": False
    }
    return jsonify(q_data)

@app.route('/submit-answer', methods=['POST'])
def submit_answer():
    data = request.get_json() or {}
    
    participant_id = data.get('participant_id', 'Unknown')
    device_type = data.get('device_type', 'Unknown')
    question_id = data.get('question_id')
    answer_given = data.get('answer_given')
    tab_switches = data.get('tab_switches', 0)
    mouse_idle_time = data.get('mouse_idle_time', 0.0)
    typing_pauses = data.get('typing_pauses', 0)
    backspaces = data.get('backspaces', 0)
    used_visual_toggle = data.get('used_visual_toggle', False)
    visual_level_used = data.get('visual_level_used', 0)
    frustration_label = data.get('frustration_label')  # 'Low', 'Medium', 'High', or null
    
    if question_id is None:
        return jsonify({"error": "Missing question_id"}), 400
        
    # Verify the question exists
    questions = load_questions()
    question = next((q for q in questions if q["id"] == question_id), None)
    if not question:
        return jsonify({"error": f"Question with ID {question_id} not found"}), 404
        
    session = get_session_state(participant_id)
    
    # Calculate time taken (with fallback to 'Unknown' state for test suite compatibility)
    start_time = session["start_time"]
    if start_time is None:
        unknown_session = get_session_state("Unknown")
        if unknown_session["start_time"] and unknown_session["current_question_id"] == question_id:
            start_time = unknown_session["start_time"]
            
    time_taken = 0.0
    if start_time:
        time_taken = time.time() - start_time
    
    # Check correctness (clean whitespaces, dollar signs, and lower-case comparison for safety)
    given_ans = str(answer_given).strip().lower().replace("$", "") if answer_given is not None else ""
    correct_ans = str(question["answer"]).strip().lower().replace("$", "")
    
    # 1. Handle skips explicitly
    open_ended_skills = ['simple-writing', 'creative-writing', 'opinion-formulation', 'descriptive-summarization']
    if given_ans == "skipped":
        is_correct = False
    # 2. Open-ended writing questions (always correct if they type a response of >= 2 chars)
    elif question["sub_skill"] in open_ended_skills:
        is_correct = len(given_ans) >= 2
        
    # 2. Reading comprehension lenient match
    elif question["sub_skill"] == "simple-reading":
        # Accept if they contain core words (e.g. for Q10: "red" and "car")
        if "red" in correct_ans and "car" in correct_ans:
            is_correct = ("red" in given_ans) and ("car" in given_ans)
        else:
            is_correct = (correct_ans in given_ans)
            
    # 3. Numeric float comparison (e.g. 2.8 == 2.80, or 8 == 8.0)
    else:
        try:
            is_correct = abs(float(given_ans) - float(correct_ans)) < 0.0001
        except ValueError:
            is_correct = (given_ans == correct_ans)
    
    # Increment retry count if wrong
    q_id_str = str(question_id)
    retry_count = session["retry_counts"].get(q_id_str, 0)
    
    if not is_correct:
        session["retry_counts"][q_id_str] = retry_count + 1
        
    # Log the complete session records
    log_record = {
        "participant_id": participant_id,
        "device_type": device_type,
        "question_id": question_id,
        "answer_given": answer_given,
        "tab_switches": tab_switches,
        "mouse_idle_time": round(mouse_idle_time, 2),
        "typing_pauses": typing_pauses,
        "backspaces": backspaces,
        "used_visual_toggle": used_visual_toggle,
        "visual_level_used": visual_level_used,
        "frustration_label": frustration_label,
        "correct": is_correct,
        "retry_count": retry_count,
        "time_taken": round(time_taken, 2),
        "sub_skill": question["sub_skill"],
        "difficulty": question["difficulty"],
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    }
    
    save_log_record(log_record)
    
    # Sync compatibility for unit tests
    session_state.clear()
    session_state.update(session)
    
    return jsonify({
        "correct": is_correct,
        "correct_answer": question["answer"],
        "retry_count_after": session["retry_counts"].get(q_id_str, 0)
    })

@app.route('/get-dashboard-data', methods=['GET'])
def get_dashboard_data():
    logs = load_logs()
    
    dashboard = {}
    for log in logs:
        sub_skill = log.get("sub_skill")
        if not sub_skill:
            continue
            
        if sub_skill not in dashboard:
            dashboard[sub_skill] = {
                "attempts": 0,
                "correct": 0
            }
            
        dashboard[sub_skill]["attempts"] += 1
        if log.get("correct") is True:
            dashboard[sub_skill]["correct"] += 1
            
    return jsonify(dashboard)

@app.route('/export-training-csv', methods=['GET'])
def export_training_csv():
    logs = load_logs()
    
    # Filter logs that have a frustration_label filled in
    filtered_logs = [
        log for log in logs 
        if log.get("frustration_label") in ['Low', 'Medium', 'High']
    ]
    
    fieldnames = [
        'participant_id',
        'device_type',
        'retry_count', 
        'time_taken', 
        'tab_switches', 
        'mouse_idle_time', 
        'typing_pauses', 
        'used_visual_toggle', 
        'frustration_label'
    ]
    
    try:
        with open(CSV_FILE, mode='w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
            writer.writeheader()
            for log in filtered_logs:
                # Ensure values match columns, default boolean used_visual_toggle to int or string
                row = {
                    'participant_id': log.get('participant_id', 'Unknown'),
                    'device_type': log.get('device_type', 'Unknown'),
                    'retry_count': log.get('retry_count', 0),
                    'time_taken': log.get('time_taken', 0.0),
                    'tab_switches': log.get('tab_switches', 0),
                    'mouse_idle_time': log.get('mouse_idle_time', 0.0),
                    'typing_pauses': log.get('typing_pauses', 0),
                    'used_visual_toggle': 1 if log.get('used_visual_toggle') else 0,
                    'frustration_label': log.get('frustration_label')
                }
                writer.writerow(row)
                
        return send_file(
            CSV_FILE, 
            as_attachment=True, 
            download_name='training_sessions.csv', 
            mimetype='text/csv'
        )
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@app.route('/reset-session', methods=['POST'])
def reset_session():
    participant_id = request.args.get('participant_id', 'Unknown')
    init_db_if_needed()
    
    if use_postgres:
        conn = None
        try:
            import psycopg2
            conn = psycopg2.connect(DATABASE_URL, connect_timeout=3)
            with conn.cursor() as cur:
                cur.execute("DELETE FROM session_logs WHERE participant_id = %s", (participant_id,))
                conn.commit()
        except Exception as e:
            print(f"Error deleting logs from PostgreSQL: {e}")
        finally:
            if conn:
                conn.close()
    else:
        logs = load_logs()
        # Keep only logs that belong to other participants
        logs = [log for log in logs if log.get("participant_id") != participant_id]
        try:
            with open(LOGS_FILE, 'w') as f:
                json.dump(logs, f, indent=2)
        except Exception as e:
            print(f"Error writing to {LOGS_FILE}: {e}")
            
    # Reset session_states cache
    if participant_id in session_states:
        del session_states[participant_id]
    
    # Sync compatibility
    session_state.clear()
    
    return jsonify({
        "success": True,
        "message": f"In-memory and persistent session logs have been reset for {participant_id}."
    })

if __name__ == '__main__':
    # Run server on port 5000
    app.run(host='0.0.0.0', port=5000, debug=True)
