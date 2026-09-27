"""Coordinator for the Backup NAS Sync integration.

Detects completed local Home Assistant backups (native backup, stored
under ``<config>/backups`` for a plain HA Core Docker install - no
Supervisor ``/backup`` mount on this project), transfers them to the
NAS via the Synology FileStation API (``py-synologydsm-api``, the same
library used by HA's native ``synology_dsm`` integration - reuses the
proven DSM connectivity instead of a bespoke SSH credential), and
verifies the transfer by downloading the copy back and comparing its
SHA-256 checksum against the local source. A failed or mismatched
transfer never leaves a file under the final backup filename.
"""
from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util
from synology_dsm.exceptions import SynologyDSMException

from .const import (
    CONF_LOCAL_BACKUP_DIR,
    CONF_POLL_INTERVAL,
    CONF_REMOTE_BASE_DIR,
    CONF_RETENTION_COUNT,
    CONF_SITE_NAME,
    CONF_STABLE_SECONDS,
    CONF_SYNOLOGY_ENTRY_ID,
    DEFAULT_LOCAL_BACKUP_DIR,
    DEFAULT_POLL_INTERVAL,
    DEFAULT_RETENTION_COUNT,
    DEFAULT_STABLE_SECONDS,
    DOMAIN,
    NOTIFY_CATEGORY,
    NOTIFY_DOMAIN,
    NOTIFY_MODULE,
    NOTIFY_ROLES,
    NOTIFY_SERVICE,
    STATUS_ERROR,
    STATUS_IDLE,
    STATUS_OK,
    STORAGE_KEY_PREFIX,
    STORAGE_VERSION,
    UPLOAD_SUFFIX,
)

_LOGGER = logging.getLogger(__name__)

MAX_RETRIES_PER_FILE = 3
BACKUP_SUFFIX = ".tar"


@dataclass
class _PersistedState:
    """Small persisted state surviving HA restarts."""

    last_synced_filename: str | None = None
    last_synced_mtime: float | None = None
    consecutive_failures: int = 0
    last_status: str = STATUS_IDLE
    pending_retries: dict[str, int] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "_PersistedState":
        if not data:
            return cls()
        return cls(
            last_synced_filename=data.get("last_synced_filename"),
            last_synced_mtime=data.get("last_synced_mtime"),
            consecutive_failures=data.get("consecutive_failures", 0),
            last_status=data.get("last_status", STATUS_IDLE),
            pending_retries=data.get("pending_retries", {}) or {},
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "last_synced_filename": self.last_synced_filename,
            "last_synced_mtime": self.last_synced_mtime,
            "consecutive_failures": self.consecutive_failures,
            "last_status": self.last_status,
            "pending_retries": self.pending_retries,
        }


class BackupNasSyncError(Exception):
    """Raised for any transfer/verification failure - never fatal to the coordinator."""


class BackupNasSyncCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Polls the local backup directory and syncs new backups to the NAS."""

    def __init__(self, hass: HomeAssistant, entry) -> None:
        self.entry = entry
        self._config = entry.data
        poll_interval = self._config.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL)
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=poll_interval),
        )
        self._store: Store = Store(
            hass, STORAGE_VERSION, f"{STORAGE_KEY_PREFIX}_{entry.entry_id}"
        )
        self._state = _PersistedState()
        self._state_loaded = False

    @property
    def local_backup_dir(self) -> Path:
        return Path(self._config.get(CONF_LOCAL_BACKUP_DIR, DEFAULT_LOCAL_BACKUP_DIR))

    @property
    def remote_dir(self) -> str:
        # Chemin NAS cible complet et definitif tel que configure par
        # l'utilisateur (pas de composition automatique avec site_name) :
        # chaque site choisit son propre repertoire, coherent avec la
        # convention deja en place sur le NAS (ha_backup_<site>).
        return self._config[CONF_REMOTE_BASE_DIR].rstrip("/")

    @property
    def stable_seconds(self) -> int:
        return self._config.get(CONF_STABLE_SECONDS, DEFAULT_STABLE_SECONDS)

    @property
    def retention_count(self) -> int:
        return self._config.get(CONF_RETENTION_COUNT, DEFAULT_RETENTION_COUNT)

    async def _async_load_state(self) -> None:
        if self._state_loaded:
            return
        stored = await self._store.async_load()
        self._state = _PersistedState.from_dict(stored)
        self._state_loaded = True

    async def _async_save_state(self) -> None:
        await self._store.async_save(self._state.as_dict())

    # ------------------------------------------------------------------ #
    # DSM client - reutilise la connexion deja authentifiee de l'entree
    # synology_dsm choisie a la configuration (meme compte/session que
    # l'integration native, aucun identifiant NAS gere par ce composant).
    # ------------------------------------------------------------------ #

    def _get_dsm_client(self):
        entry = self.hass.config_entries.async_get_entry(self._config[CONF_SYNOLOGY_ENTRY_ID])
        if entry is None:
            raise BackupNasSyncError(
                "l'entree synology_dsm associee a ete supprimee - reconfigurer le composant"
            )
        if entry.state != ConfigEntryState.LOADED:
            raise BackupNasSyncError(
                f"l'integration synology_dsm associee n'est pas chargee (etat: {entry.state})"
            )
        try:
            return entry.runtime_data.api.dsm
        except AttributeError as err:
            raise BackupNasSyncError(
                "structure interne de synology_dsm inattendue - version incompatible ?"
            ) from err

    # ------------------------------------------------------------------ #
    # Coordinator update cycle
    # ------------------------------------------------------------------ #

    async def _async_update_data(self) -> dict[str, Any]:
        await self._async_load_state()

        try:
            candidate = await self.hass.async_add_executor_job(self._find_next_candidate)
        except BackupNasSyncError as err:
            result = {"status": STATUS_ERROR, "error": str(err), "backup_name": None}
        else:
            if candidate is None:
                result = {"status": self._state.last_status or STATUS_IDLE, "backup_name": None}
            else:
                filename, path, mtime = candidate
                try:
                    result = await self._sync_one(filename, path, mtime)
                except Exception as err:  # noqa: BLE001 - never let a sync error kill the coordinator
                    _LOGGER.exception("backup_nas_sync: cycle de synchronisation en erreur")
                    result = {"status": STATUS_ERROR, "backup_name": filename, "error": str(err)}

        previous_status = self._state.last_status
        new_status = result["status"]

        if new_status == STATUS_ERROR:
            self._state.consecutive_failures += 1
        elif new_status == STATUS_OK:
            self._state.consecutive_failures = 0
        self._state.last_status = new_status
        await self._async_save_state()

        await self._maybe_notify(previous_status, new_status, result)

        return {
            "status": new_status,
            "last_checked": dt_util.utcnow().isoformat(),
            "backup_name": result.get("backup_name"),
            "checksum_source": result.get("checksum_source"),
            "checksum_nas": result.get("checksum_nas"),
            "consecutive_failures": self._state.consecutive_failures,
            "error": result.get("error"),
        }

    async def _sync_one(self, filename: str, path: Path, mtime: float) -> dict[str, Any]:
        retries = self._state.pending_retries.get(filename, 0)
        if retries >= MAX_RETRIES_PER_FILE:
            _LOGGER.warning(
                "backup_nas_sync: %s abandonne definitivement apres %s tentatives "
                "(last_synced_filename=%s, last_synced_mtime=%s) - un nouveau backup local "
                "ou une remise a zero manuelle de l'etat sont necessaires pour reessayer",
                filename,
                MAX_RETRIES_PER_FILE,
                self._state.last_synced_filename,
                self._state.last_synced_mtime,
            )
            return {
                "status": STATUS_ERROR,
                "backup_name": filename,
                "error": f"abandon apres {MAX_RETRIES_PER_FILE} tentatives",
            }

        remote_dir = self.remote_dir
        temp_name = f"{filename}{UPLOAD_SUFFIX}"

        try:
            checksum_source, data = await self.hass.async_add_executor_job(
                self._read_and_hash, path
            )
            api = self._get_dsm_client()

            uploaded = await api.file.upload_file(
                path=remote_dir, filename=temp_name, source=data, create_parents=True
            )
            if not uploaded:
                raise BackupNasSyncError("upload temporaire refuse par le NAS")

            checksum_nas = await self._download_and_hash(api, remote_dir, temp_name)
        except (BackupNasSyncError, SynologyDSMException) as err:
            # SynologyDSMException couvre les echecs remontes tels quels par
            # la librairie (ex. upload refuse avec code 414 "File already
            # exists" quand un fichier .uploading orphelin subsiste suite a
            # un redemarrage HA survenu au milieu d'un cycle precedent) :
            # sans cette capture, l'erreur echappe au comptage des tentatives
            # et au nettoyage ci-dessous, et le meme echec se reproduit a
            # l'identique indefiniment a chaque cycle.
            _LOGGER.warning(
                "backup_nas_sync: echec upload/verification temporaire pour %s (tentative %s/%s) - %s",
                filename,
                retries + 1,
                MAX_RETRIES_PER_FILE,
                err,
            )
            await self._safe_delete(remote_dir, temp_name)
            self._state.pending_retries[filename] = retries + 1
            return {"status": STATUS_ERROR, "backup_name": filename, "error": str(err)}

        if checksum_source != checksum_nas:
            await self._safe_delete(remote_dir, temp_name)
            self._state.pending_retries[filename] = retries + 1
            return {
                "status": STATUS_ERROR,
                "backup_name": filename,
                "error": "checksum NAS different du checksum local (copie temporaire corrompue)",
                "checksum_source": checksum_source,
                "checksum_nas": checksum_nas,
            }

        # Round-trip verifie OK : place la copie sous son nom final (pas de
        # rename cote API FileStation - un second upload des memes octets
        # locaux, l'echec eventuel de cette etape ne touche jamais un backup
        # different deja present sous son propre nom).
        try:
            uploaded_final = await api.file.upload_file(
                path=remote_dir, filename=filename, source=data, create_parents=True
            )
            if not uploaded_final:
                raise BackupNasSyncError("upload final refuse par le NAS")
        except (BackupNasSyncError, SynologyDSMException) as err:
            _LOGGER.warning(
                "backup_nas_sync: echec upload final pour %s (tentative %s/%s) - %s",
                filename,
                retries + 1,
                MAX_RETRIES_PER_FILE,
                err,
            )
            await self._safe_delete(remote_dir, temp_name)
            self._state.pending_retries[filename] = retries + 1
            return {"status": STATUS_ERROR, "backup_name": filename, "error": str(err)}

        await self._safe_delete(remote_dir, temp_name)
        self._state.pending_retries.pop(filename, None)
        self._state.last_synced_filename = filename
        self._state.last_synced_mtime = mtime

        await self._apply_retention(api, remote_dir)

        return {
            "status": STATUS_OK,
            "backup_name": filename,
            "checksum_source": checksum_source,
            "checksum_nas": checksum_nas,
        }

    async def _maybe_notify(
        self, previous_status: str, new_status: str, result: dict[str, Any]
    ) -> None:
        """Notify only on transition to error, or on recovery - never on repeat OK."""
        if new_status == STATUS_ERROR and previous_status != STATUS_ERROR:
            await self._async_notify(
                title="Backup NAS Sync - echec",
                message=(
                    f"Echec de synchronisation vers le NAS : {result.get('error', 'inconnu')}. "
                    f"Backup concerne : {result.get('backup_name', 'n/a')}. "
                    "La derniere copie NAS valide n'a pas ete modifiee."
                ),
            )
        elif new_status == STATUS_OK and previous_status == STATUS_ERROR:
            await self._async_notify(
                title="Backup NAS Sync - retour a la normale",
                message="La synchronisation des sauvegardes vers le NAS a repris normalement.",
            )

    async def _async_notify(self, title: str, message: str) -> None:
        if not self.hass.services.has_service(NOTIFY_DOMAIN, NOTIFY_SERVICE):
            _LOGGER.warning(
                "backup_nas_sync: %s.%s indisponible, notification non envoyee",
                NOTIFY_DOMAIN,
                NOTIFY_SERVICE,
            )
            return
        await self.hass.services.async_call(
            NOTIFY_DOMAIN,
            NOTIFY_SERVICE,
            {
                "title": title,
                "message": message,
                "category": NOTIFY_CATEGORY,
                "roles": NOTIFY_ROLES,
                "module": NOTIFY_MODULE,
            },
            blocking=True,
        )

    # ------------------------------------------------------------------ #
    # Local filesystem (executor-side, blocking)
    # ------------------------------------------------------------------ #

    def _find_next_candidate(self) -> tuple[str, Path, float] | None:
        """Return the oldest unsynced, stabilised backup file - or None."""
        if not self.local_backup_dir.is_dir():
            raise BackupNasSyncError(
                f"repertoire local introuvable : {self.local_backup_dir}"
            )

        now = datetime.now().timestamp()
        candidates: list[tuple[float, str, Path]] = []
        for entry in self.local_backup_dir.iterdir():
            if not entry.is_file() or entry.suffix != BACKUP_SUFFIX:
                continue
            mtime = entry.stat().st_mtime
            if entry.name == self._state.last_synced_filename and mtime == self._state.last_synced_mtime:
                continue
            if self._state.last_synced_mtime and mtime <= self._state.last_synced_mtime:
                continue
            if (now - mtime) < self.stable_seconds:
                continue  # not stabilised yet, revisit next cycle
            candidates.append((mtime, entry.name, entry))

        if not candidates:
            return None
        candidates.sort(key=lambda item: item[0])
        mtime, filename, path = candidates[0]
        return filename, path, mtime

    @staticmethod
    def _read_and_hash(path: Path) -> tuple[str, bytes]:
        data = path.read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        return digest, data

    # ------------------------------------------------------------------ #
    # NAS FileStation (async)
    # ------------------------------------------------------------------ #

    async def _download_and_hash(self, api, remote_dir: str, filename: str) -> str:
        from aiohttp import StreamReader

        stream = await api.file.download_file(remote_dir, filename)
        if not isinstance(stream, StreamReader):
            raise BackupNasSyncError("telechargement de controle impossible depuis le NAS")

        digest = hashlib.sha256()
        async for chunk in stream.iter_chunked(1024 * 1024):
            digest.update(chunk)
        return digest.hexdigest()

    async def _safe_delete(self, remote_dir: str, filename: str) -> None:
        try:
            api = self._get_dsm_client()
            deleted = await api.file.delete_file(remote_dir, filename)
        except Exception:  # noqa: BLE001
            _LOGGER.warning(
                "backup_nas_sync: nettoyage du fichier temporaire NAS impossible (exception) - %s",
                filename,
            )
            return
        if not deleted:
            # L'API Synology peut repondre sans lever d'exception tout en
            # signalant un echec (success=False/None) - sans ce controle,
            # un fichier .uploading orphelin non supprime declenchait un
            # "File already exists" identique a chaque nouvelle tentative,
            # jusqu'a l'abandon definitif, sans aucune trace exploitable
            # dans les logs.
            _LOGGER.warning(
                "backup_nas_sync: suppression refusee par le NAS (reponse: %s) - %s",
                deleted,
                filename,
            )

    async def _apply_retention(self, api, remote_dir: str) -> None:
        try:
            files = await api.file.get_files(remote_dir)
        except Exception:  # noqa: BLE001
            _LOGGER.warning(
                "backup_nas_sync: application de la retention NAS impossible (non bloquant)"
            )
            return

        if not files:
            return

        backups = [
            entry
            for entry in files
            if not entry.is_dir and entry.name.endswith(BACKUP_SUFFIX) and not entry.name.endswith(UPLOAD_SUFFIX)
        ]
        backups.sort(
            key=lambda entry: entry.additional.time.mtime if entry.additional else 0,
            reverse=True,
        )
        for entry in backups[self.retention_count :]:
            # Ne jamais purger la copie la plus recente connue comme valide,
            # meme si retention_count vaut 0 par erreur de configuration.
            if entry.name == self._state.last_synced_filename:
                continue
            await self._safe_delete(remote_dir, entry.name)

    async def async_force_sync(self) -> None:
        """Service backup_nas_sync.sync_now."""
        await self.async_request_refresh()
