# NR Backup NAS Sync - native BackupAgent

Candidate **0.5.0-beta.1**, Home Assistant **2026.9.3 minimum**.
Cycle reel SANDBOX (upload natif, round-trip SHA-256, reprise apres restart)
valide le 2026-09-29 ; l'UI Backup affiche encore une erreur d'une autre
destination Synology DSM. Ne pas installer en PROD sur cette base. Aucun secret NAS supplementaire n'est demande.

## Fonctionnement

1. Le gestionnaire Backup HA fournit un flux (Core Docker comme HAOS/Supervisor).
2. L'agent spoule ce flux dans un fichier temporaire non nomme, 0600, sous `.storage` (sans scanner les sauvegardes locales ni charger le tar entier en RAM), puis le transfere avec une taille connue via FileStation. SHA-256 est calcule pendant le staging.
3. Il relit l'archive NAS effectivement ecrite et compare SHA-256 et taille.
4. Il publie et relit les metadonnees natives seulement apres cette verification.
5. Il applique sa propre retention NAS, sans jamais supprimer le nouvel upload.

Un sensor expose le dernier transfert (et non un controle periodique). Le binary
sensor signale une erreur de transfert ou un avertissement de retention. Les
notifications passent uniquement par notifications_manager.notify avec category
`alerte`, roles `proprietaire`, module `ha_backup` ; sans ce service les diagnostics
restent disponibles dans les entites et l'interface Backup.

## Installation / configuration

- SANDBOX #185 : installer directement depuis la branche SANDBOX par le script
  ad hoc `deploy-ha-sandbox.sh` (autorisation utilisateur 2026-09-29), sans
  publication GitHub/HACS. Le script copie `ha-config/custom_components` et
  redemarre HA. Ne jamais utiliser de copie SSH/rsync/Docker manuelle.
- Avant DEV, prevoir la publication beta HACS et le cycle de promotion normal.
- Configurer et charger Synology DSM avec un compte FileStation adapte.
- Creer un dossier FileStation dedie a cette instance, distinct entre environnements.
- Ajouter NR Backup NAS Sync : choisir l'entree DSM, le site, le dossier absolu
  FileStation (par exemple `/Backups/sandbox`, jamais `/volume1/Backups/...`) et
  le nombre de sauvegardes a conserver (minimum 1, defaut 5).
- Dans Parametres > Systeme > Sauvegardes, selectionner explicitement cet agent
  comme destination. L'integration ne change ni calendrier, ni chiffrement, ni
  destinations existantes. Conserver une destination locale de secours.
- Pour modifier les parametres, utiliser Reconfigurer sur l'entree existante.
  Ne pas supprimer/recreer l'entree : son entry_id identifie les archives NAS.

Le staging est ferme/supprime automatiquement, meme si HA redemarre ou l'upload echoue. Sur un tres gros backup, prevoir assez d'espace libre sur le volume de configuration HA. La progression UI est rapportee apres transfert FileStation, sans granularite pendant l'upload.

La bibliotheque DSM est celle epinglee par l'integration native Synology DSM de HA
(pas de dependance concurrente installee par ce composant).

## Migration depuis v0.4.0

Sauvegarder la configuration HA avant promotion manuelle. La migration v1 -> v2
conserve l'entree, la connexion DSM, le site et le dossier cible. Elle retire
`local_backup_dir`, `poll_interval`, `stable_seconds` de data/options. Aucun
fallback filesystem : les sauvegardes existantes ne sont pas scannees ni transferees
automatiquement. Utiliser le flux natif de creation/upload HA.

`retention_count` est conserve (0/negatif devient 1 ; valeur invalide devient 5).
`backup_nas_sync.sync_now` disparait : adapter les automatisations et boutons a
l'interface native, sans appel de service de remplacement implicite.

Les unique_id des deux entites sont inchanges : `*_dernier_controle` et
`*_probleme`. Les entity_id existants restent au registre. `last_checked` signifie
maintenant dernier transfert agent. Les checksums et echecs consecutifs restent
exposes ; `avertissement_retention` distingue une purge incomplete d'un transfert
echoue. L'etat natif est stocke separement du dernier resultat de polling v0.4.0.
L'exemple `examples/dashboard.yaml` ouvre les sauvegardes natives et affiche ces
anomalies. Le premier resultat reste idle jusqu'au premier transfert.

Les anciens tar ne sont ni importes dans la liste native, ni supprimes par la
nouvelle retention. Les conserver pour restauration manuelle via HA et ne les
purger qu'apres validation operateur. La retention concerne les nouveaux backups
publies par cette entree ; des suppressions explicites dans HA restent possibles.

## Integrite, reprise et retention

Le namespace `bns-<sha256(entry_id)>-` isole les objets de cette entree. Les IDs
sont haches ; chaque tentative ecrit un tar UUID distinct. Le JSON par backup_id
contient les metadonnees HA, le nom tar et SHA-256 : seul ce marqueur rend une
copie visible. Aucun fichier existant n'est ecrase par une tentative concurrente
de cet agent (operations serialisees).

- Doublon identique : accepte apres reverification du contenu et de l'ancienne
  copie ; conflit meme ID / contenu ou metadonnees differents : refuse.
- Archive absente : BackupNotFound ; NAS inaccessible : erreur, jamais liste vide.
- Archive corrompue au download : erreur de checksum en fin de flux ; ne pas utiliser
  un telechargement interrompu avant sa fin comme preuve d'integrite.
- Metadonnees invalides : erreur explicite, retention bloquee par prudence.
- Upload interrompu : nettoyage best effort de l'objet non publie ; retry autorise.
- Publication JSON ambigue : conserver le tar verifie (ne pas risquer de detruire
  un backup effectivement publie). Retry accepte si JSON valide ; JSON corrompu
  impose inspection/reparation manuelle, aucun ecrasement automatique.
- Crash : objets sans sidecar ignores par la liste/retention. Apres arret des
  transferts, un operateur peut comparer les sidecars aux tar et supprimer seulement
  les orphelins prouves du namespace. Aucun nettoyage global automatique.
- Retention : dates natives, sauvegarde courante protegee meme si ancienne ; erreurs
  de suppression partielles signalees, transfert verifie reste OK. Une nouvelle
  demande d'upload verifiee reessaie la retention (pas de timer concurrent).

## Rollback et validation

Rollback : restaurer v0.4.0 et la configuration HA pre-migration, ou recreer une
entree v1 avec ses anciennes options. Ne pas retrograder une entree v2 en place.
Ne jamais effacer les archives natives lors du rollback ; conserver les sidecars
et l'entry_id pour une reprise v0.5. Sur HAOS le rollback ne corrige pas le defaut
historique d'acces au repertoire local.

Tests locaux : `python3 -m unittest discover -s tests/backup_nas_sync -v` depuis
le depot Factory. Ces mocks ne prouvent pas le chargement HA ni un vrai transfert.
Pour #185, SANDBOX est deploye directement par le script ad hoc sur decision
utilisateur. Avant DEV manuel : release beta HACS. Puis RECETTE et PROD manuelle.
Le test final HAOS/PROD exige un GO PO distinct. Voir issue Factory #185 et sa
specification `docs/ia/specs/185-backup-agent-natif.md`.
