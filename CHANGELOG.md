# Changelog

## 0.1.0-beta.1

- Initial staging : detection des backups locaux, transfert SSH/SFTP
  vers le NAS, verification checksum SHA-256 source/destination,
  non-ecrasement d'une copie valide en cas d'echec, retention, service
  `sync_now`, notifications via `notifications_manager.notify` sur
  transition d'etat (echec / retour a la normale uniquement).
