# NR Backup NAS Sync

**NR Backup NAS Sync** ajoute un agent de destination dans le gestionnaire de
sauvegardes natif de Home Assistant. Il transfere les sauvegardes vers un NAS
Synology via FileStation et les rend disponibles dans l'interface standard de
Home Assistant.

Version publique : **0.5.0**. Requiert Home Assistant **2026.9.3** ou plus
recent et l'integration native **Synology DSM** configuree.

> Les pre-versions etaient destinees aux installations Home Assistant Core
> dans Docker. La version 0.5.0 utilise l'API native BackupAgent et apporte la
> compatibilite avec Home Assistant OS / Supervisor.

## Installation en production

1. Dans HACS, ajouter si necessaire le depot
   `https://github.com/NetRunner81FR/ha-backup-nas-sync` en type
   **Integration**.
2. Installer **NR Backup NAS Sync** version `0.5.0`, puis redemarrer Home
   Assistant.
3. Verifier que l'integration native **Synology DSM** est deja configuree avec
   un compte ayant les droits FileStation sur le dossier de sauvegarde.
4. Sur le NAS, creer un dossier FileStation dedie a Home Assistant, par
   exemple `/Backups/home-assistant`. Ne pas utiliser un chemin systeme tel que
   `/volume1/...` dans la configuration Home Assistant.
5. Dans **Parametres > Appareils et services > Ajouter une integration**,
   ajouter **NR Backup NAS Sync**. Choisir l'entree Synology DSM, renseigner un
   nom de site, le dossier FileStation dedie et le nombre de sauvegardes a
   conserver (minimum 1, valeur par defaut 5).
6. Dans **Parametres > Systeme > Sauvegardes**, ouvrir les destinations et
   selectionner explicitement **NR Backup NAS Sync**. L'integration ne change
   ni le calendrier, ni le chiffrement, ni les autres destinations : conservez
   une destination de secours adaptee a votre politique de sauvegarde.

Pour modifier le dossier ou la retention, utiliser **Reconfigurer** sur
l'entree existante. Ne pas supprimer puis recreer l'entree : son identifiant
associe les archives deja publiees.

## Ce que fait l'agent

1. Home Assistant fournit le flux de la sauvegarde a l'agent.
2. L'agent le prepare dans un fichier temporaire prive, puis l'envoie au NAS
   avec FileStation.
3. Il relit l'archive ecrite sur le NAS et compare sa taille et son SHA-256
   avec la source.
4. La sauvegarde n'apparait dans Home Assistant qu'apres cette verification.
5. La retention est appliquee uniquement aux archives de cette entree, sans
   supprimer la sauvegarde qui vient d'etre transferee.

Les entites de l'integration exposent le dernier transfert et les anomalies de
transfert ou de retention. La verification d'integrite est effectuee a chaque
upload ; elle ne remplace pas les essais periodiques de restauration.

## Mise a jour depuis v0.4.x

Avant la mise a jour, realiser une sauvegarde de la configuration Home
Assistant. La migration conserve la connexion DSM, le site, le dossier cible
et la retention. Les anciens reglages de scan local sont retires :
`local_backup_dir`, `poll_interval` et `stable_seconds`.

A partir de v0.5.0, les nouvelles sauvegardes passent exclusivement par le
flux natif Home Assistant. Les anciennes archives ne sont ni importees dans la
liste native ni supprimees automatiquement. Conservez-les jusqu'a avoir valide
votre procedure de restauration.

Le service `backup_nas_sync.sync_now` n'est plus utilise : declenchez les
sauvegardes depuis l'interface native de Home Assistant.

## Exploitation et diagnostic

- Une archive absente ou un NAS indisponible produit une erreur explicite ; une
  liste vide n'est jamais retournee comme si tout etait sain.
- Les fichiers incomplets ou les metadonnees invalides restent invisibles pour
  la liste et ne sont pas supprimes automatiquement.
- En cas d'echec de retention, le transfert verifie reste trace et une anomalie
  est exposee pour intervention operateur.
- Pour restaurer, utiliser le parcours de restauration Home Assistant et
  verifier que l'archive est entierement telechargee avant de la considerer
  integre.

## Retour arriere

Pour revenir a v0.4.x, restaurer egalement la configuration Home Assistant
anterieure ou creer une nouvelle entree compatible v0.4.x. Ne pas retrograder
une entree v0.5.0 en place et ne pas effacer les archives natives pendant cette
operation.
