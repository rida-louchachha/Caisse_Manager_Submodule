# testSocial Inbox - Plan de test UAT (WhatsApp, Instagram, Messenger)

## Objectif
Valider que l'equipe sales peut:
- recevoir les messages clients dans Odoo,
- repondre depuis Odoo,
- suivre l'historique par conversation.

---

## 1) Perimetre MVP

- Canaux: WhatsApp, Instagram DM, Facebook Messenger
- Fonctions:
  - reception messages entrants
  - affichage conversation unifiee
  - reponse depuis Odoo
  - statut de message de base (sent/failed/received)

---

## 2) Pre-conditions avant test

- Module installe et a jour.
- Credentials saisis dans Odoo (`Social Inbox` -> `Channels`).
- Verify tokens configures dans parametres systeme.
- Webhooks Meta actifs sur les bonnes URLs.
- Minimum 1 numero/compte client de test par canal.

---

## 3) Jeux de test (cas UAT)

## Cas 1 - Reception WhatsApp
- Action: un client envoie "Test WA 01" vers le numero business.
- Attendu:
  - message visible dans `Social Inbox`
  - conversation correcte (bon contact/numero)
  - statut entrant `received`
- Resultat: [PASS/FAIL]

## Cas 2 - Reponse WhatsApp depuis Odoo
- Action: agent sales repond "Bonjour, message recu WA".
- Attendu:
  - message sortant enregistre
  - client recoit la reponse
  - si hors fenetre 24h: message d'erreur/metier coherent (template requis)
- Resultat: [PASS/FAIL]

## Cas 3 - Reception Instagram DM
- Action: client envoie "Test IG 01" en DM.
- Attendu:
  - message visible dans inbox
  - conversation liee au bon partner/external_user_id
- Resultat: [PASS/FAIL]

## Cas 4 - Reponse Instagram depuis Odoo
- Action: agent repond "Bonjour depuis Odoo IG".
- Attendu:
  - client recoit le DM
  - log sortant cree avec statut coherent
- Resultat: [PASS/FAIL]

## Cas 5 - Reception Messenger
- Action: client envoie "Test FB 01" sur Messenger page.
- Attendu:
  - message visible dans inbox
  - conversation messenger creee/retrouvee
- Resultat: [PASS/FAIL]

## Cas 6 - Reponse Messenger depuis Odoo
- Action: agent repond "Bonjour depuis Odoo FB".
- Attendu:
  - client recoit la reponse
  - log sortant present
- Resultat: [PASS/FAIL]

## Cas 7 - Creation nouveau chat (WhatsApp)
- Action: bouton nouveau chat + numero client.
- Attendu:
  - conversation creee si inexistante
  - aucune erreur RPC
- Resultat: [PASS/FAIL]

## Cas 8 - Lecture et suivi conversation
- Action: ouvrir conversation et marquer lu.
- Attendu:
  - compteur unread se met a jour
  - historique reste coherent
- Resultat: [PASS/FAIL]

---

## 4) Criteres de validation Go/No-Go

GO si:
- 100% des cas reception/reponse des 3 canaux sont PASS
- aucune erreur bloquante RPC lors usage normal
- equipe sales valide l'ergonomie de base

NO-GO si:
- un canal principal ne recoit pas ou ne repond pas
- erreurs recurrentes en production path

---

## 5) Defects log (a remplir pendant UAT)

- ID:
- Date:
- Canal:
- Scenario:
- Erreur observee:
- Capture/log:
- Severite: [High/Medium/Low]
- Statut: [Open/In progress/Closed]

---

## 6) Checklist de livraison finale

- Guide credentials partage au manager
- Procédure exploitation partagee a l'equipe sales
- Resultats UAT archives
- Scope confirme:
  - inclus: messagerie omnicanale
  - hors scope immediate: appels natifs WhatsApp/Instagram

