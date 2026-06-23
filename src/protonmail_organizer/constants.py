"""System label IDs, label types, colors, and free plan limits."""

# System label IDs (built into ProtonMail)
INBOX = "0"
ALL_DRAFTS = "1"
ALL_SENT = "2"
TRASH = "3"
SPAM = "4"
ALL_MAIL = "5"
ARCHIVE = "6"
SENT = "7"
DRAFTS = "8"
OUTBOX = "9"
STARRED = "10"
SCHEDULED = "12"

SYSTEM_LABELS = {
    INBOX: "Inbox",
    ALL_DRAFTS: "All Drafts",
    ALL_SENT: "All Sent",
    TRASH: "Trash",
    SPAM: "Spam",
    ALL_MAIL: "All Mail",
    ARCHIVE: "Archive",
    SENT: "Sent",
    DRAFTS: "Drafts",
    OUTBOX: "Outbox",
    STARRED: "Starred",
    SCHEDULED: "Scheduled",
}

# Label type IDs used by the API
LABEL_TYPE_LABEL = 1  # User-defined labels
LABEL_TYPE_FOLDER = 3  # User-defined folders
LABEL_TYPE_SYSTEM = 4  # System labels

# Free plan limits
FREE_PLAN_MAX_LABELS = 3
FREE_PLAN_MAX_FOLDERS = 3

# Batch operation settings
BATCH_SIZE = 50
BATCH_DELAY_SECONDS = 0.2

# Available label colors (ProtonMail's palette)
LABEL_COLORS = [
    "#7272a7",
    "#8989ac",
    "#cf5858",
    "#cf7e7e",
    "#c26cc7",
    "#c793ca",
    "#7569d1",
    "#9b94d1",
    "#69a9d1",
    "#a8c4d5",
    "#5ec7b7",
    "#97c9c1",
    "#72bb75",
    "#9db99f",
    "#c3d261",
    "#c6cd97",
    "#e6c04c",
    "#e7d292",
    "#e6984c",
    "#dfb286",
    "#8d7f6b",
    "#b4a898",
]

DEFAULT_LABEL_COLOR = "#7272a7"

# API base for mail operations
API_BASE_MAIL = "mail"
API_BASE_CORE = "core"
