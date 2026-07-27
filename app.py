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

# In-memory single session state
session_state = {
    "asked_ids": [],
    "current_question_id": None,
    "start_time": None,
    "retry_counts": {}  # Maps question_id (int or str) to number of retries
}

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
    if os.path.exists(LOGS_FILE):
        try:
            with open(LOGS_FILE, 'r') as f:
                return json.load(f)
        except Exception as e:
            print(f"Error reading {LOGS_FILE}: {e}")
            return []
    return []

def save_logs(logs):
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
    questions = load_questions()
    asked_set = set(session_state["asked_ids"])
    
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
    session_state["asked_ids"].append(next_q["id"])
    session_state["current_question_id"] = next_q["id"]
    session_state["start_time"] = time.time()
    
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
        
    # Calculate time taken
    time_taken = 0.0
    if session_state["start_time"] and session_state["current_question_id"] == question_id:
        time_taken = time.time() - session_state["start_time"]
    
    # Check correctness (clean whitespaces, dollar signs, and lower-case comparison for safety)
    given_ans = str(answer_given).strip().lower().replace("$", "") if answer_given is not None else ""
    correct_ans = str(question["answer"]).strip().lower().replace("$", "")
    is_correct = (given_ans == correct_ans)
    
    # Increment retry count if wrong
    # Key is saved as string to ensure JSON keys match properly
    q_id_str = str(question_id)
    retry_count = session_state["retry_counts"].get(q_id_str, 0)
    
    if not is_correct:
        session_state["retry_counts"][q_id_str] = retry_count + 1
        
    # Log the complete session records
    logs = load_logs()
    
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
    
    logs.append(log_record)
    save_logs(logs)
    
    return jsonify({
        "correct": is_correct,
        "correct_answer": question["answer"],
        "retry_count_after": session_state["retry_counts"].get(q_id_str, 0)
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
    session_state.clear()
    session_state.update({
        "asked_ids": [],
        "current_question_id": None,
        "start_time": None,
        "retry_counts": {}
    })
    return jsonify({
        "success": True,
        "message": "In-memory session state has been reset."
    })

if __name__ == '__main__':
    # Run server on port 5000
    app.run(host='0.0.0.0', port=5000, debug=True)
