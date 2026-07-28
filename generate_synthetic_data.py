import psycopg2
import random
import time
from datetime import datetime, timedelta

# Database Connection URL (External link to Render PostgreSQL)
DATABASE_URL = "postgresql://adaptive_learning_db_chk8_user:wYiX1KgJm1ugdS4DvXbhTNdFBgGvxDX4@dpg-d9jndkcm0tmc73bbuvf0-a.oregon-postgres.render.com/adaptive_learning_db_chk8"

# 20 engineering cognitive probes (mapped to sub_skills and difficulty)
QUESTIONS_METADATA = [
    {"id": 1, "sub_skill": "spelling-correction", "difficulty": "medium", "category": "dyslexia"},
    {"id": 2, "sub_skill": "simple-writing", "difficulty": "easy", "category": "dyslexia"},
    {"id": 3, "sub_skill": "visual-search", "difficulty": "medium", "category": "dyslexia"},
    {"id": 4, "sub_skill": "word-ordering", "difficulty": "medium", "category": "dyslexia"},
    {"id": 5, "sub_skill": "copy-typing", "difficulty": "medium", "category": "dyslexia"},
    {"id": 6, "sub_skill": "memory-retention", "difficulty": "easy", "category": "adhd"},
    {"id": 7, "sub_skill": "memory-recall", "difficulty": "medium", "category": "adhd"},
    {"id": 8, "sub_skill": "copy-typing", "difficulty": "easy", "category": "dyslexia"},
    {"id": 9, "sub_skill": "vocabulary-opposite", "difficulty": "easy", "category": "dyslexia"},
    {"id": 10, "sub_skill": "simple-reading", "difficulty": "easy", "category": "dyslexia"},
    {"id": 11, "sub_skill": "decimal-comparison", "difficulty": "hard", "category": "dyscalculia"},
    {"id": 12, "sub_skill": "basic-subtraction", "difficulty": "medium", "category": "dyscalculia"},
    {"id": 13, "sub_skill": "fraction-comparison", "difficulty": "medium", "category": "dyscalculia"},
    {"id": 14, "sub_skill": "skip-counting-backwards", "difficulty": "medium", "category": "dyscalculia"},
    {"id": 15, "sub_skill": "missing-operator", "difficulty": "hard", "category": "dyscalculia"},
    {"id": 16, "sub_skill": "rounding-numbers", "difficulty": "medium", "category": "dyscalculia"},
    {"id": 17, "sub_skill": "money-arithmetic", "difficulty": "medium", "category": "dyscalculia"},
    {"id": 18, "sub_skill": "fraction-word-problem", "difficulty": "medium", "category": "dyscalculia"},
    {"id": 19, "sub_skill": "number-line-mapping", "difficulty": "easy", "category": "dyscalculia"},
    {"id": 20, "sub_skill": "geometric-sequence", "difficulty": "medium", "category": "dyscalculia"}
]

# Profiles configuration
PROFILES = [
    # 5 Neurotypical (Control)
    {"id": f"sim-NT{i:03d}", "type": "Neurotypical"} for i in range(1, 6)
] + [
    # 5 ADHD
    {"id": f"sim-ADHD{i:03d}", "type": "ADHD"} for i in range(1, 6)
] + [
    # 5 Dyscalculia
    {"id": f"sim-DYSC{i:03d}", "type": "Dyscalculia"} for i in range(1, 6)
] + [
    # 5 Dyslexia
    {"id": f"sim-DYSX{i:03d}", "type": "Dyslexia"} for i in range(1, 6)
]

def generate_telemetry_for_question(profile_type, question):
    q_category = question["category"]
    difficulty = question["difficulty"]
    
    # Base defaults
    retry_count = 0
    time_taken = 0.0
    tab_switches = 0
    mouse_idle_time = 0.0
    typing_pauses = 0
    backspaces = 0
    frustration_label = "Low"
    correct = True
    answer_given = "correct_placeholder"

    # Neurotypical Profile (Control group)
    if profile_type == "Neurotypical":
        retry_count = 0
        time_taken = random.uniform(3.0, 8.0) if difficulty != "hard" else random.uniform(6.0, 12.0)
        tab_switches = 0
        mouse_idle_time = random.uniform(0.2, 1.5)
        typing_pauses = random.randint(0, 1)
        backspaces = random.randint(0, 2)
        frustration_label = "Low"
        correct = True

    # ADHD Profile (High idle, tab switches, typing pauses across all questions)
    elif profile_type == "ADHD":
        # Disengagement / Distraction
        tab_switches = random.choice([0, 0, 1, 1, 2, 3, 4])
        mouse_idle_time = random.uniform(4.0, 15.0)
        typing_pauses = random.randint(2, 7)
        time_taken = random.uniform(12.0, 30.0) + mouse_idle_time
        backspaces = random.randint(1, 5)
        
        # Impulsive mistakes leading to retries
        correct = random.choice([True, True, False])
        if not correct:
            retry_count = random.randint(1, 2)
            time_taken += retry_count * random.uniform(4.0, 8.0)
            frustration_label = random.choice(["Medium", "High"])
        else:
            retry_count = 0
            frustration_label = random.choice(["Low", "Medium"])

    # Dyscalculia Profile (Struggle heavily on math Q11-20, normal on Q1-10)
    elif profile_type == "Dyscalculia":
        if q_category == "dyscalculia":
            # Struggle on math
            retry_count = random.randint(2, 5)
            # High idle time (doing calculations in head / counting fingers)
            mouse_idle_time = random.uniform(8.0, 22.0)
            typing_pauses = random.randint(2, 6)
            backspaces = random.randint(2, 8)
            time_taken = random.uniform(25.0, 60.0) + mouse_idle_time
            frustration_label = "High" if retry_count >= 3 else "Medium"
            
            # Chance of skipping if too frustrated
            if retry_count >= 4 and random.choice([True, False]):
                answer_given = "skipped"
                correct = False
            else:
                correct = True
        else:
            # Normal spelling performance
            retry_count = 0
            time_taken = random.uniform(4.0, 9.0)
            tab_switches = 0
            mouse_idle_time = random.uniform(0.5, 2.0)
            typing_pauses = random.randint(0, 1)
            backspaces = random.randint(0, 2)
            frustration_label = "Low"
            correct = True

    # Dyslexia Profile (Struggle heavily on text Q1-10, normal on Q11-20)
    elif profile_type == "Dyslexia":
        if q_category == "dyslexia":
            # Struggle on spelling, word order, copy typing
            retry_count = random.randint(1, 4)
            # High backspaces (typing errors and self-corrections)
            backspaces = random.randint(6, 18)
            # Long reading/decoding times
            typing_pauses = random.randint(3, 9)
            time_taken = random.uniform(22.0, 50.0) + (backspaces * 0.8)
            mouse_idle_time = random.uniform(3.0, 10.0)
            frustration_label = "High" if retry_count >= 3 else "Medium"
            
            # Chance of skipping
            if retry_count >= 3 and random.choice([True, False]):
                answer_given = "skipped"
                correct = False
            else:
                correct = True
        else:
            # Normal math performance
            retry_count = random.choice([0, 0, 1])
            time_taken = random.uniform(5.0, 14.0)
            tab_switches = 0
            mouse_idle_time = random.uniform(0.5, 2.5)
            typing_pauses = random.randint(0, 2)
            backspaces = random.randint(0, 3)
            frustration_label = "Low" if retry_count == 0 else "Medium"
            correct = True

    # Build the record array (if retry_count > 0, we write previous failed attempts to match real behavior!)
    records = []
    base_time = time_taken / (retry_count + 1)
    
    for attempt in range(retry_count + 1):
        is_final_attempt = (attempt == retry_count)
        attempt_correct = correct if is_final_attempt else False
        attempt_answer = answer_given if (is_final_attempt and answer_given == "skipped") else ("incorrect_attempt" if not attempt_correct else "correct_answer")
        
        # Distribute time and backspaces over attempts
        attempt_time = base_time + random.uniform(-1.0, 1.0)
        attempt_idle = mouse_idle_time / (retry_count + 1)
        attempt_backspaces = max(0, int(backspaces / (retry_count + 1)))
        
        records.append({
            "device_type": random.choice(["Desktop", "Mobile", "Mobile", "Tablet"]) if profile_type != "ADHD" else "Desktop",
            "question_id": question["id"],
            "answer_given": attempt_answer,
            "tab_switches": tab_switches if is_final_attempt else 0,
            "mouse_idle_time": round(max(0.1, attempt_idle), 2),
            "typing_pauses": max(0, int(typing_pauses / (retry_count + 1))),
            "backspaces": attempt_backspaces,
            "used_visual_toggle": False,
            "visual_level_used": 0,
            "frustration_label": frustration_label if is_final_attempt else random.choice(["Low", "Medium"]),
            "correct": attempt_correct,
            "retry_count": attempt,
            "time_taken": round(max(1.0, attempt_time), 2),
            "sub_skill": question["sub_skill"],
            "difficulty": question["difficulty"]
        })
        
    return records

def main():
    print("Connecting to PostgreSQL database...")
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        print("Connected successfully!")
    except Exception as e:
        print(f"Failed to connect to database: {e}")
        return

    # Prepare all tuples for batch insert
    insert_tuples = []
    
    # Loop through each profile
    for profile in PROFILES:
        # Baseline start timestamp for realistic timeline
        start_ts = datetime.now() - timedelta(days=random.randint(1, 5), hours=random.randint(1, 23))
        
        for question in QUESTIONS_METADATA:
            # Generate records for this question (includes retries)
            question_records = generate_telemetry_for_question(profile["type"], question)
            
            # Prepare each record sequentially with incrementing timestamps
            for i, record in enumerate(question_records):
                record_ts = start_ts + timedelta(seconds=int(record["time_taken"] * (i + 1)))
                timestamp_str = record_ts.strftime("%Y-%m-%dT%H:%M:%SZ")
                
                insert_tuples.append((
                    profile["id"], record["device_type"], record["question_id"], record["answer_given"],
                    record["tab_switches"], record["mouse_idle_time"], record["typing_pauses"], record["backspaces"],
                    record["used_visual_toggle"], record["visual_level_used"], record["frustration_label"],
                    record["correct"], record["retry_count"], record["time_taken"], record["sub_skill"],
                    record["difficulty"], timestamp_str
                ))
            
            # Shift time forward for the next question
            start_ts += timedelta(seconds=int(sum(r["time_taken"] for r in question_records) + random.uniform(5, 15)))

    from psycopg2.extras import execute_values
    print(f"Inserting {len(insert_tuples)} records into PostgreSQL...")
    execute_values(cur, """
        INSERT INTO session_logs (
            participant_id, device_type, question_id, answer_given, 
            tab_switches, mouse_idle_time, typing_pauses, backspaces, 
            used_visual_toggle, visual_level_used, frustration_label, 
            correct, retry_count, time_taken, sub_skill, difficulty, timestamp
        ) VALUES %s
    """, insert_tuples)
    total_inserted = len(insert_tuples)

    # Commit changes
    conn.commit()
    cur.close()
    conn.close()
    
    print("\n==============================================")
    print(f"SYNTHETIC DATA GENERATION SUCCESSFUL!")
    print(f"Generated 20 unique participants (5 ADHD, 5 Dyslexia, 5 Dyscalculia, 5 Control).")
    print(f"Inserted a total of {total_inserted} records directly into your PostgreSQL database!")
    print("==============================================")

if __name__ == "__main__":
    main()
