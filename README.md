# Backup NAS Sync

Integration Home Assistant qui fiabilise la copie des sauvegardes locales
vers un NAS Synology distant (accessible en HTTPS) et controle leur
integrite par checksum.

## Pourquoi

L'agent de sauvegarde natif Synology de HA Backup peut produire des
copies corrompues sans avertissement visible avant qu'une restauration
reelle echoue. Ce composant contourne ce chemin : il ne cree pas de
backup, il ne fait que copier de maniere fiable un backup deja cree en
local (sain) vers le NAS, avec verification par round-trip.

## Fonctionnement

1. Surveille le repertoire local des sauvegardes HA (`<config>/backups`
   par defaut).
2. Des qu'un nouveau backup est detecte et stabilise, calcule son
   empreinte SHA-256 et le lit en memoire.
3. Transfere le fichier vers le NAS (API FileStation, HTTPS) sous un nom
   temporaire.
4. Retelecharge cette copie temporaire et recalcule son empreinte
   SHA-256 (verification reelle de bout en bout, pas seulement une
   confirmation d'ecriture).
5. Si les empreintes correspondent : upload sous le nom final, retention
   appliquee, fichier temporaire supprime. Sinon : fichier temporaire
   supprime, aucune copie valide existante n'est touchee, notification
   envoyee via `notifications_manager.notify`.

## Pas de nouveaux identifiants

Ce composant ne demande jamais d'hote/utilisateur/mot de passe NAS : il
reutilise la connexion DSM deja authentifiee d'une integration
**Synology DSM** (`synology_dsm`) deja configuree sur cette instance
Home Assistant. Installation identique et simple sur plusieurs
instances HA distinctes partageant le meme NAS distant.

## Entites

- `sensor.backup_nas_sync_<site>_dernier_controle` : horodatage et
  attributs du dernier controle (resultat, backup, checksums, echecs
  consecutifs).
- `binary_sensor.backup_nas_sync_<site>_probleme` : `on` si le dernier
  cycle a echoue.

## Service

- `backup_nas_sync.sync_now` : force un cycle immediat.

## Configuration

Via l'interface Home Assistant (config_flow) : choix de l'integration
Synology DSM a utiliser, nom du site (namespace le repertoire NAS cible
- isolation entre plusieurs installations HA partageant le meme NAS),
repertoires local et distant, intervalle de verification, retention.

Aucun secret n'est versionne dans ce depot.
