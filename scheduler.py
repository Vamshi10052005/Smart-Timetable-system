

import random
from collections import defaultdict
from models import Subject, Lecturer

DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]


def run_scheduler(assignments, sections, time_slots, break_slots, fixed_slots):
    try:
        timetable = {}
        all_slots = time_slots + break_slots

        # build order for non-break slots (for adjacency rule)
        slot_index = {s.display_name: idx for idx, s in enumerate(time_slots)}

        # --------------------------
        # Initialize empty timetable
        # --------------------------
        for sec in sections:
            timetable[sec.display_name] = {}
            for day in DAYS:
                timetable[sec.display_name][day] = {}
                for slot in all_slots:
                    timetable[sec.display_name][day][slot.display_name] = None

        # --------------------------
        # Apply BREAK and FIXED slots
        # --------------------------
        timetable = add_fixed_slots(timetable, sections, all_slots, fixed_slots)

        # count fixed subject occurrences
        fixed_counts = defaultdict(int)
        for fs in fixed_slots:
            if "subject_id" in fs and "lecturer_id" in fs:
                key = (fs["class_section_id"], fs["subject_id"], fs["lecturer_id"])
                fixed_counts[key] += 1

        # Build assignment objects
        assign_objs = []
        for a in assignments:
            key = (a.class_section_id, a.subject_id, a.lecturer_id)
            fixed_for_this = fixed_counts.get(key, 0)
            remaining = max(0, a.lectures_per_week - fixed_for_this)

            if remaining > 0:
                assign_objs.append(
                    {
                        "class_section_id": a.class_section_id,
                        "subject_id": a.subject_id,
                        "lecturer_id": a.lecturer_id,
                        "assignment_id": a.id,
                        "max_per_day": a.max_per_day,
                        "total_required": remaining,
                        "scheduled_count": 0,
                        "daily_counts": defaultdict(int),
                        "section_name": next(
                            s.display_name for s in sections if s.id == a.class_section_id
                        ),
                    }
                )

        if not assign_objs:
            return timetable, {
                "status": "Success",
                "message": "All lectures already satisfied by fixed slots.",
                "total_lectures_scheduled": 0,
            }

        # Try main algorithm
        success = schedule_with_distribution(
            timetable, assign_objs, sections, time_slots, slot_index
        )
        if success:
            total = sum(a["scheduled_count"] for a in assign_objs)
            return timetable, {
                "status": "Success",
                "message": "Scheduled successfully with primary algorithm.",
                "total_lectures_scheduled": total,
            }

        # Fallback scheduler
        success_fb = schedule_fallback(
            timetable, assign_objs, sections, time_slots, slot_index
        )
        if success_fb:
            total = sum(a["scheduled_count"] for a in assign_objs)
            return timetable, {
                "status": "Success",
                "message": "Scheduled using fallback algorithm.",
                "total_lectures_scheduled": total,
            }

        return timetable, {
            "status": "Failed",
            "message": "Could not schedule all lectures.",
        }

    except Exception as e:
        return timetable, {"status": "Error", "message": str(e)}


# -----------------------------------------------------
# APPLY BREAK + FIXED SLOTS
# -----------------------------------------------------
def add_fixed_slots(timetable, sections, all_slots, fixed_slots):

    break_slots = [s for s in all_slots if getattr(s, "is_break", False)]

    # Apply BREAK
    for sec_name in timetable:
        for day in timetable[sec_name]:
            for slot in break_slots:
                timetable[sec_name][day][slot.display_name] = "BREAK"

    # Apply ADMIN FIXED SLOTS
    for fs in fixed_slots:
        sec = next((s for s in sections if s.id == fs["class_section_id"]), None)
        slot = next((t for t in all_slots if t.id == fs["time_slot_id"]), None)
        if not sec or not slot:
            continue

        sec_name = sec.display_name
        day = fs["day"]
        slot_name = slot.display_name

        # Custom label (library, sports, etc.)
        if "custom_label" in fs and fs["custom_label"]:
            timetable[sec_name][day][slot_name] = {
                "custom_label": fs["custom_label"],
                "is_fixed": True,
            }

        # Subject + lecturer fixed slot
        elif "subject_id" in fs and "lecturer_id" in fs:
            subj = Subject.query.get(fs["subject_id"])
            lect = Lecturer.query.get(fs["lecturer_id"])

            timetable[sec_name][day][slot_name] = (
                fs["class_section_id"],
                fs["subject_id"],
                fs["lecturer_id"],
                subj.code if subj else None,          # SUBJECT CODE
                lect.lecturer_id if lect else None,   # LECTURER CSV ID
            )

    return timetable


# -----------------------------------------------------
# MAIN SCHEDULER - primary algorithm
# -----------------------------------------------------
def schedule_with_distribution(timetable, assignments, sections, time_slots, slot_index):

    # Heavy subjects first
    assignments.sort(key=lambda x: x["total_required"], reverse=True)
    max_attempts = 250

    for _ in range(max_attempts):

        # Reset all generated (not fixed, not break)
        for sec_name in timetable:
            for day in timetable[sec_name]:
                for slot in time_slots:
                    sname = slot.display_name
                    v = timetable[sec_name][day][sname]

                    if v == "BREAK":
                        continue
                    if isinstance(v, dict) and v.get("is_fixed"):
                        continue
                    if isinstance(v, tuple):  # fixed subject tuple (has subject code)
                        continue

                    timetable[sec_name][day][sname] = None

        # Reset assignment counters
        for a in assignments:
            a["scheduled_count"] = 0
            a["daily_counts"] = defaultdict(int)

        # Try to place each assignment
        for a in assignments:
            days_shuffled = DAYS[:]
            random.shuffle(days_shuffled)

            for day in days_shuffled:

                if a["scheduled_count"] >= a["total_required"]:
                    break

                if a["daily_counts"][day] >= a["max_per_day"]:
                    continue

                sec_name = a["section_name"]

                # find empty valid slots
                candidates = []
                for slot in time_slots:
                    sname = slot.display_name

                    if timetable[sec_name][day][sname] is None:
                        if is_valid_assignment(
                            timetable, a, day, slot, sections, time_slots, slot_index
                        ):
                            candidates.append(slot)

                if candidates:
                    chosen = random.choice(candidates)

                    subj = Subject.query.get(a["subject_id"])
                    lect = Lecturer.query.get(a["lecturer_id"])

                    timetable[sec_name][day][chosen.display_name] = (
                        a["class_section_id"],
                        a["subject_id"],
                        a["lecturer_id"],
                        subj.code if subj else None,          # SUBJECT CODE
                        lect.lecturer_id if lect else None,   # LECTURER CSV ID
                    )

                    a["scheduled_count"] += 1
                    a["daily_counts"][day] += 1

        # Done?
        if all(a["scheduled_count"] >= a["total_required"] for a in assignments):
            return True

    return False


# -----------------------------------------------------
# FALLBACK SCHEDULER
# -----------------------------------------------------
def schedule_fallback(timetable, assignments, sections, time_slots, slot_index):

    lecture_list = []
    for a in assignments:
        for _ in range(a["total_required"]):
            lecture_list.append(a)

    random.shuffle(lecture_list)

    for a in lecture_list:
        sid = a["class_section_id"]
        subid = a["subject_id"]
        lid = a["lecturer_id"]
        sec_name = next(s.display_name for s in sections if s.id == sid)

        subj = Subject.query.get(subid)
        lect = Lecturer.query.get(lid)

        placed = False

        for day in DAYS:
            if placed:
                break

            for slot in time_slots:
                sname = slot.display_name

                if timetable[sec_name][day][sname] is None:
                    if is_valid_assignment_simple(
                        timetable, a, day, slot, sections, time_slots, slot_index
                    ):

                        timetable[sec_name][day][sname] = (
                            sid,
                            subid,
                            lid,
                            subj.code if subj else None,           # SUBJECT CODE
                            lect.lecturer_id if lect else None,    # LECTURER CSV ID
                        )

                        placed = True
                        break

    return True


# -----------------------------------------------------
# VALIDATION — primary algorithm
# -----------------------------------------------------
def is_valid_assignment(timetable, a, day, slot, sections, time_slots, slot_index):

    lecturer_id = a["lecturer_id"]
    subject_id = a["subject_id"]
    sec_name = a["section_name"]
    slot_name = slot.display_name

    lecturer_obj = Lecturer.query.get(lecturer_id)
    subject_obj = Subject.query.get(subject_id)

    if not lecturer_obj or not subject_obj:
        return False

    lecturer_csv_id = lecturer_obj.lecturer_id
    subject_code = subject_obj.code

    # Clash across sections (lecturer or subject at SAME time)
    for sec in timetable:
        v = timetable[sec][day][slot_name]
        if isinstance(v, tuple):
            _, sid, lid, subj_code, lect_code = v

            if lect_code == lecturer_csv_id:
                return False
            if subj_code == subject_code:
                return False

    # Max per day (subject)
    count = 0
    for v in timetable[sec_name][day].values():
        if isinstance(v, tuple) and v[3] == subject_code:
            count += 1
        if count >= a["max_per_day"]:
            return False

    # === NEW RULE: no back-to-back classes for the same lecturer ===
    idx = slot_index.get(slot_name, None)
    if idx is not None:
        neighbour_names = []
        if idx - 1 >= 0:
            neighbour_names.append(time_slots[idx - 1].display_name)
        if idx + 1 < len(time_slots):
            neighbour_names.append(time_slots[idx + 1].display_name)

        for sec in timetable:
            for neigh in neighbour_names:
                v_neigh = timetable[sec][day].get(neigh)
                if isinstance(v_neigh, tuple):
                    _, sid2, lid2, subj_code2, lect_code2 = v_neigh
                    if lect_code2 == lecturer_csv_id:
                        # same lecturer already in previous/next slot → reject
                        return False

    return True


# -----------------------------------------------------
# VALIDATION — fallback
# -----------------------------------------------------
def is_valid_assignment_simple(
    timetable, a, day, slot, sections, time_slots, slot_index
):

    sid = a["class_section_id"]
    subid = a["subject_id"]
    lid = a["lecturer_id"]
    sec_name = next(s.display_name for s in sections if s.id == sid)
    slot_name = slot.display_name

    subj = Subject.query.get(subid)
    lect = Lecturer.query.get(lid)

    if not subj or not lect:
        return False

    sub_code = subj.code
    lect_code = lect.lecturer_id

    # Teacher/subject clash at SAME time
    for sec in timetable:
        v = timetable[sec][day][slot_name]
        if isinstance(v, tuple):
            _, ssid, llid, subj_code, lect_csv = v
            if lect_csv == lect_code:
                return False
            if subj_code == sub_code:
                return False

    # === SAME GAP RULE in fallback ===
    idx = slot_index.get(slot_name, None)
    if idx is not None:
        neighbour_names = []
        if idx - 1 >= 0:
            neighbour_names.append(time_slots[idx - 1].display_name)
        if idx + 1 < len(time_slots):
            neighbour_names.append(time_slots[idx + 1].display_name)

        for sec in timetable:
            for neigh in neighbour_names:
                v_neigh = timetable[sec][day].get(neigh)
                if isinstance(v_neigh, tuple):
                    _, ssid, llid, subj_code2, lect_csv = v_neigh
                    if lect_csv == lect_code:
                        return False

    return True
