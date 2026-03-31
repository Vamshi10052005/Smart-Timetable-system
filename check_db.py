# check_db.py
import sqlite3
import os

def check_database():
    if not os.path.exists('timetable.db'):
        print("❌ Database file does not exist")
        return False
    
    try:
        conn = sqlite3.connect('timetable.db')
        cursor = conn.cursor()
        
        # Check if class_section table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='class_section'")
        if not cursor.fetchone():
            print("❌ class_section table does not exist")
            return False
        
        # Check columns in class_section
        cursor.execute("PRAGMA table_info(class_section)")
        columns = cursor.fetchall()
        print("📊 Current class_section columns:")
        for col in columns:
            print(f"   - {col[1]} ({col[2]})")
        
        # Check for class_adviser column
        has_class_adviser = any('class_adviser' in col for col in columns)
        print(f"✅ class_adviser column: {'EXISTS' if has_class_adviser else 'MISSING'}")
        
        conn.close()
        return has_class_adviser
        
    except Exception as e:
        print(f"❌ Error checking database: {e}")
        return False

if __name__ == '__main__':
    check_database()