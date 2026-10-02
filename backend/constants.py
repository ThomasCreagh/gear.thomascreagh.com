"""Shared domain values used by the API and database models."""

LOCKERS = ["outdoor", "top", "bottom", "pad"]
LOCKER_LABELS = {
    "outdoor": "Outdoor Locker",
    "top": "Top Locker",
    "bottom": "Bottom Locker",
    "pad": "Pad Stash",
}

ITEM_STATUSES = ["active", "retired", "missing"]

CATEGORIES = [
    "harness", "pad", "rope", "cam", "quickdraw", "nut", "carabiner",
    "helmet", "belay_device", "sling", "rope_protector", "misc_trad", "misc",
]

CATEGORY_LABELS = {
    "harness": "Harness", "pad": "Pad", "rope": "Rope", "cam": "Cam",
    "quickdraw": "Quickdraw", "nut": "Nut", "carabiner": "Carabiner",
    "helmet": "Helmet", "belay_device": "Belay Device", "sling": "Sling",
    "rope_protector": "Rope Protector", "misc_trad": "Misc Trad", "misc": "Misc",
}
