# utils.py
from datetime import datetime
import re

def _to_12_hour(time_str):
    try:
        ts = str(time_str).strip()
        if ts == "":
            return ts
        if ts.count(':') == 2:
            ts = ts.rsplit(':', 1)[0]
        dt = datetime.strptime(ts, "%H:%M")
        return dt.strftime("%I:%M %p")
    except Exception:
        return str(time_str)

def canonical_time_range(start_time, end_time):
    s = _to_12_hour(start_time)
    e = _to_12_hour(end_time)
    return f"{s}-{e}"

def slot_key_from_obj(slot):
    """
    Return the canonical slot key in the format:
       "<Name> (HH:MM AM-HH:MM PM)"
    Accepts:
      - TimeSlot model instance (has .name, .start_time, .end_time)
      - dict with keys name/start_time/end_time or start/end
      - tuple/list (name, start, end) or (start, end)
      - string attempt to parse "Name (HH:MM-HH:MM)" style
    """
    # If object has attributes 'name' and times
    start = None; end = None; name = None
    if hasattr(slot, 'name'):
        name = getattr(slot, 'name', None)
        start = getattr(slot, 'start_time', None) or getattr(slot, 'start', None)
        end = getattr(slot, 'end_time', None) or getattr(slot, 'end', None)
    # dict-like
    elif hasattr(slot, 'get'):
        name = slot.get('name') or slot.get('slot_name')
        start = slot.get('start_time') or slot.get('start')
        end = slot.get('end_time') or slot.get('end')
    # list/tuple
    elif isinstance(slot, (list, tuple)):
        if len(slot) == 3:
            name, start, end = slot[0], slot[1], slot[2]
        elif len(slot) == 2:
            start, end = slot[0], slot[1]
    # if we have start & end, format time and include name if present
    if start is not None and end is not None:
        time_range = canonical_time_range(start, end)
        if name:
            return f"{name} ({time_range})"
        else:
            return time_range
    # try parse string "Name (HH:MM-HH:MM)" or "HH:MM-HH:MM"
    s = str(slot)
    m = re.search(r'([A-Za-z0-9\s\-_]+)?\(?\s*(\d{1,2}:\d{2})\s*[-to]\s*(\d{1,2}:\d{2})\s*\)?', s)
    if m:
        possible_name = m.group(1).strip() if m.group(1) else None
        if possible_name:
            return f"{possible_name} ({canonical_time_range(m.group(2), m.group(3))})"
        return canonical_time_range(m.group(2), m.group(3))
    return str(slot)
