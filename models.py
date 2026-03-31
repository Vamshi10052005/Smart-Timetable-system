# models.py
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

# ------------------------------
# Lecturer
# ------------------------------
class Lecturer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    lecturer_id = db.Column(db.String(20), unique=True, nullable=False)   # CSV ID
    name = db.Column(db.String(100), nullable=False)


# ------------------------------
# Subject
# ------------------------------
class Subject(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(20), unique=True, nullable=False)          # CSV subject code
    name = db.Column(db.String(100), nullable=False)


# ------------------------------
# Time Slot
# ------------------------------
class TimeSlot(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    start_time = db.Column(db.String(10), nullable=False)  # HH:MM 24-hour
    end_time = db.Column(db.String(10), nullable=False)
    is_break = db.Column(db.Boolean, default=False)

    @property
    def display_name(self):
        # "Period 1 (09:00 AM-10:00 AM)"
        def to_12h(t):
            try:
                if t.count(":") == 2:
                    t = t.rsplit(":", 1)[0]
                h, m = t.split(":")
                h = int(h)
                ampm = "AM" if h < 12 else "PM"
                hh = h % 12 or 12
                return f"{hh:02d}:{m} {ampm}"
            except:
                return t

        return f"{self.name} ({to_12h(self.start_time)}-{to_12h(self.end_time)})"


# ------------------------------
# Class Section
# ------------------------------
class ClassSection(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    year = db.Column(db.Integer, nullable=False)
    section_name = db.Column(db.String(50), nullable=False)
    department = db.Column(db.String(50), nullable=False, default="CSE")
    class_adviser = db.Column(db.String(100), default="To be assigned")

    @property
    def display_name(self):
        return f"{self.year} Year - {self.section_name} ({self.department})"


# ------------------------------
# Assignment (Subject + Lecturer to Section)
# ------------------------------
class Assignment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    lecturer_id = db.Column(db.Integer, db.ForeignKey("lecturer.id"))
    subject_id = db.Column(db.Integer, db.ForeignKey("subject.id"))
    class_section_id = db.Column(db.Integer, db.ForeignKey("class_section.id"))
    lectures_per_week = db.Column(db.Integer, nullable=False, default=1)
    max_per_day = db.Column(db.Integer, nullable=False, default=1)

    lecturer = db.relationship("Lecturer", backref="assignments")
    subject = db.relationship("Subject", backref="assignments")
    class_section = db.relationship("ClassSection", backref="assignments")


# ------------------------------
# Generated Timetable (Stored JSON versions)
# ------------------------------
class GeneratedTimetable(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    section_id = db.Column(db.Integer, db.ForeignKey("class_section.id"))
    timetable_data = db.Column(db.Text)  # JSON
    generated_at = db.Column(db.DateTime, default=datetime.utcnow)
    version = db.Column(db.Integer, default=1)
    is_active = db.Column(db.Boolean, default=True)
    generation_notes = db.Column(db.Text)

    section = db.relationship("ClassSection", backref="timetables")


# ------------------------------
# TimetableEntry (Generated entries)
# ------------------------------
class TimetableEntry(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    timetable_id = db.Column(db.Integer, db.ForeignKey("generated_timetable.id"))
    day = db.Column(db.String(10), nullable=False)
    time_slot_id = db.Column(db.Integer, db.ForeignKey("time_slot.id"))
    class_section_id = db.Column(db.Integer, db.ForeignKey("class_section.id"))
    assignment_id = db.Column(db.Integer, db.ForeignKey("assignment.id"))

    lecturer_id = db.Column(db.Integer, db.ForeignKey("lecturer.id"))
    subject_id = db.Column(db.Integer, db.ForeignKey("subject.id"))

    custom_label = db.Column(db.String(100))
    is_fixed = db.Column(db.Boolean, default=False)
    is_generated = db.Column(db.Boolean, default=True)

    time_slot = db.relationship("TimeSlot")
    class_section = db.relationship("ClassSection")
    assignment = db.relationship("Assignment")
    lecturer = db.relationship("Lecturer")
    subject = db.relationship("Subject")
    timetable = db.relationship("GeneratedTimetable", backref="entries")


# ------------------------------
# NEW: Fixed Slot Table (Required for clash-check)
# ------------------------------
class FixedSlot(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    class_section_id = db.Column(db.Integer, db.ForeignKey("class_section.id"))
    day = db.Column(db.String(10), nullable=False)
    time_slot_id = db.Column(db.Integer, db.ForeignKey("time_slot.id"))

    subject_id = db.Column(db.Integer, db.ForeignKey("subject.id"), nullable=True)
    lecturer_id = db.Column(db.Integer, db.ForeignKey("lecturer.id"), nullable=True)

    custom_label = db.Column(db.String(100), nullable=True)

    class_section = db.relationship("ClassSection")
    subject = db.relationship("Subject")
    lecturer = db.relationship("Lecturer")
    time_slot = db.relationship("TimeSlot")
