# PacketBridge 0.1 — prototip experimental

Colaborare autorizată în Cisco Packet Tracer: gazda selectează ferestrele, oferă un cod temporar și acceptă participantul. Participantul vede ferestrele aprobate într-un browser și trimite clickuri/taste. Nu se desenează un cursor remote peste ecranul gazdei și adaptorul nu folosește `SetCursorPos` sau `SendInput`.

**Stare reală:** codul și testele de protocol sunt implementate. Integrarea cu Packet Tracer pe Windows NU a fost verificată pe un sistem Windows. Nu există încă un server public activ, un GitHub Release sau executabile compilate. Nu este un înlocuitor complet verificat pentru AnyDesk.

| Funcție | v0.1 |
|---|---|
| Gazdă Windows | Adaptor experimental, necesită test real |
| Participant Windows / macOS | Client în browser; launcher desktop comun |
| Gazdă macOS | Neimplementată |
| Cod temporar + acceptul gazdei | Implementate; teste automate |
| Mai multe ferestre / terminale | Gazda aprobă explicit fiecare fereastră |
| Click, clic dreapta, dublu-click, drag, scroll | Implementate prin mesaje Win32, compatibilitate PT nevalidată |
| Text CLI + taste de navigare | Implementate; fără Ctrl/Cmd/Alt în această versiune |
| Fereastră minimizată | Nu este suportată |
| Captură fără desktop în fundal | Solicitare de randare adresată ferestrei; poate fi neagră/incompletă |
| Pachete Windows și Mac | Workflow de build inclus, încă nerulat |

## Pornire locală din surse

Instalează Python 3.12. Pe Windows folosește instalatorul oficial cu Tcl/Tk. Dezarhivează proiectul și deschide terminalul în folderul care conține acest README.

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python -m packetbridge.relay
```

Lasă terminalul serverului deschis. În al doilea terminal:

```powershell
.venv\Scripts\python launch.py
```

1. Deschide Cisco Packet Tracer, fără „Run as administrator”.
2. În PacketBridge apasă **Actualizează ferestrele** și selectează fereastra principală.
3. Lasă adresa `http://127.0.0.1:8765` pentru test pe același PC.
4. Apasă **Generează cod**. Copiază codul din interfață.
5. Deschide `http://127.0.0.1:8765` în browser și introdu codul.
6. Acceptă cererea în interfața gazdei. Codul expiră după 10 minute, cererea după 60 de secunde.
7. Alege fereastra și dă click pe imagine. Folosește caseta de text pentru comenzi CLI mai lungi; **Enter** este separat.
8. Dacă deschizi un router/terminal într-o fereastră nouă, în interfața gazdei actualizează lista, selectează toate ferestrele dorite cu Ctrl+click și apasă **Partajează selecția**. Selecția înlocuiește lista aprobată.
9. **Oprește sesiunea** sau închiderea aplicației revocă accesul. Reconectarea necesită un cod nou.

Pe macOS, pentru launcherul participantului din surse:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python launch.py
```

Launcherul Mac deschide browserul; nu este un motor de control macOS. Participantul poate folosi direct browserul, fără Python sau launcher.

## Conectarea colegului prin internet

`127.0.0.1` înseamnă calculatorul propriu: colegul NU poate folosi acea adresă pentru a ajunge la serverul tău. Este necesar un relay HTTPS accesibil ambilor. Nu este inclus un serviciu găzduit.

Pe un server Linux cu Docker Compose și un domeniu propriu:

1. Direcționează în DNS domeniul ales spre server și permite porturile TCP 80/443.
2. În `deploy/.env` scrie `DOMAIN=remote.domeniul-tau.ro` folosind domeniul real.
3. Rulează din folderul `deploy`: `docker compose up -d --build`.
4. Caddy obține certificatul TLS. Verifică `https://remote.domeniul-tau.ro/healthz`.
5. Gazda introduce `https://remote.domeniul-tau.ro` în PacketBridge; colegul deschide aceeași adresă în browser pe Mac/Windows.

Ambele calculatoare inițiază conexiuni către relay; nu se deschid porturi la calculatoarele participanților. HTTPS este obligatoriu în afara loopback. Relay-ul este un singur proces cu sesiuni în memorie; repornirea lui închide sesiunile. TLS protejează fiecare legătură, **nu există criptare end-to-end față de administratorul relay-ului**. Nu folosi un relay necunoscut pentru date private.

## Compilare și GitHub Releases

Pe Windows sau macOS, după instalarea dependențelor:

```bash
python -m pip install pyinstaller==6.16.0
python -m PyInstaller --noconfirm --clean --windowed --onedir --name PacketBridge launch.py
```

Pe Windows rezultatul este `dist/PacketBridge/PacketBridge.exe` împreună cu întregul folder. Pe Mac rezultatul este `dist/PacketBridge.app`. Compilarea trebuie făcută pe platforma țintă. Pachetele sunt nesemnate; nu dezactiva antivirusul sau protecțiile sistemului pentru a le rula. Distribuția publică necesită semnare și, pe Mac, notarizare.

Workflow-ul `.github/workflows/build.yml`:

- verifică testele pe Linux și pe sistemele de build;
- generează Windows x64, macOS ARM64 și macOS x64;
- păstrează arhivele în Actions → Artifacts;
- la un tag `v*`, publică un **prerelease** cu arhivele.

Pentru un repository dedicat nou, pune conținutul acestui folder în rădăcina repository-ului. Nu urca `.venv`, `dist` sau fișiere cu secrete. După primul build reușit, creează un tag, de exemplu `v0.1.0`. Workflow-ul de Release nu a fost încă executat și runner-ele/dependențele pot necesita ajustări la prima rulare.

## Limitări importante și testarea pe PC

Nu este suficient să nu miști cursorul pentru a obține control complet independent. Qt/Packet Tracer poate ignora mesajele sintetice, poate folosi focusul global sau poate modifica însuși cursorul. Codul nu mută cursorul global, dar nu poate garanta comportamentul intern al aplicației. Terminalele, meniurile, combinațiile de taste, ferestrele modale și drag-and-drop trebuie validate individual.

Captura folosește `WM_PRINT` adresat ferestrei, cu timeout de 500 ms, pentru a nu bloca fără limită interfața. Nu face fallback la capturarea întregului desktop. GPU-ul sau felul în care PT își desenează widgeturile pot produce cadre negre sau parțiale; aplicația afișează eroare pentru cadre uniforme. O fereastră acoperită poate funcționa, dar nu este garantat. Nu minimiza ferestrele partajate.

**Restricția la ferestre nu este un sandbox de fișiere.** Sunt validate procesul PacketTracer, identitatea lui și ferestrele aprobate, dar Packet Tracer poate deschide/salva fișiere sau afișa dialoguri Qt în interiorul unei ferestre deja aprobate. Filtrarea dialogurilor Open/Save nu este implementată. Nu există transfer de fișiere, clipboard comun, shell remote sau captură a altor aplicații în protocol; totuși, aprobă doar un participant în care ai încredere. Pentru izolare strictă folosește un cont de laborator sau o mașină virtuală cu proiectele necesare.

Nu sunt instalate servicii ascunse, persistență sau pornire automată. Starea conexiunii și oprirea sunt în fereastra PacketBridge. Nu se suprapune niciun panou peste Packet Tracer. Modificările, dialogurile și topologia rămân vizibile local.

Lista manuală de acceptanță este în `MANUAL_TESTS.md`. Dacă funcția de bază nu trece, nu trata build-ul ca funcțional doar fiindcă testele de rețea trec.

## Teste și arhitectură

```bash
python -m unittest discover -s tests -v
```

- `relay.py`: coduri aleatorii de 10 caractere, TTL, aprobare corelată cu cererea, un participant, expirare, limitare încercări, revocare la deconectare.
- `agent.py`: conexiune outbound, trimiterea cadrelor doar după aprobare, un cadru în așteptarea confirmării clientului.
- `windows.py`: listă explicită de HWND-uri aprobate, verificare PID/timp de creare proces, captură limitată la clientul ferestrei, input prin mesaje.
- `desktop.py`: interfața Tk a gazdei și launcherul participantului.
- `web/`: client fără dependențe frontend, coordonate normalizate și confirmarea cadrelor.

Transportul este WebSocket cu JPEG la maximum aproximativ 6 cadre/s; nu WebRTC. Relay-ul vede imaginile în memorie, nu le scrie pe disc. Limita de 20 conexiuni/minut este per IP TCP văzut de proces; în spatele proxy-ului Caddy inclus devine practic comună clienților acelui proxy. Pentru utilizare mai largă trebuie implementată limitare corectă la proxy, monitorizare și configurare operațională.

Referințe tehnice: [WM_PRINT](https://learn.microsoft.com/en-us/windows/win32/gdi/wm-print), [PrintWindow](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-printwindow), [mesaje de mouse](https://learn.microsoft.com/en-us/windows/win32/learnwin32/mouse-movement), [websockets](https://websockets.readthedocs.io/en/stable/reference/asyncio/server.html).
