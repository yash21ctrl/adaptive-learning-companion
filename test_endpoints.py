import unittest
import json
import os
import time
import csv
from app import app, session_state, QUESTIONS_FILE, LOGS_FILE, CSV_FILE

class TestAdaptiveLearningCompanion(unittest.TestCase):
    def setUp(self):
        # Configure app for testing
        app.config['TESTING'] = True
        self.client = app.test_client()
        
        # Reset in-memory state
        self.client.post('/reset-session')
        
        # Back up existing files if they exist to avoid overriding user's data
        self.backup_logs = None
        if os.path.exists(LOGS_FILE):
            with open(LOGS_FILE, 'r') as f:
                self.backup_logs = f.read()
            os.remove(LOGS_FILE)
            
        self.backup_csv = None
        if os.path.exists(CSV_FILE):
            with open(CSV_FILE, 'r') as f:
                self.backup_csv = f.read()
            os.remove(CSV_FILE)

    def tearDown(self):
        # Restore files after tests
        if os.path.exists(LOGS_FILE):
            os.remove(LOGS_FILE)
        if self.backup_logs is not None:
            with open(LOGS_FILE, 'w') as f:
                f.write(self.backup_logs)
                
        if os.path.exists(CSV_FILE):
            os.remove(CSV_FILE)
        if self.backup_csv is not None:
            with open(CSV_FILE, 'w') as f:
                f.write(self.backup_csv)

    def test_get_next_question(self):
        # Verify fetching first question
        response = self.client.get('/get-next-question')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        
        self.assertIn('id', data)
        self.assertIn('text', data)
        self.assertIn('type', data)
        self.assertIn('difficulty', data)
        self.assertIn('sub_skill', data)
        self.assertNotIn('answer', data) # VERY IMPORTANT: answer should not be sent
        self.assertFalse(data['finished'])
        
        # Check that active timer state was set
        self.assertEqual(session_state["current_question_id"], data['id'])
        self.assertIsNotNone(session_state["start_time"])

    def test_submit_answer_correct(self):
        # Fetch a question to set the timer
        response = self.client.get('/get-next-question')
        q_data = json.loads(response.data)
        q_id = q_data['id']
        
        # We need the correct answer to submit. Since it's in questions.json, we can load it here
        with open(QUESTIONS_FILE, 'r') as f:
            questions = json.load(f)
        question = next(q for q in questions if q['id'] == q_id)
        correct_answer = question['answer']
        
        # Sleep to guarantee elapsed time > 0
        time.sleep(0.05)
        
        # Submit correct answer
        submit_data = {
            "participant_id": "TestSubject_A",
            "question_id": q_id,
            "answer_given": correct_answer,
            "tab_switches": 2,
            "mouse_idle_time": 4.5,
            "typing_pauses": 1,
            "backspaces": 0,
            "used_visual_toggle": True,
            "visual_level_used": 1,
            "frustration_label": "Low"
        }
        
        response = self.client.post('/submit-answer', 
                                    data=json.dumps(submit_data),
                                    content_type='application/json')
        self.assertEqual(response.status_code, 200)
        res_data = json.loads(response.data)
        self.assertTrue(res_data['correct'])
        self.assertEqual(res_data['correct_answer'], correct_answer)
        
        # Verify entry was logged
        self.assertTrue(os.path.exists(LOGS_FILE))
        with open(LOGS_FILE, 'r') as f:
            logs = json.load(f)
        self.assertEqual(len(logs), 1)
        self.assertTrue(logs[0]['correct'])
        self.assertEqual(logs[0]['question_id'], q_id)
        self.assertEqual(logs[0]['participant_id'], 'TestSubject_A')
        self.assertEqual(logs[0]['frustration_label'], 'Low')
        self.assertEqual(logs[0]['retry_count'], 0) # 1st try was correct, so retry index is 0
        self.assertGreater(logs[0]['time_taken'], 0)

    def test_submit_answer_incorrect_retry(self):
        # Fetch question
        response = self.client.get('/get-next-question')
        q_data = json.loads(response.data)
        q_id = q_data['id']
        
        # Submit WRONG answer
        submit_data = {
            "participant_id": "TestSubject_B",
            "question_id": q_id,
            "answer_given": "incorrect_answer_xyz",
            "tab_switches": 0,
            "mouse_idle_time": 0,
            "typing_pauses": 0,
            "backspaces": 2,
            "used_visual_toggle": False,
            "visual_level_used": 0,
            "frustration_label": "High"
        }
        
        response = self.client.post('/submit-answer', 
                                    data=json.dumps(submit_data),
                                    content_type='application/json')
        res_data = json.loads(response.data)
        self.assertFalse(res_data['correct'])
        
        # The first try retry count should be logged as 0, but backend incremented to 1 for the next try
        self.assertEqual(session_state["retry_counts"][str(q_id)], 1)
        
        # Submit WRONG answer again (retry)
        response = self.client.post('/submit-answer', 
                                    data=json.dumps(submit_data),
                                    content_type='application/json')
        res_data = json.loads(response.data)
        self.assertFalse(res_data['correct'])
        
        # Now retry count in state should be 2
        self.assertEqual(session_state["retry_counts"][str(q_id)], 2)
        
        # Verify log has 2 records and second one logged retry_count as 1
        with open(LOGS_FILE, 'r') as f:
            logs = json.load(f)
        self.assertEqual(len(logs), 2)
        self.assertEqual(logs[0]['retry_count'], 0)
        self.assertEqual(logs[1]['retry_count'], 1)
        self.assertEqual(logs[0]['participant_id'], 'TestSubject_B')
        self.assertEqual(logs[1]['participant_id'], 'TestSubject_B')

    def test_dashboard_and_csv_export(self):
        # Submit multiple answers to build logs
        with open(QUESTIONS_FILE, 'r') as f:
            questions = json.load(f)
            
        for i in range(3):
            # Fetch next question to set start_time
            self.client.get('/get-next-question')
            q = questions[i]
            
            # Submit responses with varying frustration levels
            submit_data = {
                "participant_id": "TestSubject_Multi",
                "question_id": q['id'],
                "answer_given": q['answer'] if i != 1 else "x",
                "tab_switches": i,
                "mouse_idle_time": i * 1.5,
                "typing_pauses": i,
                "used_visual_toggle": True if i == 0 else False,
                "visual_level_used": 2 if i == 0 else 0,
                "frustration_label": "Medium" if i != 2 else None  # i=2 has no frustration filled
            }
            self.client.post('/submit-answer', 
                             data=json.dumps(submit_data),
                             content_type='application/json')
            
        # 1. Verify dashboard endpoints
        dash_response = self.client.get('/get-dashboard-data')
        self.assertEqual(dash_response.status_code, 200)
        dash_data = json.loads(dash_response.data)
        
        # Ensure we have aggregated counts
        total_attempts = sum(x['attempts'] for x in dash_data.values())
        self.assertEqual(total_attempts, 3)
        total_correct = sum(x['correct'] for x in dash_data.values())
        self.assertEqual(total_correct, 2) # i=0 and i=2 were correct
        
        # 2. Verify CSV Export
        csv_response = self.client.get('/export-training-csv')
        self.assertEqual(csv_response.status_code, 200)
        self.assertEqual(csv_response.mimetype, 'text/csv')
        
        # Parse CSV directly from the response stream
        csv_text = csv_response.data.decode('utf-8')
        reader = csv.reader(csv_text.splitlines())
        headers = next(reader)
        self.assertEqual(headers, ['participant_id', 'device_type', 'retry_count', 'time_taken', 'tab_switches', 'mouse_idle_time', 'typing_pauses', 'used_visual_toggle', 'frustration_label', 'data_source'])
        
        rows = list(reader)
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0][0], 'TestSubject_Multi')
        self.assertEqual(rows[0][1], 'Unknown')  # Defaults to Unknown since test did not pass device_type
        self.assertEqual(rows[0][8], 'Medium')
        self.assertEqual(rows[1][8], 'Medium')

if __name__ == '__main__':
    unittest.main()
