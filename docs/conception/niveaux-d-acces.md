# Niveaux d'accès d'un connecteur

- **Statut** : validé par le mainteneur le 14/10/2026
- **Dernière révision** : 2026-10-14

## Résumé

Un connecteur à consentement OAuth peut déclarer des niveaux d'accès nommés, au moins `read` et `full`, chacun avec la liste des droits (scopes) que le consentement demande. Chaque fonction déclare les droits qu'elle exige. L'hôte choisit un niveau par organisation ou par équipe, `full` par défaut. Une fonction dont les droits ne sont pas couverts par le niveau n'est ni servie ni appelable, et le consentement ne demande que les droits du niveau. `full` ne filtre rien : c'est le comportement d'un connecteur sans niveaux.

## Contexte

Un consentement OAuth demande une liste de droits fixée par le connecteur. Une organisation qui veut ouvrir un outil tiers en lecture seule, le temps d'un essai, n'avait que deux choix : tout accorder, ou ne pas brancher le connecteur. Le marquage `class` d'une fonction (`read`, `write`, `sensitive`, voir [Format de description](format-de-description.md)) dit ce que fait une fonction, pas ce qu'elle exige : deux lectures peuvent demander des droits différents, et un niveau « lecture » qui n'accorde qu'une partie des lectures laisserait servir des fonctions vouées à l'échec.

## Objectifs et non-objectifs

Objectifs :
- un niveau restreint se déclare dans la description du connecteur, sans code ;
- une fonction non couverte disparaît de ce que voit l'agent et se refuse à l'appel, avec un refus nommé ;
- le consentement ne demande que les droits du niveau ;
- un connecteur sans niveaux ne change pas.

Non-objectifs :
- des droits par personne : le niveau se règle par organisation ou par équipe ;
- vérifier, à chaque appel, les droits réellement accordés par le fournisseur : le niveau est une politique de l'hôte, appliquée même à un jeton plus large ;
- les connecteurs sans consentement OAuth (clé d'API) : leurs droits se fixent chez le fournisseur, à la création de la clé.

## Conception

Dans `connector.auth`, en `oauth2_user`, `access_levels` remplace `scopes` :

```yaml
auth:
  kind: oauth2_user
  access_levels:
    read: { scopes: [Records.READ, Settings.READ] }
    full: { scopes: [Records.ALL, Settings.READ, Users.READ] }
  scope_implies:
    Records.ALL: [Records.READ, Records.CREATE, Records.UPDATE, Records.DELETE]
```

- `access_levels` porte au moins `full`. Un autre nom (`read`, `support`…) est un niveau restreint. `scopes` et `access_levels` s'excluent : un connecteur sans niveaux garde `scopes`, et c'est son niveau `full`.
- `scope_implies` dit qu'un droit en couvre d'autres. C'est une donnée, propre au fournisseur, jamais une règle devinée : un droit « tout » ne couvre un droit « lecture » que si le fichier le dit.
- Chaque fonction d'un connecteur à niveaux déclare `scopes`, les droits qu'elle exige. Elle est servie dans un niveau si chacun de ses droits figure parmi ceux du niveau ou de ce qu'ils impliquent. `class` reste : il dit ce que fait la fonction, et se lit à côté.

Côté hôte :
- le niveau se règle par organisation, puis par équipe. Une équipe peut restreindre le niveau de son organisation, jamais l'élargir ;
- au niveau `full`, rien n'est filtré ;
- une fonction non couverte est retirée de ce que voit l'agent. Quand un outil regroupe plusieurs fonctions sous un paramètre d'opération, les opérations non couvertes sortent de son schéma. Un appel direct est refusé avec `access_level_denied`, qui nomme le niveau et l'opération ;
- le consentement demande les droits du niveau en vigueur au départ, signe ce niveau dans l'état du flux et le rejoue au retour. Les droits que le fournisseur dit avoir accordés sont gardés avec le compte ;
- passer d'un niveau restreint à `full` demande un nouveau consentement : un jeton obtenu pour `read` n'a pas les droits d'écriture.

## Décisions et alternatives écartées

- **Les droits exigés, plutôt que la classe.** Un niveau « lecture » défini par `class: read` servirait toutes les lectures, y compris celles dont le droit n'est pas accordé. Les droits exigés ne servent que ce qui marchera.
- **`full` ne filtre rien.** `full` reproduit l'état d'avant, à l'octet près, pour tous les connecteurs existants. La déclaration des droits d'une fonction ne peut donc rien casser tant qu'aucune organisation ne choisit un niveau restreint.
- **L'implication déclarée.** Une règle générique (« `ALL` couvre `READ` ») varie d'un fournisseur à l'autre et se trompe en silence. Écartée.
- **Un outil par niveau** (un outil de lecture, un outil d'écriture). Il double la surface servie pour un réglage que la plupart des organisations ne touchent pas. Écarté au profit du filtrage des opérations.
- **Le niveau porté par le jeton seul.** Lire les droits accordés à chaque appel suffirait pour un nouveau consentement, mais laisserait écrire un jeton obtenu avant le réglage. Écarté : le niveau est une politique, le jeton n'en est qu'une conséquence.

## Sécurité et confidentialité

Le niveau borne ce que l'hôte laisse faire, indépendamment du jeton : un ancien jeton aux droits complets ne peut pas écrire sous un niveau restreint. Le consentement d'un niveau restreint ne demande que ses droits : le fournisseur n'en accorde pas plus. L'état signé du flux porte le niveau : il ne peut pas être élargi entre le départ et le retour.

## Écart avec le code

- Le schéma de description et sa validation ne portent pas encore `access_levels`, `scope_implies` ni le `scopes` d'une fonction. Aucun connecteur décrit ne déclare de niveaux.
- Premier usage : un CRM et un centre d'aide dont les outils sont écrits à la main chez l'hôte d'oto 1, qui déclare leurs niveaux dans le même vocabulaire, en Python.

## Questions ouvertes

- Un niveau restreint par défaut, posé par le connecteur plutôt que par l'organisation ?
- Faut-il refuser, au départ du consentement, un niveau dont les droits ne couvrent aucune fonction ?

## Historique

- 2026-10-14 : création — niveaux d'accès, droits exigés par fonction, implication déclarée, réglage par organisation et par équipe — décidé par le mainteneur (source : besoin d'un essai en lecture seule).
