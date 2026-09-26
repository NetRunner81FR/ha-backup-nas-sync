# Backup NAS Sync

Integration Home Assistant qui fiabilise la copie des sauvegardes locales
vers un NAS et controle leur integrite par checksum.

## Pourquoi

L'integration native HA Backup ciblant un NAS (agent "NAS Synology")
peut produire des copies corrompues sans avertissement visible avant
qu'une restauration reelle echoue. Ce composant contourne ce chemin :
il ne cree pas de backup, il ne fait que copier de maniere fiable un
backup deja cree en local (sain) vers le NAS, avec verification.

## Fonctionnement

1. Surveille le repertoire local des sauvegardes HA (`<config>/backups`
   par defaut).
2. Des qu'un nouveau backup est detecte et stabilise, calcule son
   empreinte SHA-256.
3. Transfere le fichier vers le NAS par SSH/SFTP.
4. Calcule l'empreinte SHA-256 du fichier cote NAS (commande distante).
5. Compare les deux empreintes :
   - identiques -> synchronisation validee, retention appliquee ;
   - differentes ou erreur -> la copie precedente valide n'est jamais
     ecrasee, notification envoyee via `notifications_manager.notify`.

## Entites

- `sensor.backup_nas_sync_<env>_dernier_controle` : horodatage et
  attributs du dernier controle (resultat, backup, checksums, echecs
  consecutifs).
- `binary_sensor.backup_nas_sync_<env>_probleme` : `on` si le dernier
  cycle a echoue.

## Service

- `backup_nas_sync.sync_now` : force un cycle immediat.

## Configuration

Via l'interface Home Assistant (config_flow) : hote NAS, port,
utilisateur SSH, authentification (mot de passe ou cle privee),
environnement (sandbox/dev/recette/prod - determine le sous-repertoire
NAS cible, isolation stricte entre environnements), repertoires local
et distant, intervalle de verification, retention.

Aucun secret n'est versionne dans ce depot.
