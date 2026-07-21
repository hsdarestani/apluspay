# Apple-Anmeldung für A+Pay

Die Apple-Anmeldung ist ausschließlich für Kundenkonten vorgesehen. Betreiber-, Leitungs-, Mitarbeiter- und Plattformkonten melden sich weiterhin mit Benutzername und Passwort an.

## Einstellungen im Apple-Entwicklerkonto

1. Für die Webanmeldung eine **Services ID** anlegen.
2. Die Domain `pay.smarbiz.sbs` als Webdomain registrieren.
3. Folgende Rücksprungadresse exakt eintragen:

   `https://pay.smarbiz.sbs/accounts/apple/callback/`

4. Einen Schlüssel mit aktivierter Funktion „Sign in with Apple“ erstellen und die zugehörige `.p8`-Datei sicher speichern.

## Erforderliche GitHub-Geheimnisse

Im Repository unter den GitHub-Actions-Geheimnissen folgende Werte hinterlegen:

- `APPLE_CLIENT_ID`: die Services ID
- `APPLE_TEAM_ID`: die Apple-Teamkennung
- `APPLE_KEY_ID`: die Kennung des erstellten Schlüssels
- `APPLE_PRIVATE_KEY_BASE64`: der vollständige Inhalt der `.p8`-Datei als Base64-Zeichenfolge

Beispiel zur Umwandlung der Schlüsseldatei unter Linux:

```bash
base64 -w 0 AuthKey_ABC123DEFG.p8
```

Unter macOS:

```bash
base64 < AuthKey_ABC123DEFG.p8 | tr -d '\n'
```

Nach dem Speichern der vier Geheimnisse reicht eine erneute Produktionsbereitstellung. Der private Schlüssel wird niemals im Repository gespeichert. A+Pay erzeugt den kurzlebigen Apple-Client-Schlüssel bei jeder Anmeldung dynamisch.

## Datenschutz und Kontenverknüpfung

- A+Pay akzeptiert nur von Apple bestätigte E-Mail-Adressen.
- „E-Mail-Adresse verbergen“ wird unterstützt; dabei verwendet A+Pay die private Apple-Relay-Adresse.
- Ein bestehendes reines Kundenkonto wird anhand derselben bestätigten E-Mail-Adresse verbunden.
- Betreiber- oder Mitarbeiterkonten werden niemals automatisch über Apple verbunden.
- Status und Einmalwert schützen vor manipulierten oder wiederholten Rückrufen.
