# Create a migration script: fix_time_slots.py
from app import app, db
from models import TimeSlot

def fix_time_slots():
    with app.app_context():
        # Example: Fix lunch break time
        lunch_break = TimeSlot.query.filter_by(name="Lunch Break").first()
        if lunch_break:
            lunch_break.start_time = "13:15"  # 1:15 PM
            lunch_break.end_time = "14:10"    # 2:10 PM
        
        # Add other time slot fixes as needed
        db.session.commit()
        print("Time slots fixed successfully!")

if __name__ == '__main__':
    fix_time_slots()