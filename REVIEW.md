# Code és usability review

Ellenőrzés dátuma: 2026-10-08. A feltárt, alább felsorolt hibák javítva.

| Súlyosság | Megállapítás | Javítás |
| --- | --- | --- |
| Magas | A sikertelen küldetés négy másodperc után törölte a munkamenetet, túl kevés időt hagyva az exportra. | A lezárt küldetés naplója és jegyzetei megmaradnak kifejezett lezárásig vagy lejáratig. |
| Magas | Az IP-nkénti keret nem korlátozta sok különböző IP összesített AI-fogyasztását. | Tartós, közös napi tokenkeret; az IP-kerettel együtt atomikus foglalás és az eredeti napra történő elszámolás éjfél után is. |
| Magas | Másik böngészőfül továbblépése után a régi fül rossz állomásra alkalmazhatott műveletet vagy jegyzetet. | A böngésző az aktuális állomás számát küldi; eltéréskor a szerver módosítás nélkül 409-et ad. |
| Közepes | Export előtt kimaradhatott a még nem mentett jegyzet. | Export előtt a jegyzet mentése megtörténik; mentési hiba esetén nincs félrevezető export. |
| Közepes | Mentés alatt szerkesztett jegyzetet tévesen mentettnek jelölt a felület. | A visszaigazolt pillanatképet összehasonlítja az aktuális szöveggel. A későbbi szerkesztés mentetlen marad; elnavigálás előtt a böngésző figyelmeztet. |
| Közepes | AI-válaszra várva begépelt következő üzenetet törölhette a felület. | Csak a beküldött, azóta változatlan szöveget üríti. |
| Közepes | Hibás Unicode, túl hosszú JSON-szám és néhány hibás válasz szerverhibát vagy félrevezető klienshibát okozhatott. | Biztonságos JSON-hibaválasz; megmaradó HTTP-státusz és érthető hálózati helyreállítási útmutató. |
| Közepes | Csonkolt modellválasz érvényesnek tűnő JSON-nal is továbbjuthatott. | A length/content_filter lezárási okok elutasítva, automatikus újrahívás és promptfogyasztás nélkül. |
| Közepes | Zárra váró kérés a munkamenet lejárata után is végrehajtódhatott. | A lejárat újbóli ellenőrzése a zár megszerzésekor. |
| Közepes | A modellbemeneti túllépés szolgáltatói hibának látszott; a Unicode felesleges escape-karakterekké bővült. | 413-as, rövidítésre kérő válasz a hívás előtt; UTF-8 szöveg közvetlenül az értékelő bemenetben. |
| Közepes | Nem volt egyértelmű várakozási állapot, a sikertelen inicializálás után hiányzott a helyreállítás, a kvóta elavulhatott. | Látható várakozás és aria-busy; inicializáláskor letiltott indítás, Reconnect, elutasítás/lejárat után frissített indítási keret. |
| Közepes | Segítségkérés promptköltsége, a közös IP-kvóta és a küldetés lezárásának következménye nem volt elég világos. | Pontosabb szövegek, kevés hátralévő prompt kiemelése és kvótát mutató lezárási párbeszédablak. |
| Közepes | Egy hint lekérése újraépítette és újra felolvastathatta a teljes beszélgetést. | Változatlan beszélgetésnél nincs DOM-csere; új üzenetek hozzáfűzése, javított fókuszkezelés. |
| Alacsony | 320 pixelen összenyomott műveleti linkek, kicsi kattintási célok, elvesző workshop-visszajelzés és téves „ten” felirat. | Mobilon külön műveleti sor, legalább 32 px magas célok, workshop-eredmény visszaállítása, fifteen felirat és duplikált CSS eltávolítása. |

## Ellenőrzések

- 55 tesztes teljes backendcsomag sikeres; a végső Unicode/bemeneti módosítás után a 11 review-teszt is sikeres, benne 2 további új eset. Összesen 57 különböző backendteszt.
- 20 sikeres böngészőteszt: asztali és mobil, teljes 15 állomásos küldetés, dekódolás, export, folytatás, hint, gyakorlólabor, kvóta, mentési versenyhelyzet, üzenetvázlat és reconnect.
- 6 sikeres JavaScript-teszt.
- Axe ellenőrzések a tesztelt landing/mission/labor/guide nézeteken: nincs jelzett szabálysértés.
- Külön vizuális és geometriai ellenőrzés 320, 768 és 1440 px szélességen: nincs oldalszintű vízszintes túllógás vagy JavaScript-hiba.
- Ruff és Prettier ellenőrzések sikeresek.

## Konfiguráció és ellenőrzési határok

A napi AI-keret alapértelmezése PROVIDER_DAILY_TOKEN_LIMIT=30000000, UTC napokra. Ez a tokenkeret frissül naponta; a három küldetésindítás/IP szabály továbbra is összesített, és nem nullázódik naponta. Az API-kulcs és a .env tartalma nem került a kliensbe vagy a jelentésbe.

A Groq hálózati elérése ebben a környezetben korlátozott. A szemantikus értékelés bekötése és ellenőrzése tesztelt, de a valódi modell nyelvi pontossága és tényleges késleltetése nem mérhető itt. A játékállapot a dokumentált módon egy folyamat memóriájában él, hat óra után lejár, és szerver-újraindításkor elveszik; a kvóta és tokenelszámolás tartós.

## A húsz kihívásos változat ellenőrzése — 2026-10-09

- Öt új, eltérő bemeneti forrást és munkafolyamatot vizsgáló kihívás; a Command Core a huszadik finálé.
- A bemeneti állomáskorlát a kihívások számából származik; a 20. állomás műveletei és a hibás indexek külön tesztelve.
- 77 sikeres backendteszt, 22 sikeres asztali/mobil böngészőteszt és 6 sikeres JavaScript-teszt.
- Teljes húszállomásos végigjátszás, 200 pontos maximum, PDF napló és egyoldalas tanúsítvány ellenőrizve.
- Új orbitális grafika és kezelőfelület: külön vizuális/geometriai ellenőrzés 320, 768 és 1440 px szélességen; nincs oldalszintű túllógás vagy JavaScript-hiba.
- A tesztelt kezdő-, játék-, labor- és súgónézetek axe ellenőrzése sikeres. A szolgáltató neve nem szerepel a webes felületen.
- A publikálási lista és a teljes Git-index ellenőrzése nem talált helyi titkot vagy privát fájlt.
