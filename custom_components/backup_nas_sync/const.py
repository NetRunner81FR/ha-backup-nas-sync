"""Constants for the Backup NAS Sync integration."""

DOMAIN = "backup_nas_sync"

SYNOLOGY_DSM_DOMAIN = "synology_dsm"

CONF_SYNOLOGY_ENTRY_ID = "synology_entry_id"
CONF_SITE_NAME = "site_name"
CONF_REMOTE_BASE_DIR = "remote_base_dir"
CONF_LOCAL_BACKUP_DIR = "local_backup_dir"
CONF_POLL_INTERVAL = "poll_interval"
CONF_RETENTION_COUNT = "retention_count"
CONF_STABLE_SECONDS = "stable_seconds"

# HA Core (Docker, sans Supervisor) stocke les backups locaux dans
# <config>/backups - pas de volume /backup dedie sur ce projet
# (verifie : environments/*/docker-compose.yml ne montent que /config).
# Sur d'autres installations (HAOS/Supervisor), /backup peut etre le bon
# chemin - configurable a l'installation.
DEFAULT_LOCAL_BACKUP_DIR = "/config/backups"
# Chemin FileStation cible - champ requis, pas de valeur par defaut :
# chaque installation choisit son propre repertoire, coherent avec la
# convention deja en place sur le NAS (ex. /BackUpHA/ha_backup_<site>).
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

UPLOAD_SUFFIX = ".uploading"
