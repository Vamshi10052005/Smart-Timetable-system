# migrate_database.py - Safe migration without file deletion
import sqlite3
import os
from app import app, db

def migrate_database():
    print("🔄 DATABASE MIGRATION")
    print("=" * 40)
    
    if not os.path.exists('timetable.db'):
        print("❌ Database file not found")
        return False
    
    try:
        # Connect to existing database
        conn = sqlite3.connect('timetable.db')
        cursor = conn.cursor()
        
        # Check current columns
        cursor.execute("PRAGMA table_info(class_section)")
        current_columns = [col[1] for col in cursor.fetchall()]
        print("📊 Current columns:", current_columns)
        
        # Add class_adviser column if it doesn't exist
        if 'class_adviser' not in current_columns:
            print("➕ Adding class_adviser column...")
            cursor.execute('ALTER TABLE class_section ADD COLUMN class_adviser VARCHAR(100) DEFAULT "To be assigned"')
            conn.commit()
            print("✅ class_adviser column added successfully!")
            
            # Update existing records with default value
            cursor.execute('UPDATE class_section SET class_adviser = "To be assigned"')
            conn.commit()
            print("✅ Updated existing sections with default class adviser")
        else:
            print("✅ class_adviser column already exists")
        
        # Verify the migration
        cursor.execute("PRAGMA table_info(class_section)")
        new_columns = [col[1] for col in cursor.fetchall()]
        print("📊 New columns:", new_columns)
        
        # Show current data
        cursor.execute("SELECT id, section_name, class_adviser FROM class_section")
        sections = cursor.fetchall()
        if sections:
            print("📋 Current sections:")
            for section in sections:
                print(f"   - ID: {section[0]}, Section: {section[1]}, Adviser: {section[2]}")
        else:
            print("📋 No sections found in database")
        
        conn.close()
        print("🎉 DATABASE MIGRATION COMPLETED SUCCESSFULLY!")
        return True
        
    except Exception as e:
        print(f"❌ Migration failed: {e}")
        return False

if __name__ == '__main__':
    migrate_database()