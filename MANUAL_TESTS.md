# Validare necesară pe Windows + Packet Tracer

Nu există rezultate native confirmate încă. Rulează întâi pe un proiect de probă. Notează versiunea Windows, versiunea PT, scalarea DPI și rezultatul fiecărui pas.

| Test | Rezultat așteptat |
|---|---|
| Deschide Packet Tracer și actualizează lista | Doar ferestrele procesului PacketTracer apar |
| Generează cod și conectează browserul | Nicio imagine și niciun input înainte de accept |
| Refuză conectarea | Ambele conexiuni se închid, codul se invalidează |
| Acceptă conectarea | Imaginea ferestrei apare în browser |
| Ține mouse-ul gazdei într-un colț, click remote | Cursorul local nu se deplasează; PT reacționează |
| Adaugă router și switch | Elementele apar; verifică separat click și drag |
| Trasează un cablu | Alegerea porturilor funcționează |
| Dublu-click pe router | Dialogul se deschide local |
| Aprobă fereastra routerului din gazdă | Fereastra apare în selectorul remote |
| CLI: enable, configure terminal, hostname TEST | Comenzile și Enter sunt interpretate corect |
| Backspace, Tab, săgeți, scroll | Reacție corectă în controlul selectat |
| Redimensionează și testează DPI 125% / 150% | Clickurile rămân aliniate imaginii |
| Acoperă PT cu altă aplicație | Nu se transmite cealaltă aplicație; documentează dacă PT mai randează |
| Minimizează fereastra | Captura se oprește / mesaj de limitare; fără fallback desktop |
| Elimină o fereastră din selecția partajată | Fereastra nu mai poate primi input sau captură |
| Oprește sesiunea în timpul unui drag | Acces revocat și buton eliberat când ținta este încă disponibilă |
| Închide browserul, PT sau întrerupe rețeaua | Sesiunea se închide; codul vechi nu permite reconectare |
| Mac participant către Windows prin HTTPS | Aceleași operații de bază; măsoară latența |

Dacă captura este neagră sau clickurile sunt ignorate, salvează mesajul din PacketBridge și versiunea PT. Nu activa un fallback care controlează întreg desktopul. Pentru compatibilitate completă poate fi nevoie de alt mecanism sau de o instanță PT izolată într-o mașină virtuală.
