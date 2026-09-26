"""Coordinator for the Backup NAS Sync integration.

Detects completed local Home Assistant backups (native backup, stored
under ``<config>/backups`` for a plain HA Core Docker install - no
Supervisor ``/backup`` mount on this project), transfers them to the
NAS over SSH/SFTP, and verifies the transfer with a SHA-256 checksum
computed on both sides. A failed or mismatched transfer never
overwrites a previously valid NAS copy.
"""
from __future__ import annotations

import hashlib
import logging
import shlex
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .const import (
    CONF_AUTH_METHOD,
    CONF_ENVIRONMENT,
    CONF_HOST,
    CONF_KEY_FILE,
    CONF_LOCAL_BACKUP_DIR,
    CONF_PASSWORD,
    CONF_PORT,
    CONF_POLL_INTERVAL,
    CONF_REMOTE_BASE_DIR,
    CONF_RETENTION_COUNT,
    CONF_STABLE_SECONDS,
    CONF_USERNAME,
    AUTH_KEY_FILE,
    DEFAULT_LOCAL_BACKUP_DIR,
    DEFAULT_POLL_INTERVAL,
    DEFAULT_PORT,
    DEFAULT_REMOTE_BASE_DIR,
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
        base = self._config.get(CONF_REMOTE_BASE_DIR, DEFAULT_REMOTE_BASE_DIR)
        environment = self._config[CONF_ENVIRONMENT]
        return f"{base.rstrip('/')}/{environment}"

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

    async def _async_update_data(self) -> dict[str, Any]:
        await self._async_load_state()
        try:
            result = await self.hass.async_add_executor_job(self._sync_cycle)
        except Exception as err:  # noqa: BLE001 - never let a sync error kill the coordinator
            _LOGGER.exception("backup_nas_sync: cycle de synchronisation en erreur")
            result = {
                "status": STATUS_ERROR,
                "error": str(err),
                "backup_name": self._state.last_synced_filename,
            }

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
    # Executor-side (blocking) logic
    # ------------------------------------------------------------------ #

    def _sync_cycle(self) -> dict[str, Any]:
        candidate = self._find_next_candidate()
        if candidate is None:
            return {"status": self._state.last_status or STATUS_IDLE, "backup_name": None}

        filename, path, mtime = candidate
        retries = self._state.pending_retries.get(filename, 0)
        if retries >= MAX_RETRIES_PER_FILE:
            return {
                "status": STATUS_ERROR,
                "backup_name": filename,
                "error": f"abandon apres {MAX_RETRIES_PER_FILE} tentatives",
            }

        try:
            checksum_source = self._sha256_file(path)
            checksum_nas = self._transfer_and_verify(path, filename, checksum_source)
        except BackupNasSyncError as err:
            self._state.pending_retries[filename] = retries + 1
            return {"status": STATUS_ERROR, "backup_name": filename, "error": str(err)}

        if checksum_source != checksum_nas:
            self._state.pending_retries[filename] = retries + 1
            return {
                "status": STATUS_ERROR,
                "backup_name": filename,
                "error": "checksum NAS different du checksum local",
                "checksum_source": checksum_source,
                "checksum_nas": checksum_nas,
            }

        self._state.pending_retries.pop(filename, None)
        self._state.last_synced_filename = filename
        self._state.last_synced_mtime = mtime
        self._apply_retention()

        return {
            "status": STATUS_OK,
            "backup_name": filename,
            "checksum_source": checksum_source,
            "checksum_nas": checksum_nas,
        }

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
            if mtime == self._state.last_synced_mtime and entry.name == self._state.last_synced_filename:
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
    def _sha256_file(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def _transfer_and_verify(self, local_path: Path, filename: str, checksum_source: str) -> str:
        import paramiko  # imported lazily: only needed in the executor thread

        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            client.connect(
                hostname=self._config[CONF_HOST],
                port=self._config.get(CONF_PORT, DEFAULT_PORT),
                username=self._config[CONF_USERNAME],
                password=self._auth_password(),
                key_filename=self._auth_key_file(),
                timeout=30,
            )
        except Exception as err:  # noqa: BLE001
            raise BackupNasSyncError(f"connexion SSH impossible : {err}") from err

        try:
            remote_dir = self.remote_dir
            self._ensure_remote_dir(client, remote_dir)
            remote_tmp = f"{remote_dir}/.{filename}.uploading"
            remote_final = f"{remote_dir}/{filename}"

            try:
                sftp = client.open_sftp()
                try:
                    sftp.put(str(local_path), remote_tmp)
                finally:
                    sftp.close()
            except Exception as err:  # noqa: BLE001
                self._safe_remove(client, remote_tmp)
                raise BackupNasSyncError(f"transfert SFTP en echec : {err}") from err

            checksum_nas = self._remote_sha256(client, remote_tmp)

            if checksum_nas == checksum_source:
                self._run(client, f"mv {shlex.quote(remote_tmp)} {shlex.quote(remote_final)}")
            else:
                # Copie corrompue : supprimer uniquement le fichier temporaire,
                # jamais une copie NAS precedente valide (remote_final intact).
                self._safe_remove(client, remote_tmp)

            return checksum_nas
        finally:
            client.close()

    def _ensure_remote_dir(self, client, remote_dir: str) -> None:
        self._run(client, f"mkdir -p {shlex.quote(remote_dir)}")

    def _remote_sha256(self, client, remote_path: str) -> str:
        stdout, stderr, code = self._run(client, f"sha256sum {shlex.quote(remote_path)}")
        if code != 0:
            raise BackupNasSyncError(
                f"controle checksum NAS en echec (code {code}) : {stderr.strip()}"
            )
        try:
            return stdout.split()[0]
        except IndexError as err:
            raise BackupNasSyncError("reponse sha256sum NAS inattendue") from err

    def _safe_remove(self, client, remote_path: str) -> None:
        try:
            self._run(client, f"rm -f {shlex.quote(remote_path)}")
        except Exception:  # noqa: BLE001
            _LOGGER.warning("backup_nas_sync: nettoyage du fichier temporaire NAS impossible")

    @staticmethod
    def _run(client, command: str) -> tuple[str, str, int]:
        stdin, stdout, stderr = client.exec_command(command, timeout=60)
        exit_code = stdout.channel.recv_exit_status()
        return stdout.read().decode("utf-8", "replace"), stderr.read().decode("utf-8", "replace"), exit_code

    def _apply_retention(self) -> None:
        import paramiko  # noqa: F401 - reuse connection pattern below

        try:
            self._apply_retention_ssh()
        except Exception:  # noqa: BLE001
            _LOGGER.warning(
                "backup_nas_sync: application de la retention NAS impossible (non bloquant)"
            )

    def _apply_retention_ssh(self) -> None:
        import paramiko

        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(
            hostname=self._config[CONF_HOST],
            port=self._config.get(CONF_PORT, DEFAULT_PORT),
            username=self._config[CONF_USERNAME],
            password=self._auth_password(),
            key_filename=self._auth_key_file(),
            timeout=30,
        )
        try:
            sftp = client.open_sftp()
            try:
                entries = [
                    (attr.filename, attr.st_mtime)
                    for attr in sftp.listdir_attr(self.remote_dir)
                    if attr.filename.endswith(BACKUP_SUFFIX)
                ]
            finally:
                sftp.close()

            entries.sort(key=lambda item: item[1], reverse=True)
            for filename, _mtime in entries[self.retention_count :]:
                # Ne jamais purger la copie la plus recente connue comme valide,
                # meme si retention_count vaut 0 par erreur de configuration.
                if filename == self._state.last_synced_filename:
                    continue
                self._safe_remove(client, f"{self.remote_dir}/{filename}")
        finally:
            client.close()

    def _auth_password(self) -> str | None:
        if self._config.get(CONF_AUTH_METHOD) == AUTH_KEY_FILE:
            return None
        return self._config.get(CONF_PASSWORD)

    def _auth_key_file(self) -> str | None:
        if self._config.get(CONF_AUTH_METHOD) != AUTH_KEY_FILE:
            return None
        return self._config.get(CONF_KEY_FILE)

    async def async_force_sync(self) -> None:
        """Service backup_nas_sync.sync_now."""
        await self.async_request_refresh()
