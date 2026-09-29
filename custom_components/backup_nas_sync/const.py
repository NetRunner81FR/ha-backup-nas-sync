"""Constants for the Backup NAS Sync integration."""

DOMAIN = "backup_nas_sync"

SYNOLOGY_DSM_DOMAIN = "synology_dsm"

CONF_SYNOLOGY_ENTRY_ID = "synology_entry_id"
CONF_SITE_NAME = "site_name"
CONF_REMOTE_BASE_DIR = "remote_base_dir"
CONF_RETENTION_COUNT = "retention_count"

DEFAULT_RETENTION_COUNT = 5
DATA_AGENT_LISTENERS = f"{DOMAIN}_agent_listeners"

NOTIFY_DOMAIN = "notifications_manager"
NOTIFY_SERVICE = "notify"
NOTIFY_MODULE = "ha_backup"
NOTIFY_CATEGORY = "alerte"
NOTIFY_ROLES = ["proprietaire"]


STATUS_IDLE = "idle"
STATUS_OK = "ok"
STATUS_ERROR = "error"

PLATFORMS = ["sensor", "binary_sensor"]
