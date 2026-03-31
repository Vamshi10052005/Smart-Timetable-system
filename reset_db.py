# reset_db.py - COMPLETE WORKING VERSION
import os
import time
import sys
from app import app, db

def ensure_db_reset():
    """Completely reset the database"""
    print("🚀 COMPLETE DATABASE RESET")
    print("=" * 50)
    
    # Step 1: Delete existing database file
    db_path = 'timetable.db'
    if os.path.exists(db_path):
        print("🔄 Removing existing database...")
        try:
            os.remove(db_path)
            print("✅ Database file removed")
            time.sleep(1)  # Wait for file system
        except Exception as e:
            print(f"❌ Could not remove database: {e}")
            print("💡 Please close all applications and try again")
            return False
    
    # Step 2: Create new database with updated schema
    print("🔄 Creating new database with updated schema...")
    try:
        with app.app_context():
            # Drop all tables and recreate
            db.drop_all()
            db.create_all()
            
            # Verify the creation
            from models import ClassSection
            from sqlalchemy import inspect
            
            inspector = inspect(db.engine)
            columns = [col['name'] for col in inspector.get_columns('class_section')]
            
            if 'class_adviser' in columns:
                print("✅ class_adviser column successfully created")
            else:
                print("❌ class_adviser column missing - schema issue")
                return False
                
            print("✅ New database created successfully!")
            return True
            
    except Exception as e:
        print(f"❌ Error creating database: {e}")
        return False

if __name__ == '__main__':
    if ensure_db_reset():
        print("\n🎉 DATABASE RESET COMPLETE!")
        print("=" * 50)
        print("📋 New schema includes:")
        print("   • ClassSection.class_adviser field")
        print("   • Professional PDF generation")
        print("   • Enhanced clash detection")
        print("\n🚀 You can now start the application:")
        print("   python app.py")
    else:
        print("\n❌ RESET FAILED!")
        print("💡 Try these steps:")
        print("   1. Close ALL applications (VS Code, browsers, etc.)")
        print("   2. Restart your computer")
        print("   3. Run this script again")
        sys.exit(1)