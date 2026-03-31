
import os
import io
import json
import pandas as pd
from flask import Flask, request, jsonify, render_template, send_file
from flask_cors import CORS

from models import (
    db,
    Lecturer,
    Subject,
    TimeSlot,
    ClassSection,
    Assignment,
    GeneratedTimetable,
    TimetableEntry,
    FixedSlot,
)

from scheduler import run_scheduler

app = Flask(__name__, static_folder="static", template_folder="templates")
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///timetable.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db.init_app(app)
CORS(app)

DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]

# In-memory fixed slots (frontend sends full list each time)
fixed_slots_storage = []


# -----------------------------------------------------------
# Merge fixed slots with generated timetable
# -----------------------------------------------------------
def merge_fixed_slots_with_timetable(timetable_data, section_id):
    section = ClassSection.query.get(section_id)
    if not section:
        return timetable_data

    section_name = section.display_name

    # Detect shape of saved timetable
    if any(day in timetable_data for day in DAYS):
        base = {section_name: timetable_data}  # old single-section format
    else:
        base = timetable_data  # already keyed by section

    # Deep copy to avoid mutating original
    merged = json.loads(json.dumps(base))

    if section_name not in merged:
        merged[section_name] = {d: {} for d in DAYS}

    # Overlay fixed slots from memory
    for fs in fixed_slots_storage:
        if fs.get("class_section_id") != section_id:
            continue

        tslot = TimeSlot.query.get(fs["time_slot_id"])
        day = fs.get("day")
        if not tslot or not day:
            continue

        if day not in merged[section_name]:
            merged[section_name][day] = {}

        key = tslot.display_name

        if fs.get("custom_label"):
            merged[section_name][day][key] = {
                "custom_label": fs["custom_label"],
                "is_fixed": True,
            }
        elif fs.get("subject_id") and fs.get("lecturer_id"):
            merged[section_name][day][key] = {
                "subject_id": fs["subject_id"],
                "lecturer_id": fs["lecturer_id"],
                "is_fixed": True,
            }

    return merged


# -----------------------------------------------------------
# Home page
# -----------------------------------------------------------
@app.route("/")
def index():
    return render_template("index.html")


# -----------------------------------------------------------
# Get all data
# -----------------------------------------------------------
@app.route("/api/data", methods=["GET"])
def get_all_data():
    try:
        lecturers = Lecturer.query.all()
        subjects = Subject.query.all()
        slots = TimeSlot.query.order_by(TimeSlot.start_time).all()
        sections = ClassSection.query.all()
        assignments = Assignment.query.all()

        return jsonify(
            {
                "lecturers": [{"id": l.id, "name": l.name} for l in lecturers],
                "subjects": [
                    {"id": s.id, "code": s.code, "name": s.name} for s in subjects
                ],
                "time_slots": [
                    {
                        "id": t.id,
                        "name": t.name,
                        "start": t.start_time,
                        "end": t.end_time,
                        "is_break": bool(t.is_break),
                        "display_name": t.display_name,
                    }
                    for t in slots
                ],
                "sections": [
                    {"id": s.id, "display_name": s.display_name} for s in sections
                ],
               "assignments": [
    {
        "id": a.id,
        "lecturer": a.lecturer.name,
        "lecturer_id": a.lecturer_id,
        "subject": a.subject.name,
        "subject_id": a.subject_id,
        "section": a.class_section.display_name,
        "class_section_id": a.class_section_id,
        "weekly_count": a.lectures_per_week,
        "max_per_day": a.max_per_day,
    }
    for a in assignments
],

                "fixed_slots": fixed_slots_storage,
            }
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# -----------------------------------------------------------
# Upload combined CSV (Lecturer + Subject)
# -----------------------------------------------------------
ALLOWED_EXT = {".csv", ".xlsx", ".xls"}


@app.route("/upload/combined_list", methods=["POST"])
def upload_combined_list():
    try:
        if "file" not in request.files:
            return jsonify({"error": "No file part"}), 400

        file = request.files["file"]
        if file.filename == "":
            return jsonify({"error": "No selected file"}), 400

        ext = os.path.splitext(file.filename)[1].lower()
        if ext not in ALLOWED_EXT:
            return jsonify({"error": "Unsupported file type"}), 400

        if ext == ".csv":
            content = file.stream.read().decode("utf-8")
            df = pd.read_csv(io.StringIO(content))
        else:
            df = pd.read_excel(file)

        required = ["Lecture ID", "Lecture Name", "Subject Code", "Subject Name"]
        for col in required:
            if col not in df.columns:
                return jsonify({"error": f"Missing column: {col}"}), 400

        added_lect = 0
        added_sub = 0

        # Lecturers
        for _, row in (
            df[["Lecture ID", "Lecture Name"]].dropna().drop_duplicates().iterrows()
        ):
            lid = str(row["Lecture ID"]).strip()
            lname = str(row["Lecture Name"]).strip()
            if not lid or not lname:
                continue

            if not Lecturer.query.filter_by(lecturer_id=lid).first():
                db.session.add(Lecturer(lecturer_id=lid, name=lname))
                added_lect += 1

        # Subjects
        for _, row in (
            df[["Subject Code", "Subject Name"]].dropna().drop_duplicates().iterrows()
        ):
            sc = str(row["Subject Code"]).strip()
            sn = str(row["Subject Name"]).strip()
            if not sc or not sn:
                continue

            if not Subject.query.filter_by(code=sc).first():
                db.session.add(Subject(code=sc, name=sn))
                added_sub += 1

        db.session.commit()
        return jsonify(
            {
                "success": f"Upload complete. Added Lecturers: {added_lect}, Subjects: {added_sub}"
            }
        )
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


# -----------------------------------------------------------
# Time Slot CRUD
# -----------------------------------------------------------
@app.route("/api/timeslots", methods=["POST"])
def add_timeslot():
    try:
        data = request.get_json()
        t = TimeSlot(
            name=data["name"],
            start_time=data["start_time"],
            end_time=data["end_time"],
            is_break=bool(data.get("is_break", False)),
        )
        db.session.add(t)
        db.session.commit()
        return jsonify({"success": "Time slot added", "id": t.id})
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


@app.route("/api/timeslots/<int:slot_id>", methods=["PUT"])
def update_timeslot(slot_id):
    try:
        t = TimeSlot.query.get(slot_id)
        if not t:
            return jsonify({"error": "Time slot not found"}), 404

        data = request.get_json()
        t.name = data["name"]
        t.start_time = data["start_time"]
        t.end_time = data["end_time"]
        t.is_break = bool(data.get("is_break", False))

        db.session.commit()
        return jsonify({"success": "Time slot updated"})
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


@app.route("/api/timeslots/<int:slot_id>", methods=["DELETE"])
def delete_timeslot(slot_id):
    try:
        t = TimeSlot.query.get(slot_id)
        if not t:
            return jsonify({"error": "Time slot not found"}), 404

        db.session.delete(t)
        db.session.commit()
        return jsonify({"success": "Time slot deleted"})
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


# -----------------------------------------------------------
# Section + Assignment
# -----------------------------------------------------------
@app.route("/api/sections", methods=["POST"])
def add_section():
    try:
        data = request.get_json()
        s = ClassSection(
            year=int(data["year"]),
            section_name=data["section_name"],
            department=data["department"],
            class_adviser=data.get("class_adviser", "To be assigned"),
        )
        db.session.add(s)
        db.session.commit()
        return jsonify({"success": "Section added", "id": s.id})
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

# -----------------------------------------------------------
# Delete Section (and its dependent data)
# -----------------------------------------------------------
@app.route("/api/sections/<int:section_id>", methods=["DELETE"])
def delete_section(section_id):
    try:
        section = ClassSection.query.get(section_id)
        if not section:
            return jsonify({"error": "Section not found"}), 404

        # 1) Delete all assignments for this section
        Assignment.query.filter_by(class_section_id=section_id).delete()

        # 2) Delete timetable entries for this section (if any)
        TimetableEntry.query.filter_by(class_section_id=section_id).delete()

        # 3) Delete generated timetables for this section
        GeneratedTimetable.query.filter_by(section_id=section_id).delete()

        # 4) Delete fixed slots in DB (if you store them there)
        FixedSlot.query.filter_by(class_section_id=section_id).delete()

        # 5) Remove the section itself
        db.session.delete(section)
        db.session.commit()

        # 6) Also clean in-memory fixed_slots_storage for this section
        global fixed_slots_storage
        fixed_slots_storage = [
            fs
            for fs in fixed_slots_storage
            if int(fs.get("class_section_id")) != section_id
        ]

        return jsonify({"success": "Section deleted"})
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


@app.route("/api/assignments", methods=["POST"])
def add_assignment():
    try:
        data = request.get_json()
        a = Assignment(
            class_section_id=int(data["class_section_id"]),
            subject_id=int(data["subject_id"]),
            lecturer_id=int(data["lecturer_id"]),
            lectures_per_week=int(data["lectures_per_week"]),
            max_per_day=int(data["max_per_day"]),
        )
        db.session.add(a)
        db.session.commit()
        return jsonify({"success": "Assignment added", "id": a.id})
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500
@app.route("/api/assignments/<int:assignment_id>", methods=["PUT"])
def update_assignment(assignment_id):
    try:
        a = Assignment.query.get(assignment_id)
        if not a:
            return jsonify({"error": "Assignment not found"}), 404

        data = request.get_json() or {}

        if "class_section_id" in data:
            a.class_section_id = int(data["class_section_id"])
        if "subject_id" in data:
            a.subject_id = int(data["subject_id"])
        if "lecturer_id" in data:
            a.lecturer_id = int(data["lecturer_id"])
        if "lectures_per_week" in data:
            a.lectures_per_week = int(data["lectures_per_week"])
        if "max_per_day" in data:
            a.max_per_day = int(data["max_per_day"])

        db.session.commit()
        return jsonify({"success": "Assignment updated"})
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

@app.route("/api/assignments/<int:assignment_id>", methods=["DELETE"])
def delete_assignment(assignment_id):
    try:
        a = Assignment.query.get(assignment_id)
        if not a:
            return jsonify({"error": "Assignment not found"}), 404

        db.session.delete(a)
        db.session.commit()
        return jsonify({"success": "Assignment deleted"})
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

# -----------------------------------------------------------
# CLEAR ALL LECTURERS / SUBJECTS
# -----------------------------------------------------------
@app.route("/api/lecturers/clear", methods=["DELETE"])
def clear_all_lecturers():
    try:
        Assignment.query.delete()
        Lecturer.query.delete()
        db.session.commit()
        return jsonify({"success": "All lecturers (and their assignments) cleared"})
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


@app.route("/api/subjects/clear", methods=["DELETE"])
def clear_all_subjects():
    try:
        Assignment.query.delete()
        Subject.query.delete()
        db.session.commit()
        return jsonify({"success": "All subjects (and their assignments) cleared"})
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


# -----------------------------------------------------------
# Fixed Slots (with clash checking)
# -----------------------------------------------------------
@app.route("/api/fixed_slots", methods=["GET"])
def get_fixed_slots():
    return jsonify({"fixed_slots": fixed_slots_storage})


@app.route("/api/fixed_slots", methods=["POST"])
def update_fixed_slots():
    """
    Accepts a full list of fixed slots from frontend and:
      1) Checks clashes between fixed slots themselves (same time, different section)
         - by lecturer CSV ID
         - by subject code
      2) Checks clashes with already saved generated timetables (GeneratedTimetable)
      3) Adds a WARNING (not error) if a lecturer has continuous periods
         (e.g. 9–10 and 10–11 in different sections)
      4) If no hard clash, updates fixed_slots_storage
    """
    try:
        global fixed_slots_storage
        data = request.get_json() or {}
        new_list = data.get("fixed_slots", [])

        # Helper: get real lecturer_id (from CSV) and subject_code
        def get_codes(fs):
            lect_row = (
                Lecturer.query.get(fs.get("lecturer_id"))
                if fs.get("lecturer_id")
                else None
            )
            subj_row = (
                Subject.query.get(fs.get("subject_id"))
                if fs.get("subject_id")
                else None
            )
            lect_code = lect_row.lecturer_id if lect_row else None
            subj_code = subj_row.code if subj_row else None
            return lect_code, subj_code

        # ------------------------------
        # A) FIXED vs FIXED (hard clash)
        # ------------------------------
        for i, fs in enumerate(new_list):
            sec_id = int(fs["class_section_id"])
            day = fs["day"]
            slot_id = int(fs["time_slot_id"])

            fs_lect_code, fs_subj_code = get_codes(fs)

            for j, other in enumerate(new_list):
                if i == j:
                    continue
                if other["day"] != day or int(other["time_slot_id"]) != slot_id:
                    continue
                if int(other["class_section_id"]) == sec_id:
                    continue  # same section is allowed

                other_lect_code, other_subj_code = get_codes(other)

                if fs_lect_code and other_lect_code and fs_lect_code == other_lect_code:
                    return (
                        jsonify(
                            {
                                "error": f"Lecturer clash: Lecturer ID {fs_lect_code} used at same time in two sections."
                            }
                        ),
                        400,
                    )

                if fs_subj_code and other_subj_code and fs_subj_code == other_subj_code:
                    return (
                        jsonify(
                            {
                                "error": f"Subject clash: Subject {fs_subj_code} used at same time in two sections."
                            }
                        ),
                        400,
                    )

        # ------------------------------
        # B) FIXED vs GENERATED TIMETABLES (hard clash)
        # ------------------------------
        active_tts = GeneratedTimetable.query.filter_by(is_active=True).all()
        time_slots = {t.id: t for t in TimeSlot.query.all()}
        sections = {s.id: s for s in ClassSection.query.all()}

        for fs in new_list:
            sec_id = int(fs["class_section_id"])
            day = fs["day"]
            slot_id = int(fs["time_slot_id"])

            slot = time_slots.get(slot_id)
            if not slot:
                continue

            fs_lect_code, fs_subj_code = get_codes(fs)

            for tt in active_tts:
                if tt.section_id == sec_id:
                    continue  # same section, ignore

                sec_obj = sections.get(tt.section_id)
                if not sec_obj:
                    continue

                sec_name = sec_obj.display_name
                tt_data = json.loads(tt.timetable_data)

                sec_block = tt_data.get(sec_name, {})
                day_block = sec_block.get(day, {})
                if slot.display_name not in day_block:
                    continue

                val = day_block[slot.display_name]

                # generated tuple
                if isinstance(val, (list, tuple)) and len(val) >= 3:
                    gen_subject_id = val[1]
                    gen_lecturer_id = val[2]
                    gen_lect = Lecturer.query.get(gen_lecturer_id)
                    gen_subj = Subject.query.get(gen_subject_id)

                    gen_lect_code = gen_lect.lecturer_id if gen_lect else None
                    gen_subj_code = gen_subj.code if gen_subj else None

                    if fs_lect_code and gen_lect_code and fs_lect_code == gen_lect_code:
                        return (
                            jsonify(
                                {
                                    "error": f"Lecturer clash with generated timetable: Lecturer ID {fs_lect_code} already used at this time."
                                }
                            ),
                            400,
                        )

                    if fs_subj_code and gen_subj_code and fs_subj_code == gen_subj_code:
                        return (
                            jsonify(
                                {
                                    "error": f"Subject clash with generated timetable: Subject {fs_subj_code} already used at this time."
                                }
                            ),
                            400,
                        )

                # fixed dict inside saved timetable
                if isinstance(val, dict):
                    ex_sub_id = val.get("subject_id")
                    ex_lect_id = val.get("lecturer_id")

                    ex_lect = Lecturer.query.get(ex_lect_id) if ex_lect_id else None
                    ex_subj = Subject.query.get(ex_sub_id) if ex_sub_id else None

                    ex_lect_code = ex_lect.lecturer_id if ex_lect else None
                    ex_subj_code = ex_subj.code if ex_subj else None

                    if fs_lect_code and ex_lect_code and fs_lect_code == ex_lect_code:
                        return (
                            jsonify(
                                {
                                    "error": f"Lecturer clash with saved fixed timetable: {fs_lect_code}"
                                }
                            ),
                            400,
                        )

                    if fs_subj_code and ex_subj_code and fs_subj_code == ex_subj_code:
                        return (
                            jsonify(
                                {
                                    "error": f"Subject clash with saved fixed timetable: {fs_subj_code}"
                                }
                            ),
                            400,
                        )

        # ------------------------------
        # C) WARNING: continuous classes for same lecturer
        # ------------------------------
        # order non-break slots by start_time
        non_break_slots = (
            TimeSlot.query.filter_by(is_break=False)
            .order_by(TimeSlot.start_time)
            .all()
        )
        slot_order = {s.id: idx for idx, s in enumerate(non_break_slots)}

        warnings = []
        # group by (lecturer_csv_id, day)
        lect_day_map = {}

        for fs in new_list:
            lect_code, _ = get_codes(fs)
            if not lect_code:
                continue
            slot_id = int(fs["time_slot_id"])
            if slot_id not in slot_order:
                continue
            day = fs["day"]
            key = (lect_code, day)
            lect_day_map.setdefault(key, []).append(fs)

        for (lect_code, day), entries in lect_day_map.items():
            # sort by slot index
            entries_sorted = sorted(
                entries, key=lambda x: slot_order.get(int(x["time_slot_id"]), -1)
            )
            for i in range(len(entries_sorted) - 1):
                a = entries_sorted[i]
                b = entries_sorted[i + 1]
                idx_a = slot_order[int(a["time_slot_id"])]
                idx_b = slot_order[int(b["time_slot_id"])]
                # consecutive slots?
                if idx_b == idx_a + 1:
                    # only warn if they are in different sections
                    if int(a["class_section_id"]) != int(b["class_section_id"]):
                        sec_a = sections.get(int(a["class_section_id"]))
                        sec_b = sections.get(int(b["class_section_id"]))
                        name_a = (
                            sec_a.display_name
                            if sec_a
                            else str(a["class_section_id"])
                        )
                        name_b = (
                            sec_b.display_name
                            if sec_b
                            else str(b["class_section_id"])
                        )
                        warnings.append(
                            f"Lecturer {lect_code} has continuous classes on {day} "
                            f"for sections {name_a} and {name_b}."
                        )

        # ------------------------------
        # NO HARD CLASHES → SAVE
        # ------------------------------
        fixed_slots_storage = [
            {
                "class_section_id": int(fs["class_section_id"]),
                "day": fs["day"],
                "time_slot_id": int(fs["time_slot_id"]),
                "subject_id": int(fs["subject_id"]) if fs.get("subject_id") else None,
                "lecturer_id": int(fs["lecturer_id"]) if fs.get("lecturer_id") else None,
                "custom_label": fs.get("custom_label"),
            }
            for fs in new_list
        ]

        response = {"success": "Fixed slots updated with clash protection"}
        if warnings:
            # join distinct warnings into one message
            response["warning"] = " | ".join(sorted(set(warnings)))

        return jsonify(response)

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/check_clashes", methods=["GET"])
def check_clashes():
    """
    Simple clash check:
      - Same lecturer (by CSV ID) teaching in >1 section at the same time
      - Same subject code appearing in >1 section at the same time
      - Uses ACTIVE GeneratedTimetable with fixed slots merged
    """
    try:
        active_tts = GeneratedTimetable.query.filter_by(is_active=True).all()
        if not active_tts:
            return jsonify({"clashes": [], "message": "No active timetables found"})

        # we care about ALL time slots (including breaks)
        time_slots = TimeSlot.query.order_by(TimeSlot.start_time).all()
        if not time_slots:
            return jsonify({"clashes": [], "message": "No time slots defined"})

        sections_by_id = {s.id: s for s in ClassSection.query.all()}

        clashes = []

        # For each day + time slot, see which sections use same lecturer/subject
        for day in DAYS:
            for slot in time_slots:
                subj_usage = {}   # subject_code -> [section_display_names]
                lect_usage = {}   # lecturer_csv_id -> [section_display_names]

                for tt in active_tts:
                    sec_obj = sections_by_id.get(tt.section_id)
                    if not sec_obj:
                        continue

                    sec_name = sec_obj.display_name
                    tt_data = json.loads(tt.timetable_data)

                    # merge fixed slots (so timetable includes admin fixes too)
                    merged = merge_fixed_slots_with_timetable(tt_data, tt.section_id)

                    if (
                        sec_name not in merged
                        or day not in merged[sec_name]
                        or slot.display_name not in merged[sec_name][day]
                    ):
                        continue

                    val = merged[sec_name][day][slot.display_name]

                    subj_code = None
                    lect_code = None

                    # CASE 1: generated/fixed tuple
                    # (class_section_id, subject_id, lecturer_id, subj_code, lect_csv_id)
                    if isinstance(val, (list, tuple)):
                        if len(val) >= 5:
                            subj_code = val[3]
                            lect_code = val[4]
                        elif len(val) >= 3:
                            # older format: (sec_id, subj_id, lect_id)
                            subj_row = Subject.query.get(val[1])
                            lect_row = Lecturer.query.get(val[2])
                            subj_code = subj_row.code if subj_row else None
                            lect_code = lect_row.lecturer_id if lect_row else None

                    # CASE 2: fixed dict {subject_id, lecturer_id, custom_label, ...}
                    elif isinstance(val, dict):
                        sid = val.get("subject_id")
                        lid = val.get("lecturer_id")
                        if sid:
                            subj = Subject.query.get(sid)
                            subj_code = subj.code if subj else None
                        if lid:
                            lect = Lecturer.query.get(lid)
                            lect_code = lect.lecturer_id if lect else None

                    # BREAK or empty / custom label only → ignore for clash
                    if not subj_code and not lect_code:
                        continue

                    if subj_code:
                        subj_usage.setdefault(subj_code, []).append(sec_name)
                    if lect_code:
                        lect_usage.setdefault(lect_code, []).append(sec_name)

                time_label = f"{slot.start_time}-{slot.end_time}"

                # record subject clashes (same code in >1 section)
                for code, secs in subj_usage.items():
                    unique_secs = sorted(set(secs))
                    if len(unique_secs) > 1:
                        clashes.append(
                            {
                                "type": f"Subject {code} clash",
                                "day": day,
                                "time": time_label,
                                "sections": unique_secs,
                            }
                        )

                # record lecturer clashes (same lecturer CSV in >1 section)
                for code, secs in lect_usage.items():
                    unique_secs = sorted(set(secs))
                    if len(unique_secs) > 1:
                        clashes.append(
                            {
                                "type": f"Lecturer {code} clash",
                                "day": day,
                                "time": time_label,
                                "sections": unique_secs,
                            }
                        )

        return jsonify({"clashes": clashes})

    except Exception as e:
        # helpful to see actual error in your Flask console
        print("ERROR in /api/check_clashes:", e)
        return jsonify({"error": str(e)}), 500

@app.route("/api/clash_analysis", methods=["GET"])
def clash_analysis():
    """
    Detailed clash analysis:
      - Finds cases where the SAME lecturer (by CSV ID)
        has back-to-back classes (consecutive periods)
        on the same day, possibly in different sections.
      - Uses active GeneratedTimetable + fixed slots.
    """
    try:
        active_tts = GeneratedTimetable.query.filter_by(is_active=True).all()
        if not active_tts:
            return jsonify(
                {"gap_violations": [], "message": "No active timetables found"}
            )

        # non-break slots in order
        time_slots = (
            TimeSlot.query.filter_by(is_break=False)
            .order_by(TimeSlot.start_time)
            .all()
        )
        if not time_slots:
            return jsonify(
                {"gap_violations": [], "message": "No teaching time slots defined"}
            )

        slot_index = {s.display_name: idx for idx, s in enumerate(time_slots)}
        sections = {s.id: s for s in ClassSection.query.all()}
        lecturers = Lecturer.query.all()
        lect_by_csv = {l.lecturer_id: l.name for l in lecturers}

        # (lecturer_csv_id, day) -> list of entries
        lect_day_map = {}

        for tt in active_tts:
            sec_obj = sections.get(tt.section_id)
            if not sec_obj:
                continue

            sec_name = sec_obj.display_name
            tt_data = json.loads(tt.timetable_data)

            # include fixed slots too
            merged = merge_fixed_slots_with_timetable(tt_data, tt.section_id)

            if sec_name not in merged:
                continue

            for day in DAYS:
                day_block = merged[sec_name].get(day, {})
                if not day_block:
                    continue

                for slot in time_slots:
                    sname = slot.display_name
                    val = day_block.get(sname)
                    if not val:
                        continue

                    lecturer_csv = None

                    # tuple: (class_section_id, subject_id, lecturer_id, subj_code, lect_csv_id)
                    if isinstance(val, (list, tuple)) and len(val) >= 5:
                        lecturer_csv = val[4]

                    # dict fixed
                    elif isinstance(val, dict):
                        lid = val.get("lecturer_id")
                        if lid:
                            lect = Lecturer.query.get(lid)
                            lecturer_csv = lect.lecturer_id if lect else None

                    if not lecturer_csv:
                        continue

                    key = (lecturer_csv, day)
                    lect_day_map.setdefault(key, []).append(
                        {
                          "slot_idx": slot_index[sname],
                          "time_label": f"{slot.start_time}-{slot.end_time}",
                          "section": sec_name,
                        }
                    )

        gap_violations = []

        # Now detect consecutive slots per lecturer per day
        for (lect_csv, day), entries in lect_day_map.items():
            if len(entries) < 2:
                continue

            entries_sorted = sorted(entries, key=lambda x: x["slot_idx"])

            for i in range(len(entries_sorted) - 1):
                a = entries_sorted[i]
                b = entries_sorted[i + 1]

                if b["slot_idx"] == a["slot_idx"] + 1:
                    gap_violations.append(
                        {
                            "lecturer_id": lect_csv,
                            "lecturer_name": lect_by_csv.get(lect_csv),
                            "day": day,
                            "first_time": a["time_label"],
                            "second_time": b["time_label"],
                            "first_section": a["section"],
                            "second_section": b["section"],
                        }
                    )

        return jsonify(
            {
                "gap_violations": gap_violations,
                "total_gap_violations": len(gap_violations),
            }
        )

    except Exception as e:
        return jsonify({"error": str(e)}), 500

# -----------------------------------------------------------
# Generate (uses fixed_slots_storage)
# -----------------------------------------------------------
@app.route("/generate", methods=["POST"])
def generate_timetable():
    try:
        assignments = Assignment.query.all()
        sections = ClassSection.query.all()
        time_slots = TimeSlot.query.filter_by(is_break=False).all()
        break_slots = TimeSlot.query.filter_by(is_break=True).all()

        timetable, report = run_scheduler(
            assignments, sections, time_slots, break_slots, fixed_slots_storage
        )

        return jsonify({"timetable": timetable, "report": report})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# -----------------------------------------------------------
# Regenerate & save timetable ONLY for one section
# -----------------------------------------------------------
@app.route("/regenerate", methods=["POST"])
def regenerate_timetable():
    try:
        data = request.get_json() or {}
        section_id = data.get("section_id")

        if not section_id:
            return jsonify({"error": "section_id is required"}), 400

        section = ClassSection.query.get(int(section_id))
        if not section:
            return jsonify({"error": "Section not found"}), 404

        # Still schedule for ALL sections (to keep cross-section clash checking)
        assignments = Assignment.query.all()
        sections = ClassSection.query.all()
        time_slots = TimeSlot.query.filter_by(is_break=False).all()
        break_slots = TimeSlot.query.filter_by(is_break=True).all()

        timetable, report = run_scheduler(
            assignments, sections, time_slots, break_slots, fixed_slots_storage
        )

        sec_name = section.display_name

        if sec_name not in timetable:
            return jsonify(
                {"error": "No timetable generated for the selected section."}
            ), 500

        sec_data = timetable[sec_name]

        # Deactivate only this section's previous versions
        GeneratedTimetable.query.filter_by(
            section_id=section.id, is_active=True
        ).update({"is_active": False})

        last = (
            GeneratedTimetable.query.filter_by(section_id=section.id)
            .order_by(GeneratedTimetable.version.desc())
            .first()
        )
        next_version = (last.version + 1) if last else 1

        # Save ONLY this section's timetable to DB
        section_timetable = {sec_name: sec_data}

        rec = GeneratedTimetable(
            section_id=section.id,
            timetable_data=json.dumps(section_timetable),
            generation_notes=json.dumps(report),
            version=next_version,
            is_active=True,
        )
        db.session.add(rec)
        db.session.commit()

    
        return jsonify(
            {
                "timetable": timetable,              # all sections
                "section_timetable": section_timetable,  # only this section
                "report": report,
                "section_id": section.id,
                "version": next_version,
            }
        )

    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

# -----------------------------------------------------------
# Load Saved Timetable
# -----------------------------------------------------------
@app.route("/api/timetable/pdf/<int:section_id>", methods=["GET"])
def generate_pdf(section_id):
    """
    PDF: days as rows, time slots as columns.
    - Uses the ACTIVE saved timetable (GeneratedTimetable) for this section.
    - Merges fixed slots so PDF matches saved timetable + fixes.
    - College-style header + footer.
    """
    try:
        from reportlab.platypus import (
            SimpleDocTemplate,
            Table,
            TableStyle,
            Paragraph,
            Spacer,
        )
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.lib import colors
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.enums import TA_CENTER, TA_LEFT

        # 1) Get active saved timetable
        tt = GeneratedTimetable.query.filter_by(
            section_id=section_id, is_active=True
        ).first()
        if not tt:
            return "No active timetable found for this section. Please regenerate and save first.", 404

        section = ClassSection.query.get(section_id)
        if not section:
            return "Section not found", 404

        original = json.loads(tt.timetable_data)
        merged = merge_fixed_slots_with_timetable(original, section_id)

        # all slots in chronological order (including breaks)
        all_slots = TimeSlot.query.order_by(TimeSlot.start_time).all()
        if not all_slots:
            return "No time slots defined", 404

        def to12(time_str: str) -> str:
            try:
                h, m = time_str.split(":")[:2]
                h = int(h)
                ampm = "AM" if h < 12 else "PM"
                hh = h % 12 or 12
                return f"{hh:02d}:{m} {ampm}"
            except Exception:
                return time_str

        buffer = io.BytesIO()

        # Landscape A4 with margins
        page_size = landscape(A4)
        doc = SimpleDocTemplate(
            buffer,
            pagesize=page_size,
            leftMargin=36,
            rightMargin=36,
            topMargin=36,
            bottomMargin=72,  # space for footer
        )
        styles = getSampleStyleSheet()

        # ---------- Dynamic font size ----------
        slot_count = max(len(all_slots), 1)
        if slot_count <= 7:
            base_font_size = 10
        elif slot_count <= 9:
            base_font_size = 9
        elif slot_count <= 11:
            base_font_size = 8
        else:
            base_font_size = 7

        cell_style = styles["BodyText"].clone("CellStyle")
        cell_style.fontSize = base_font_size
        cell_style.leading = base_font_size + 1
        cell_style.alignment = TA_CENTER

        # ---------- Build table data from SAVED timetable ----------
        data_table = []

        # header row
        header = ["Day"] + [
            f"{to12(s.start_time)}\n{to12(s.end_time)}" for s in all_slots
        ]
        data_table.append(header)

        sec_key = section.display_name

        for day in DAYS:
            day_cell = Paragraph(day, cell_style)
            row = [day_cell]

            for slot in all_slots:
                cell_text = ""
                if (
                    sec_key in merged
                    and day in merged[sec_key]
                    and slot.display_name in merged[sec_key][day]
                ):
                    v = merged[sec_key][day][slot.display_name]

                    if v == "BREAK":
                        cell_text = "BREAK"
                    elif isinstance(v, (list, tuple)):
                        # (sec_id, subject_id, lecturer_id, subj_code, lect_csv)
                        subj_id = v[1] if len(v) >= 2 else None
                        subj = Subject.query.get(subj_id) if subj_id else None
                        if subj:
                            # subject name only
                            cell_text = subj.name
                    elif isinstance(v, dict):
                        if v.get("custom_label"):
                            cell_text = v["custom_label"]
                        elif v.get("subject_id"):
                            subj = Subject.query.get(v["subject_id"])
                            if subj:
                                cell_text = subj.name

                if cell_text:
                    if cell_text == "BREAK":
                        row.append(Paragraph("<b>BREAK</b>", cell_style))
                    else:
                        row.append(Paragraph(cell_text, cell_style))
                else:
                    row.append("")

            data_table.append(row)

        # ---------- Column widths ----------
        day_col_width = 80
        usable_width = doc.width
        remaining_width = max(usable_width - day_col_width, 100)
        slot_col_width = remaining_width / slot_count
        col_widths = [day_col_width] + [slot_col_width] * slot_count

        table = Table(data_table, colWidths=col_widths, repeatRows=1)
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.grey),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                    ("BACKGROUND", (0, 0), (0, 0), colors.darkgrey),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("FONTSIZE", (0, 0), (-1, -1), base_font_size),
                ]
            )
        )

        # ---------- Header (college style) ----------
        header_title_style = ParagraphStyle(
            "HeaderTitle",
            parent=styles["Title"],
            alignment=TA_CENTER,
            fontSize=14,
        )
        header_sub_style = ParagraphStyle(
            "HeaderSub",
            parent=styles["Normal"],
            alignment=TA_CENTER,
            fontSize=10,
        )
        header_small_style = ParagraphStyle(
            "HeaderSmall",
            parent=styles["Normal"],
            alignment=TA_CENTER,
            fontSize=9,
        )
        header_left_style = ParagraphStyle(
            "HeaderLeft",
            parent=styles["Normal"],
            alignment=TA_LEFT,
            fontSize=9,
        )

        college_name = Paragraph("CANARA ENGINEERING COLLEGE", header_title_style)
        address = Paragraph("Bantwal, D.K - 574219", header_sub_style)
        acad_tt = Paragraph("Academic Time Table", header_small_style)

        programme_text = "Programme: Information Science & Engineering"
        semester_text = "Semester: __________"
        section_text = f"Section: {section.section_name}"

        header_row1 = [
            Paragraph(programme_text, header_left_style),
            Paragraph(semester_text, header_left_style),
            Paragraph(section_text, header_left_style),
        ]

        ay_text = "Academic Year (AY): __________"
        scheme_text = "Scheme: __________"
        room_text = "Room: __________"

        if section.class_adviser and section.class_adviser != "To be assigned":
            adviser_text = f"Class Adviser: {section.class_adviser}"
        else:
            adviser_text = "Class Adviser: __________"

        header_row2 = [
            Paragraph(ay_text, header_left_style),
            Paragraph(scheme_text, header_left_style),
            Paragraph(room_text, header_left_style),
            Paragraph(adviser_text, header_left_style),
        ]

        header_table_data = [
            [header_row1[0], header_row1[1], header_row1[2], ""],
            header_row2,
        ]

        h_col_width = doc.width / 4.0
        header_table = Table(
            header_table_data,
            colWidths=[h_col_width] * 4,
            hAlign="LEFT",
        )
        header_table.setStyle(
            TableStyle(
                [
                    ("SPAN", (2, 0), (3, 0)),
                    ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("FONTSIZE", (0, 0), (-1, -1), 9),
                    ("LINEBELOW", (0, 1), (-1, 1), 0.5, colors.black),
                ]
            )
        )

        elements = [
            college_name,
            address,
            acad_tt,
            Spacer(1, 6),
            header_table,
            Spacer(1, 12),
            table,
        ]

        # ---------- Footer (signatures) ----------
        def add_footer(canvas, doc_obj):
            width_page, height_page = doc_obj.pagesize
            y = 40
            canvas.setFont("Helvetica", 10)

            canvas.line(60, y, 220, y)
            canvas.drawString(60, y - 12, "Time Table Coordinator")

            canvas.line(width_page - 220, y, width_page - 60, y)
            canvas.drawString(
                width_page - 220, y - 12, "Head of the Department"
            )

        doc.build(elements, onFirstPage=add_footer, onLaterPages=add_footer)
        buffer.seek(0)

        return send_file(
            buffer,
            as_attachment=True,
            download_name=f"timetable_section_{section_id}.pdf",
            mimetype="application/pdf",
        )
    except Exception as e:
        return f"Error generating PDF: {e}", 500

# -----------------------------------------------------------
# MAIN
# -----------------------------------------------------------
if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(debug=True)
