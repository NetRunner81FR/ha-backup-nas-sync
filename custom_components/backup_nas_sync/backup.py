"""Native BackupAgent with streamed, verified FileStation publication."""
from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable, Coroutine
from datetime import datetime
import hashlib
import json
import logging
import re
import tempfile
from typing import Any
from uuid import uuid4

from homeassistant.components.backup import (
    AgentBackup, BackupAgent, BackupAgentError, BackupNotFound, OnProgressCallback,
)
from homeassistant.core import HomeAssistant, callback

from .const import DOMAIN, DATA_AGENT_LISTENERS

_LOGGER = logging.getLogger(__name__)
_CHUNK = 1024 * 1024
_META_LIMIT = 1024 * 1024


def _open_staged_reader(file_descriptor: int):
    """Open the staged tar in HA's executor, never from its event loop."""
    return open(file_descriptor, "rb", closefd=False)


async def async_get_backup_agents(hass: HomeAssistant, **kwargs: Any) -> list[BackupAgent]:
    """Expose only loaded entries, keeping a single lock/agent per entry."""
    return [hass.data[DOMAIN][entry.entry_id].agent
            for entry in hass.config_entries.async_loaded_entries(DOMAIN)
            if entry.entry_id in hass.data.get(DOMAIN, {})]


@callback
def async_register_backup_agents_listener(
    hass: HomeAssistant, *, listener: Callable[[], None], **kwargs: Any,
) -> Callable[[], None]:
    listeners = hass.data.setdefault(DATA_AGENT_LISTENERS, [])
    listeners.append(listener)

    @callback
    def unsubscribe() -> None:
        if listener in listeners:
            listeners.remove(listener)

    return unsubscribe


class BackupNasSyncAgent(BackupAgent):
    """Publish metadata only after verifying the actual NAS archive."""

    domain = DOMAIN

    def __init__(self, coordinator) -> None:
        self.coordinator = coordinator
        self.unique_id = coordinator.entry.entry_id
        self.name = coordinator.entry.title
        self._prefix = f"bns-{hashlib.sha256(self.unique_id.encode()).hexdigest()}-"

    def _meta_name(self, backup_id: str) -> str:
        return self._prefix + hashlib.sha256(backup_id.encode()).hexdigest() + ".json"

    @property
    def _fs(self):
        return self.coordinator.file_station

    async def _files(self) -> set[str]:
        """Paginate, fail closed on unavailable API (None is not an empty list)."""
        names: set[str] = set()
        offset = 0
        while True:
            page = await self._fs.get_files(path=self.coordinator.remote_dir, offset=offset, limit=1000)
            if page is None:
                raise BackupAgentError("Liste NAS indisponible")
            fresh = {f.name for f in page if not f.is_dir}
            if page and offset and not fresh.difference(names):
                raise BackupAgentError("Pagination NAS incohérente")
            names.update(fresh)
            if len(page) < 1000:
                return names
            offset += len(page)

    async def _stream(self, filename: str) -> AsyncIterator[bytes]:
        response = await self._fs.download_file(path=self.coordinator.remote_dir, filename=filename)
        if not hasattr(response, "iter_chunked"):
            raise BackupAgentError("Téléchargement NAS indisponible")
        return response.iter_chunked(_CHUNK)

    async def _read_meta(self, filename: str) -> dict:
        data = bytearray()
        async for chunk in await self._stream(filename):
            data.extend(chunk)
            if len(data) > _META_LIMIT:
                raise BackupAgentError("Métadonnées NAS trop volumineuses")
        try:
            record = json.loads(data)
            backup = AgentBackup.from_dict(record["backup"])
            expected = self._meta_name(backup.backup_id)
            tar_prefix = re.escape(expected[:-5])
            date = datetime.fromisoformat(backup.date)
            if (record["schema"] != 1 or expected != filename
                    or not re.fullmatch(tar_prefix + r"-[0-9a-f]{32}\.tar", record["filename"])
                    or not re.fullmatch(r"[0-9a-f]{64}", record["sha256"])
                    or not isinstance(backup.size, int) or isinstance(backup.size, bool)
                    or backup.size < 0 or date.tzinfo is None):
                raise ValueError("invalid metadata")
        except (KeyError, TypeError, ValueError, AttributeError) as err:
            raise BackupAgentError("Métadonnées NAS invalides ; aucune purge effectuée") from err
        return record

    async def _records(self, names: set[str]) -> dict[str, dict]:
        records = {}
        for name in sorted(names):
            if re.fullmatch(re.escape(self._prefix) + r"[0-9a-f]{64}\.json", name):
                record = await self._read_meta(name)
                records[record["backup"]["backup_id"]] = record
        return records

    async def _get_record(self, backup_id: str) -> dict:
        names = await self._files()
        if self._meta_name(backup_id) not in names:
            raise BackupNotFound("Sauvegarde absente du NAS")
        record = await self._read_meta(self._meta_name(backup_id))
        if record["filename"] not in names:
            raise BackupNotFound("Archive NAS absente")
        return record

    async def _hash(self, filename: str) -> tuple[str, int]:
        digest = hashlib.sha256()
        size = 0
        async for chunk in await self._stream(filename):
            digest.update(chunk)
            size += len(chunk)
        return digest.hexdigest(), size

    async def async_list_backups(self, **kwargs: Any) -> list[AgentBackup]:
        try:
            async with self.coordinator.lock:
                names = await self._files()
                records = await self._records(names)
                return [AgentBackup.from_dict(r["backup"]) for r in records.values()
                        if r["filename"] in names]
        except BackupAgentError:
            raise
        except Exception as err:
            raise BackupAgentError("Impossible de lister les sauvegardes NAS") from err

    async def async_get_backup(self, backup_id: str, **kwargs: Any) -> AgentBackup:
        try:
            async with self.coordinator.lock:
                return AgentBackup.from_dict((await self._get_record(backup_id))["backup"])
        except BackupAgentError:
            raise
        except Exception as err:
            raise BackupAgentError("Impossible de lire la sauvegarde NAS") from err

    async def async_download_backup(self, backup_id: str, **kwargs: Any) -> AsyncIterator[bytes]:
        """Return an iterator, not an async generator function, as required by HA."""
        # Resolve absence immediately; revalidate under lock when the consumer starts.
        await self.async_get_backup(backup_id)

        async def verified_stream() -> AsyncIterator[bytes]:
            try:
                async with self.coordinator.lock:
                    record = await self._get_record(backup_id)
                    digest = hashlib.sha256()
                    size = 0
                    async for chunk in await self._stream(record["filename"]):
                        digest.update(chunk)
                        size += len(chunk)
                        yield chunk
                    if digest.hexdigest() != record["sha256"] or size != record["backup"]["size"]:
                        raise BackupAgentError("Archive NAS corrompue : checksum ou taille incorrect")
            except BackupAgentError:
                raise
            except Exception as err:
                raise BackupAgentError("Téléchargement NAS interrompu") from err

        return verified_stream()

    async def _delete(self, filename: str) -> None:
        if not await self._fs.delete_file(path=self.coordinator.remote_dir, filename=filename):
            raise BackupAgentError("Suppression NAS refusée")

    async def _delete_record(self, backup_id: str, record: dict, names: set[str]) -> None:
        if record["filename"] in names:
            await self._delete(record["filename"])
        await self._delete(self._meta_name(backup_id))

    async def async_delete_backup(self, backup_id: str, **kwargs: Any) -> None:
        try:
            async with self.coordinator.lock:
                names = await self._files()
                meta = self._meta_name(backup_id)
                if meta not in names:
                    raise BackupNotFound("Sauvegarde absente du NAS")
                record = await self._read_meta(meta)
                await self._delete_record(backup_id, record, names)
        except BackupAgentError:
            raise
        except Exception as err:
            raise BackupAgentError("Impossible de supprimer la sauvegarde NAS") from err

    async def _retention(self, protected_id: str) -> str | None:
        """Never fail a verified upload because retention failed."""
        try:
            names = await self._files()
            records = await self._records(names)
            others = sorted(
                ((key, r) for key, r in records.items() if key != protected_id),
                key=lambda item: (datetime.fromisoformat(item[1]["backup"]["date"]), item[0]),
                reverse=True,
            )
            failed = False
            for key, record in others[max(1, self.coordinator.retention_count) - 1:]:
                try:
                    await self._delete_record(key, record, names)
                except Exception:  # continue independent deletions, never hide the warning
                    failed = True
            return "Rétention NAS incomplète ; transfert vérifié conservé" if failed else None
        except Exception:
            return "Rétention NAS indisponible ; transfert vérifié conservé"

    async def _record_result(self, **kwargs: Any) -> None:
        try:
            await self.coordinator.async_record_result(**kwargs)
        except Exception:
            # Storage/notifications must never turn a committed upload into a failure.
            _LOGGER.exception("Impossible de publier le diagnostic du transfert NAS")

    async def async_upload_backup(
        self, *, open_stream: Callable[[], Coroutine[Any, Any, AsyncIterator[bytes]]],
        backup: AgentBackup, on_progress: OnProgressCallback, **kwargs: Any,
    ) -> None:
        async with self.coordinator.lock:
            filename = self._meta_name(backup.backup_id)[:-5] + f"-{uuid4().hex}.tar"
            published = False
            metadata_attempted = False
            checksum_source = None
            checksum_nas = None
            try:
                # An absent folder is not silently treated as an empty NAS. Configure
                # an existing dedicated FileStation folder before selecting the agent.
                names = await self._files()
                meta_name = self._meta_name(backup.backup_id)
                existing = await self._read_meta(meta_name) if meta_name in names else None
                # DSM FileStation corrupts chunked multipart uploads of an
                # AsyncIterator on the real SANDBOX NAS (same byte count, wrong
                # SHA-256). Materialize the HA-provided stream once in a secure,
                # auto-unlinked temporary file, then send a seekable reader with
                # a known Content-Length. This is NOT a backup-folder scan.
                digest = hashlib.sha256()
                size = 0
                with tempfile.TemporaryFile(
                    mode="w+b", dir=self.coordinator.hass.config.path(".storage")
                ) as staged:
                    stream = await open_stream()
                    try:
                        async for chunk in stream:
                            digest.update(chunk)
                            size += len(chunk)
                            await self.coordinator.hass.async_add_executor_job(
                                staged.write, chunk
                            )
                    finally:
                        if hasattr(stream, "aclose"):
                            await stream.aclose()
                    if size != backup.size:
                        raise BackupAgentError("Taille du flux HA incorrecte")
                    await self.coordinator.hass.async_add_executor_job(staged.flush)
                    await self.coordinator.hass.async_add_executor_job(staged.seek, 0)
                    # `open` and `close` are filesystem operations: schedule both
                    # outside HA's event loop.  The reader stays open across the
                    # awaited FileStation upload and is always closed on failure.
                    source = await self.coordinator.hass.async_add_executor_job(
                        _open_staged_reader, staged.fileno()
                    )
                    try:
                        uploaded = await self._fs.upload_file(
                            path=self.coordinator.remote_dir, filename=filename,
                            source=source, create_parents=False,
                        )
                    finally:
                        await self.coordinator.hass.async_add_executor_job(source.close)
                    if not uploaded:
                        raise BackupAgentError("Transfert NAS refusé")
                    on_progress(bytes_uploaded=size)
                checksum_source = digest.hexdigest()
                checksum_nas, nas_size = await self._hash(filename)
                if size != backup.size or nas_size != size or checksum_source != checksum_nas:
                    _LOGGER.warning(
                        "Vérification NAS : source_bytes=%s expected_bytes=%s "
                        "nas_bytes=%s sha256_equal=%s",
                        size, backup.size, nas_size, checksum_source == checksum_nas,
                    )
                    raise BackupAgentError("Vérification NAS échouée : checksum ou taille incorrect")
                if existing:
                    if (existing["backup"] != backup.as_dict() or existing["sha256"] != checksum_source):
                        raise BackupAgentError("Conflit : identifiant de sauvegarde déjà présent")
                    # Do not silently accept an already corrupted committed copy.
                    old_hash, old_size = await self._hash(existing["filename"])
                    if old_hash != checksum_source or old_size != size:
                        raise BackupAgentError("Copie NAS existante corrompue ; réparation manuelle requise")
                else:
                    record = {"schema": 1, "backup": backup.as_dict(),
                              "filename": filename, "sha256": checksum_source}
                    encoded = json.dumps(record, ensure_ascii=True).encode()
                    if len(encoded) > _META_LIMIT:
                        raise BackupAgentError("Métadonnées trop volumineuses")
                    metadata_attempted = True
                    if not await self._fs.upload_file(path=self.coordinator.remote_dir,
                                                     filename=meta_name, source=encoded, create_parents=False):
                        raise BackupAgentError("Publication des métadonnées NAS refusée")
                    if await self._read_meta(meta_name) != record:
                        raise BackupAgentError("Vérification des métadonnées NAS échouée")
                    published = True
                warning = await self._retention(backup.backup_id)
                await self._record_result(backup_name=backup.name, checksum_source=checksum_source,
                                          checksum_nas=checksum_nas, retention_warning=warning)
            except asyncio.CancelledError:
                raise
            except Exception as err:
                # Do not expose DSM exception payloads (may contain private API data).
                message = str(err) if isinstance(err, BackupAgentError) else "Transfert NAS indisponible ou interrompu"
                await self._record_result(backup_name=backup.name, error=message,
                                          checksum_source=checksum_source, checksum_nas=checksum_nas)
                raise BackupAgentError(message) from err
            finally:
                if not published:
                    # If metadata publication is ambiguous, keep archive rather than
                    # risk deleting a backup the NAS has actually committed.
                    if not metadata_attempted:
                        try:
                            await self._delete(filename)
                        except Exception:
                            _LOGGER.warning("Objet NAS de tentative non nettoyé ; aucune copie validée supprimée")
