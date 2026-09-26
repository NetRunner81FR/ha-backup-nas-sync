"""Constants for the Backup NAS Sync integration."""

DOMAIN = "backup_nas_sync"

CONF_HOST = "host"
CONF_PORT = "port"
CONF_USERNAME = "username"
CONF_AUTH_METHOD = "auth_method"
CONF_PASSWORD = "password"
CONF_KEY_FILE = "key_file"
CONF_ENVIRONMENT = "environment"
CONF_REMOTE_BASE_DIR = "remote_base_dir"
CONF_LOCAL_BACKUP_DIR = "local_backup_dir"
CONF_POLL_INTERVAL = "poll_interval"
CONF_RETENTION_COUNT = "retention_count"
CONF_STABLE_SECONDS = "stable_seconds"

AUTH_PASSWORD = "password"
AUTH_KEY_FILE = "key_file"

ENVIRONMENTS = ["sandbox", "dev", "recette", "prod"]

DEFAULT_PORT = 22
# HA Core (Docker, sans Supervisor) stocke les backups locaux dans
# <config>/backups - pas de volume /backup dedie sur ce projet
# (verifie : environments/*/docker-compose.yml ne montent que /config).
DEFAULT_LOCAL_BACKUP_DIR = "/config/backups"
DEFAULT_REMOTE_BASE_DIR = "/volume1/docker/backups/ha-nas-sync"
DEFAULT_POLL_INTERVAL = 300
DEFAULT_RETENTION_COUNT = 5
DEFAULT_STABLE_SECONDS = 60

NOTIFY_DOMAIN = "notifications_manager"
NOTIFY_SERVICE = "notify"
NOTIFY_MODULE = "ha_backup"
NOTIFY_CATEGORY = "alerte"
NOTIFY_ROLES = ["proprietaire"]

STORAGE_VERSION = 1
STORAGE_KEY_PREFIX = f"{DOMAIN}_state"

STATUS_IDLE = "idle"
STATUS_OK = "ok"
STATUS_ERROR = "error"

PLATFORMS = ["sensor", "binary_sensor"]
