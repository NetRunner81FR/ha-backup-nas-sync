# NR Backup NAS Sync

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
2. Des qu'un nouveau backup est detecte et stabilise (aucune modification
   depuis `stable_seconds`), calcule son empreinte SHA-256 et le lit en
   memoire.
3. Transfere le fichier vers le NAS (API FileStation, HTTPS) sous un nom
   temporaire (`<nom>.uploading`).
4. Retelecharge cette copie temporaire et recalcule son empreinte
   SHA-256 (verification reelle de bout en bout, pas seulement une
   confirmation d'ecriture - il n'existe pas d'API de checksum distant
   native sur FileStation).
5. Si les empreintes correspondent : upload sous le nom final (pas de
   rename cote FileStation - un second envoi des memes octets), retention
   appliquee (les copies les plus anciennes au-dela de `retention_count`
   sont supprimees, jamais la derniere copie valide), fichier temporaire
   supprime. Si elles different, ou si une etape echoue : fichier
   temporaire supprime, aucune copie valide existante n'est touchee,
   nouvelle tentative au cycle suivant (3 tentatives maximum par fichier,
   puis abandon pour laisser la file progresser sur les fichiers plus
   recents), notification envoyee via `notifications_manager.notify`
   uniquement sur transition (echec initial, ou retour a la normale -
   jamais a chaque succes repete).

## Pas de nouveaux identifiants

Ce composant ne demande jamais d'hote/utilisateur/mot de passe NAS : il
reutilise la connexion DSM deja authentifiee d'une integration
**Synology DSM** (`synology_dsm`) deja configuree sur cette instance
Home Assistant. Installation identique et simple sur plusieurs
instances HA distinctes partageant le meme NAS distant.

## Entites

- `sensor.backup_nas_sync_<site>_dernier_controle` : horodatage et
  attributs du dernier controle (resultat, backup, checksums, echecs
  consecutifs, erreur).
- `binary_sensor.backup_nas_sync_<site>_probleme` : `on` si le dernier
  cycle a echoue.

## Service

- `backup_nas_sync.sync_now` : force un cycle immediat (sans attendre
  `poll_interval`).

## Configuration initiale

Via l'interface Home Assistant (Parametres > Appareils et services >
Ajouter une integration > NR Backup NAS Sync) :

| Parametre | Role |
| --- | --- |
| Integration Synology DSM a utiliser | Quelle connexion `synology_dsm` deja configuree reutiliser. |
| Nom du site | Identifie ce lieu/cette instance dans le nom des entites - n'affecte pas le chemin NAS. **Non modifiable apres creation** (voir ci-dessous). |
| Repertoire NAS cible | Chemin FileStation complet et definitif (ex. `/BackUpHA/ha_backup_recette`) - jamais de prefixe `/volumeN/`, le dossier partage Synology est adresse directement par son nom. |
| Repertoire local des backups | Ou HA stocke ses sauvegardes locales (`/config/backups` par defaut, installation Docker standard sans Supervisor). |
| Intervalle de verification | Frequence de detection d'un nouveau backup pret a synchroniser. |
| Nombre de versions conservees | Retention sur le NAS - la derniere copie valide n'est jamais purgee. |
| Delai de stabilisation | Duree sans modification du fichier local avant de le considerer complet. |

## Modifier les parametres

Depuis Parametres > Appareils et services > NR Backup NAS Sync > menu
"..." de l'entree > **Configurer** : tous les parametres ci-dessus sauf
le nom du site sont modifiables sans supprimer/recreer l'integration -
la synchronisation reprend avec les nouvelles valeurs immediatement
(rechargement automatique de l'entree, pas de redemarrage HA requis).
Renommer un site reste une operation de suppression/recreation
(rare en pratique, le nom du site ne sert qu'a l'affichage).

## Aucun secret versionne

Aucun identifiant NAS n'est gere ni stocke par ce composant - il ne fait
que reutiliser une session `synology_dsm` deja authentifiee par ailleurs.
