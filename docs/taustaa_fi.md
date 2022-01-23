# Powerguru - energian kulutuksen ja varastoinnin ohjausjärjestelmä

**Sähköturvallisuudesta
Vain valtuutettu sähköalan ammattilainen saa tehdä verkkovirtaan kytkettyjen laitteiden , kuten myöhemmin mainittujen energiamittareiden ja varaajien ohjaamiseen käytettyjen verkkovirtareleiden asennutöitä. Hän on myös vastuussa asennustöiden verkkovirtalaitteiden asennusten turvallisuudesta. JÄTÄ VERKKOVIRTALAITTEIDEN VALINNAT JA KYTKENNÄT AINA AMMATTILAISELLE!**

## Yleistä
Powerguru  energian kulutuksen ja varastoinnin ohjausjärjestelmä on tarkoitettu optimoimaan kiinteistön (aurinkovoimalan) sähköntuotannon käyttöä sekä sähkön hankintaa edullisimmille tunneille. Automaattisen ohjauksen mahdollistamiseksi kiinteistössä on oltava yksi tai useampi energiavarasto, johon energiaa voidaan varastoida myöhempää käyttöä varten. Tyypillisesti energiaa voidaa varastoida lämpönä esim. vesivaraajiin tai rakenteisiin lattialämmityksen avulla tai sähköauton akkuun tai kiinteään kotiakkuun. 

Ohjelmiston ensimmäinen versio on ollut käytössä vuoden 2020 kesästä alkaen ohjaamassa eteläsuomalaisen maatilan 30 kWp aurinkovoimalan tuotannon käyttöä. Tämän version kehitetty versio 2 otetaan testikäyttöön kevättalvella 2022. Ohjelmiston lähdekoodi ja perusohjeistus on vapaasti saatavilla [Githubissa](https://powerguru.eu). Ohjelmisto toimii Raspberry Pi tietokoneella, johon kytketään tarvittavat lisälaitteet tietojen lukemiseksi ja laitteiden ohjaamiseksi

## Ominaisuudet
Ohjelmiston tärkeimmät ominaisuudet lyhyesti
- Oman (aurinkovoimalan) tuotannon fiksu ohjaus ensisijaisesti omaan käyttöön tai myyntiin kalliin energian aikana.
- Sähkön oston ajoittaminen edullisimmille tunneille erityisesti, jos käytössä on pörssisähkö (tai yösähkö).
- Tuntitinetotuksen ja vuonna 2023 käyttöönotettavan varttinetotuksen hyödyntäminen.
- Korkeimpien kulutuspiikkien välttäminen  liittymän (sulake)koon optimoimiseksi ja mahdollisten siirron tehomaksujen pienentämiseksi. 

### Oman käytön maksimointi ja myynnin ajoitus
Kun omaan tuotantoa ei ole saatavissa (kun aurinko ei paista) voidaan energian ostoa kohdistaa edullisimmille tunneille. Tämä riippuu valitusta sähköenergian ostosopimuksesta (pörssisähkö, kiinteä, yö/päivä jne) sekä verkkopalvelusopimuksen tyypistä. Sähkön ollessa edullisinta se on yleisesti myös puhtaimmin tuotettua, joten edullisiin tunteihin ostojen painottaminen on myös ekoteko. 

Itse tuotetun sähkön oma käyttö maksimoidaan (aurinkopaneeleilla)  varaamalla lämpöä vesivaarajiin tai rakenteisiin (lattialämmitys) ja vähennetään näin ostoenergian tarvetta. Ostoenergiasta joutuu maksamaan aina verkkoyhtiölle verkkopalvelumaksun (siirtomaksu), joten oman käytön maksimointi on yleensä hyvin kannattavaa. Mikäli sähkön hintapiikki osuus aurinkoiselle tunnille on Powergurun avulla mahdollista omaa kulutusta (esim. varaajaan)  tällöin rajoittaa ja myydä mahdollisimman paljon verkkoon. Tämä voi olla kannattavaa mikäli "korvaava" sähkö on myöhemmin saatavissa omista aurinkopaneeleista tai ostettavissa selkeästi halvemmalla (verkkopalvelumaksu huomioiden).

### Ostettavan energian kulutuksen ohjaus
Pörssisähköä käytettäessä järjestelmänn sääntöjen avulla voidaan ohjata kulutusta edullisimmille tunneilla. Kellonaikaan tai kalenteriin sidotulla sopimuksella sähköä ostavien on mahdollista määritellä ohjeusehdot vastaavasti. Ehdoissa voidaan määritellä esim. tavoitetason varaajan lämpötilalle tai varaaja voidaan pitää päällä vain edullisimman sähkön aikana, jolloin se on toimii optimoidummin kuin pelkästään ajastimella käynnistettävä varaaja.

### Tuntinetotuksen hyödyntöminen 
Powerguru tukee sähköverkon tuntinetotusta ja  myöhemmin käyttöönotettavaa 15-minuutin netotusta. Käytännössä tämä tarkoittaa sitä, että kun on omaa tuotantoa (aurinko paistaa) niin osto ja myynti pyritään tasapainottomaan kyseisen ajan (60 tai 15 minuuttia)  sisällä esim. varaajia ohjaamalla. Esimerkiksi jos aurinkovoimala tuottaa tunnin aikana tasaisen 2kW:n "ylimääräisen" tehon (joka menisi muuten myyntiin), niin Powerguru kytkee 6 kW-tehoisen varaajan päälle tunnin aikana yhteensä 20 minuutiksi. Tällöin kyseisen tunnin ajalla laskennallisesti sähkön osto ja myynti ovat tasapainossa, eikä ostosta (eikä siirrosta) laskuteta eikä myynnistä makseta, vaikka tunnin aikana sähköä onkin kulkenut verkosta/verkkoon. Lisätieto tuntinetotuksesta https://yle.fi/uutiset/3-11767604 

Powerguru osaa optimoida sähkön käytön myös niiden sähköyhtiöiden alueella, jotka eivät vielä ole ottaneet tunti- tai vaihenetotusta käyttöön, mikäli esim. varaajan ohjaus toteutetaan vaihekohtaisesti. Koska vaihenetotus ja tuntinetotus ovat tulossa käyttöön kaikissa verkkoyhtiössä viimeistään 1.1.2023, ei varaajien ohjausta kannata enää uusissa asennuksissa netotuksen puuttumisen takia kannata toteuttaa vaihekohtaisesti.

### Energiasääennuste
Powerguru osaa hyödyntää paikkakunnalle laadittua energiasääennustetta. Esimerkiksi jos ennusteessa on luvattu tulevalle päivällä korkeaa aurinkovoimalan tuottoa voidaan varaajien tai lattialämmityksen lämmitystä siirtää päivään lämmittämällä yöllä minimitasolle ja mahdollistamalla näin itsetuotetulle sähkölle käyttökohde päivällä. Mikäli tulossa onkin pimeä päivä (vähän omaa tuotantoa), niin lämmitys kannattaa tehdä halvemmalla yösähköllä tai tyypillisesti halvemmila spot-hinnoilla.

Laitteiden ohjauksessa voidaan huomioida kulloinenkin sähkön kulutus jopa eri vaiheiden osalta. Samalla järjestelmä voi auttaa pienentämään suurinta käytettyä ostotehoa (vaikuttaa joissakin verkkoyhtiöissä verkkopalvelumaksuun).
Esimerkki kulutusrajoituksesta: Taloudessa, jossa on 25 A sähköliittymä rajataan vesivaraajan käynnistystä niin, että sitä ei laiteta päälle, mikäli hetkellinen kuorma on yli 20A. Näin voidaan mahdollisesti pienentää liittymän kokoa ja siitä aiheutuneita tehomaksuja.  

Powerguru voi myös ohjata vesikiertoista lattialämmitystä. Tietyissä Ouman-lämmönsäätimissä on kotona/poissa-kytkin, joka voidaan myös liittää automaattiseen ohjaukseen. Näin lämpöä varataan betonilaattaan kytkemällä ohjain kotona-tilaan  (korkeampi lämpötila) kun energia edullista ja lämmitystä vastaavasti vähennetään kytkemällä Ouman poissa-tilaan. Käyttäjä voi säätää Oumaniin em. tilojen lämpötilat halutuiksi - mitä suurempi lämpötilaero sitä enemmän voidaan lämpöä tarvittaessa varastoida lattiarakenteeseen. 


### Tietolähteet
Ohjelmisto kerää tietoa tarpeen mukaan valituista tietolähteistä. Tietolähteitä voivat olla:
- sähköliittymän kokonaiskulutusta/-myyntiä mittavaa ns. takamittari
- aurinkovoimalan invertterin tuotantotiedot
- sähkön nykyiset ja tulevat spot-hinnat
- aurinkovoimalan lähiajan tuotantoa ennustava energiasääennuste
- vesivaraajien lämpötila-anturit
- sähköauton tai akuston varaustieto (suunnitteilla)
![Data flow diagram](https://github.com/Olli69/powerguru/blob/main/docs/img/Powerguru%20data%20diagram.drawio.png?raw=true)

Sähkön markkinahinnat päivitetään eurooppalaisten verkko-operaattoreiden ylläpitämästä ENTSO-E -palvelusta https://www.entsoe.eu/.

### Takamittarointi
Laitteiden, esimerkiksi vesivaraajien, voi perustua aurinkovoimalan invertteriltä tulevaan tietoon senhetkisestä tuotetusta tehosta. Tällöin vesivaraaja voidaan kytkeä päälle, kun aurinkovoimalan tuotto ylittää asetetun rajan. Tämä voi olla riittävä tapa ohjata, jos kulutus on tasaista. Jos esim. oletetaan että talouden pohjakuorma aurinkoisena aikana on 2 kW, niin tämän ylittävä teho voidaan ohjata lämminvesivaraajalle, sillä muuten se menisi myyntiin (ja todennäköisesti myöhemmin varaajan lämmittämiseen ostettavan energian kokonaiskustannus olisi korkeampi). Powerguru tukee tätäkin ohjaustapaa, mikäli invertteri tukee tehotiedon automaattista hakua. Tarkempaan optimointiin päästään kuitenkin mikäli reaaliaikainen sähkönkulutus/myyntitieto luetaan ns. takamittarilta, jonka kautta kulkee kaikki sähköliittymän energia. Takamittari mittaa  samaa sähkövirtaa kuin verkkoyhtiön mittari, mutta se mahdollistaa tietojen reaaliaikaisen luvun järjestelmään - sähköyhtiön mittarilta ei reaaliaikaista tietoa ole saatavissa.

### Invertterin tiedot
Tällä hetkelle on kehitteillä liitännät tietyiltä Froniuksen ja SMA:n invertterimalleilta.

## Tekninen toteutus
Yksityiskohtaisempaa tietoa teknisestä toteutuksesta on luettavissa [englannikielisestä dokumentaatiosta](../README.md). 

### Raspberry Pi ohjauslaitteena
Raspberry Pi (Raspi) on yleisesti luotettava pieni tietokone, josta on osaamista paljon etenkin harrastajapiireissä. Oletuksena Raspi käyttää tietojen tallennukseen muistikorttia, jotka on suunniteltu tiedostojen tallennukseen esimerkiksi kameroissa eikä varsinaisesti tietokoneen massamuistiksi, jossa muisti voi joutua ajan kanssa liian kovalle kovalle käytölle. Muistikortin ennenaikainen rikkoutuminen on riski, jota voi välttää joko minimoimalla muistikortille tehtävät tallennukset tai korvaamalla muistikortin toisella tallennusvälineellä, kuten USB-porttiin tulevalla ulkoisella SDD-levyllä tai kiintolevyllä. Muistikorttia käytettäessä kannattaa valita mahdollisimman laadukas muistikortti. Kapasiteetiltään suurempi muistikortti kestää kauemmin kuin pieni muistikortti, koska samaan kohtaan muistikortti ei jouduta kirjoittamaan yhtä usein.

Powerguru on suunniteltu niin, että perusasennuksessa muistikortille kirjoitetaan harvoin, jolloin riski sen rikkoutuminen kulumisen vuoksi minimoituu. Tämä takia analytiikkatiedot tallennetaan pilvipalveluun. Mikäli kuitenkin tallentaa tiedot pilvipalvelun sijasta omalla Raspberry Pi palvelimelle, suosittelemme että siinä käytetään massamuistina ulkoista USB-massamuistia. Tämä asennus ei kuulu ns. perusasennukseen, vaan siinä tarvitaan jonkin verran Linux-käyttöjärjestelmäosaamista.

### Telegraf
Tietojen keräämiseen ja [Telegraf](https://github.com/influxdata/telegraf)

### Tiedon analysointi - InfluxDB ja Grafana 
Järjestelmän keräämät tiedot voidaan tallentaa analysointia varten. Helpoimmin tietojen keruu ja analysointi onnistuu pilvipohjaisessa palvelussa, mutta tiedot on myös mahdollista kerätä omalla palvelimelle.




