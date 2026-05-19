def _flatten_text_items(value):
    if isinstance(value, dict):
        items = []
        for key, entries in value.items():
            if isinstance(entries, list):
                for entry in entries:
                    items.append(f"{key}:{entry}")
            elif entries:
                items.append(f"{key}:{entries}")
        return items
    if isinstance(value, list):
        return [str(item) for item in value if item]
    if value:
        return [str(value)]
    return []


def _merge_unique(target, additions):
    seen = set(target)
    for item in additions:
        text = str(item or "").strip()
        if not text or text in seen:
            continue
        target.append(text)
        seen.add(text)


def resolve_meeting_notes(meetings=None, runtime_store=None):
    notes = {
        "risk_notes": [],
        "forbidden_actions": [],
        "forbidden_actions_map": {},
        "next_6h_focus": [],
        "fleet_restrictions": {},
        "capital_adjustments": {},
        "enabled_strategies": [],
        "disabled_strategies": [],
        "source_meeting_id": "",
    }

    meetings = list(meetings or [])
    for meeting in meetings:
        conclusion = dict(meeting.get("conclusion") or {})
        if not conclusion and not meeting.get("summary"):
            continue
        notes["source_meeting_id"] = str(meeting.get("meeting_id") or meeting.get("id") or "")
        _merge_unique(notes["risk_notes"], _flatten_text_items(conclusion.get("risk_notes")))
        _merge_unique(notes["next_6h_focus"], conclusion.get("next_6h_focus", []))
        forbidden = conclusion.get("forbidden_actions", {})
        if isinstance(forbidden, dict):
            notes["forbidden_actions_map"] = dict(forbidden)
            _merge_unique(notes["forbidden_actions"], _flatten_text_items(forbidden))
        else:
            _merge_unique(notes["forbidden_actions"], _flatten_text_items(forbidden))
        notes["fleet_restrictions"] = dict(conclusion.get("fleet_restrictions", {}) or {})
        notes["capital_adjustments"] = dict(conclusion.get("capital_adjustments", {}) or {})
        notes["enabled_strategies"] = list(conclusion.get("enabled_strategies", []) or [])
        notes["disabled_strategies"] = list(conclusion.get("disabled_strategies", []) or [])
        break

    if runtime_store is not None:
        memories = runtime_store.recent_round_table_decision_memory(limit=1)
        if memories:
            memory = dict(memories[0] or {})
            if not notes["source_meeting_id"]:
                notes["source_meeting_id"] = "round_table_memory"
            if memory.get("reason"):
                _merge_unique(notes["risk_notes"], [memory.get("reason")])
            notes["fleet_restrictions"] = {**memory.get("fleet_restrictions", {}), **notes["fleet_restrictions"]}
            notes["capital_adjustments"] = {**memory.get("capital_adjustments", {}), **notes["capital_adjustments"]}
            if memory.get("disabled_strategies"):
                _merge_unique(notes["disabled_strategies"], memory.get("disabled_strategies", []))

    return notes
