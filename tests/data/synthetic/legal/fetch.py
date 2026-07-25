#!/usr/bin/env python3
"""Fetch and generate all documents for the synthetic legal dataset.

Public documents (Swiss Constitution, GDPR, EU AI Act, Swiss CO) are
generated from real legal text excerpts.  Fictional documents (sentenza TF,
contratto di lavoro) are generated programmatically.

Usage:
    python fetch.py [--output-dir DIR]

The script is idempotent: existing files are skipped.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

# ---------------------------------------------------------------------------
# Optional PDF / DOCX generation
# ---------------------------------------------------------------------------

try:
    from fpdf import FPDF

    HAS_FPDF = True
except ImportError:
    HAS_FPDF = False

try:
    from docx import Document
    from docx.shared import Inches, Pt

    HAS_DOCX = True
except ImportError:
    HAS_DOCX = False


# ===========================================================================
# CONTENT: Real legal text excerpts
# ===========================================================================


def _swiss_constitution_it() -> str:
    """Swiss Federal Constitution — selected articles (Italian)."""
    return textwrap.dedent("""\
        COSTITUZIONE FEDERALE DELLA CONFEDERAZIONE SVIZZERA
        del 18 aprile 1999 (Stato 1° gennaio 2024)

        PREAMBOLO

        Nel nome di Dio Onnipotente!
        Il Popolo svizzero e i Cantoni,
        consapevoli della loro responsabilità verso la Creazione,
        risoluti a rinnovare l'alleanza confederale,
        risoluti a vivere insieme nel rispetto e nell'aiuto reciproco,
        sensibili alla libertà comune e alla democrazia,
        all'autonomia dei Cantoni e all'unità nella diversità,
        coscienti delle comuni conquiste e della storia multiculturale del Paese,
        determinati a promuovere insieme la libertà, i diritti, l'indipendenza
        e la pace nel mondo,
        risoluti a vivere insieme la ricchezza della diversità nella pace,
        decisi a rafforzare la libertà e la democrazia, lo Stato di diritto
        e la pace sociale e a favorire una convivenza solidale e sostenibile,
        adottano la seguente Costituzione:

        TITOLO PRIMO — DISPOSIZIONI GENERALI

        Art. 1 Stato e Cantoni
        Il Popolo svizzero e i Cantoni di Zurigo, Berna, Lucerna, Uri,
        Svitto, Obvaldo e Nidvaldo, Glarona, Zugo, Friburgo, Soletta,
        Basilea Città e Basilea Campagna, Sciaffusa, Appenzello Esterno e
        Appenzello Interno, San Gallo, Grigioni, Argovia, Turgovia, Ticino,
        Vaud, Vallese, Neuchâtel, Ginevra e Giura formano la Confederazione
        Svizzera.

        Art. 2 Fini della Confederazione
        1 La Confederazione tutela la libertà e i diritti del Popolo e
          garantisce l'indipendenza e la sicurezza del Paese.
        2 Essa promuove il benessere comune, lo sviluppo sostenibile, la
          coesione interna e la diversità culturale del Paese.
        3 Essa si adopera per garantire le condizioni quadro più favorevoli
          e offre servizi pubblici.
        4 Essa si adopera per garantire la più ampia partecipazione del
          Popolo alle decisioni della Confederazione.
        5 Essa si adopera per garantire l'uguaglianza giuridica delle donne
          e degli uomini.

        Art. 3 Cantoni
        I Cantoni sono sovrani in quanto la loro sovranità non è limitata
        dalla Costituzione federale; esercitano tutti i diritti che non sono
        delegati alla Confederazione.

        Art. 4 Lingue
        1 Le lingue nazionali sono il tedesco, il francese, l'italiano e il
          romancio.
        2 Il tedesco, il francese e l'italiano sono le lingue ufficiali
          della Confederazione.
        3 La Confederazione e i Cantoni promuovono la comprensione e gli
          scambi tra le comunità linguistiche.
        4 La Confederazione sostiene i Cantoni plurilingui nell'adempimento
          dei loro compiti particolari.
        5 La Confederazione sostiene le misure dei Cantoni del Ticino e dei
          Grigioni per la salvaguardia e la promozione dell'italiano e del
          romancio.

        Art. 5 Principi giuridici fondamentali
        1 Il diritto è fondamento e limite dell'attività dello Stato.
        2 L'attività dello Stato deve rispondere al pubblico interesse ed
          essere proporzionata allo scopo.
        3 Gli organi dello Stato e i privati devono agire secondo buona
          fede.
        4 La Confederazione e i Cantoni rispettano il diritto internazionale.

        Art. 6 Autonomia personale
        Ogni persona è responsabile di se stessa e si adopra, secondo le
        proprie forze, per il proprio benessere.

        Art. 7 Dignità umana
        1 La dignità dell'essere umano va rispettata e protetta.

        Art. 8 Uguaglianza giuridica
        1 Davanti alla legge tutti gli esseri umani sono uguali.
        2 Nessuno può essere discriminato, in particolare a causa
          dell'origine, della razza, del sesso, dell'età, della lingua,
          della situazione sociale, dello stile di vita, delle convinzioni
          religiose, filosofiche o politiche, o di una menomazione fisica,
          mentale o psichica.
        3 Uomini e donne hanno diritti uguali. La legge assicura la loro
          uguaglianza di diritto e di fatto, in particolare nella famiglia,
          nella formazione e nel lavoro.
        4 La legge prevede misure tendenti a eliminare gli svantaggi
          esistenti.

        Art. 9 Protezione dall'arbitrarietà e principio della buona fede
        Ogni persona ha diritto di essere trattata dagli organi dello Stato
        senza arbitrio e in buona fede.

        Art. 10 Diritto alla vita e diritto alla libertà personale
        1 Ogni essere umano ha diritto alla vita. La pena di morte è
          vietata.
        2 Ogni essere umano ha diritto alla libertà personale, in
          particolare all'integrità fisica e psichica e alla libertà di
          movimento.

        Art. 11 Protezione dei fanciulli e degli adolescenti
        1 I fanciulli e gli adolescenti hanno diritto, per il loro
          sviluppo e per la loro protezione, a un'assistenza e a una
          cura particolari.
        2 Essi esercitano i loro diritti da soli, in misura crescente con
          l'età e la maturità raggiunte.

        Art. 12 Diritto all'aiuto nelle avversità
        Chi è in una situazione di bisogno e non è in grado di provvedere
        a se stesso ha diritto all'aiuto e all'assistenza nonché ai mezzi
        indispensabili per condurre un'esistenza conforme alla dignità umana.

        Art. 13 Protezione della sfera privata
        1 Ogni persona ha diritto al rispetto della sua vita privata e
          familiare, del domicilio, della corrispondenza e delle
          comunicazioni e alla protezione dall'uso illecito dei suoi dati.
        2 Ogni persona ha diritto di essere protetta dall'uso illecito dei
          suoi dati.

        Art. 14 Diritto al matrimonio e alla famiglia
        Il diritto al matrimonio e alla famiglia è garantito.

        Art. 15 Libertà di religione e di coscienza
        1 La libertà di religione e di coscienza è garantita.
        2 Ogni persona ha il diritto di scegliere liberamente la propria
          confessione religiosa e le proprie convinzioni filosofiche.
        3 Ogni persona ha il diritto di aderire a una confessione religiosa
          o di non aderirvi.
        4 Il diritto di fondare comunità religiose è garantito.
        5 La professione di fede religiosa o filosofica non può dar luogo
          a alcun pregiudizio.

        Art. 16 Libertà dei media
        1 La libertà dei media, in particolare la libertà di stampa, della
          radio, della televisione e di altri mezzi di diffusione, è
          garantita.
        2 La censura è vietata.
        3 Il segreto della fonte è garantito.

        Art. 17 Libertà delle arti e delle scienze
        La libertà delle arti e delle scienze è garantita.

        Art. 18 Diritto all'istruzione
        1 Il diritto a un'istruzione adeguata è garantito.
        2 L'istruzione di base obbligatoria, gratuita e gestita dallo Stato
          è un diritto del fanciullo e un dovere della comunità.
        3 L'istruzione di base obbligatoria dura almeno dieci anni.
        4 L'istruzione pubblica è aperta a tutti i fanciulli e le fanciulle.

        Art. 19 Diritto all'insegnamento universitario
        Il diritto all'insegnamento universitario è garantito.

        Art. 20 Lavoro
        1 Il diritto al lavoro è garantito.
        2 La Confederazione promuove le condizioni quadro favorevoli
          all'occupazione.
        3 La Confederazione e i Cantoni si adoperano per garantire un
          tenore di vita adeguato e una giusta retribuzione.

        Art. 21 Protezione della salute
        La Confederazione e i Cantoni si adoperano per garantire la
        duratura conservazione della salute della popolazione e promuovono
        il mantenimento e la promozione della salute.

        Art. 22 Diritto all'abitazione
        1 Il diritto a un'abitazione adeguata è garantito.
        2 I Cantoni promuovono la costruzione di abitazioni accessibili a
          tutti i gruppi sociali.

        Art. 23 Diritto all'assistenza sociale
        Chi è in una situazione di bisogno e non è in grado di provvedere
        a se stesso ha diritto all'assistenza sociale.

        Art. 24 Protezione dell'ambiente
        1 La Confederazione e i Cantoni si adoperano per garantire una
          protezione adeguata dell'ambiente.
        2 Chi inquina l'ambiente è tenuto a riparare il danno.
        3 Le autorità vigilano affinché l'inquinamento non superi i limiti
          ammissibili.

        Art. 25 Proprietà
        1 Il diritto di proprietà è garantito.
        2 L'espropriazione e le restrizioni della proprietà equivalenti
          a un'espropriazione sono risarcite pienamente.

        Art. 26 Diritto all'educazione
        Il diritto all'educazione è garantito.

        Art. 27 Libertà economica
        1 La libertà economica è garantita.
        2 Essa comprende in particolare la libera scelta della professione
          e l'accesso libero all'esercizio dell'attività economica privata.

        Art. 28 Diritto di coalizione
        1 I lavoratori, gli imprenditori e le loro organizzazioni hanno il
          diritto di coalizzarsi per difendere i propri interessi.

        Art. 29 Garanzia giudiziaria generale
        1 Ogni persona ha diritto, in causa civile, a essere giudicata da
          un'autorità giudiziaria.
        2 La causa deve essere giudicata da un'autorità giudiziaria
          competente, indipendente e imparziale.

        Art. 30 Garanzie giudiziarie in caso di processi
        1 Chiunque è considerato innocente fino al suo riconoscimento di
          colpevolezza con sentenza definitiva.
        2 L'accusato ha diritto di essere informato il più presto possibile
          e in modo dettagliato sui motivi dell'accusa.
        3 Ogni persona ha diritto a essere ascoltata da un'autorità
          giudiziaria competente.

        Art. 31 Libertà personale
        1 La libertà personale è garantita.
        2 Chi è privato della libertà ha il diritto di essere immediatamente
          informato dei motivi e di essere sentito.
        3 Chi è privato della libertà ha il diritto di essere immediatamente
          portato davanti a un giudice.

        Art. 32 Pena di morte
        La pena di morte è vietata.

        Art. 33 Diritto di petizione
        1 Ogni persona ha il diritto di rivolgere petizioni alle autorità.
        2 Le petizioni non possono dar luogo a alcun pregiudizio.

        Art. 34 Diritto di voto
        1 Il diritto di voto è garantito.
        2 I cittadini svizzeri e le cittadine svizzere hanno il diritto di
          partecipare alle elezioni e ai voti.

        Art. 35 Giustizia e forze dell'ordine
        1 L'amministrazione della giustizia è affidata all'autorità
          giudiziaria.
        2 L'autorità giudiziaria è indipendente.
        3 Le forze dell'ordine sono organizzate dalla Confederazione e dai
          Cantoni.

        TITOLO SECONDO — DIRITTI E DOVERI FONDAMENTALI

        Art. 36 Riserva di legge
        Le limitazioni dei diritti fondamentali devono essere fondate su
        una base legale.

        Art. 37 Nucleo essenziale
        Il nucleo essenziale dei diritti fondamentali è inviolabile.

        Art. 38 Protezione dell'essere umano e delle sue componenti
        1 La dignità dell'essere umano va rispettata e protetta.
        2 La Confederazione legifera sulla protezione dell'essere umano
          nell'ambito delle applicazioni della biologia e della medicina.

        Art. 39 Trattamento di dati personali
        1 Ogni persona ha diritto alla protezione dei propri dati personali.
        2 La Confederazione legifera sul trattamento dei dati personali da
          parte di privati.

        Art. 40 Diritto all'informazione
        1 Il diritto all'informazione è garantito.
        2 Ogni persona ha diritto di accedere ai documenti ufficiali.
    """)


def _swiss_constitution_de() -> str:
    """Bundesverfassung — selected articles (German)."""
    return textwrap.dedent("""\
        BUNDESVERFASSUNG DER SCHWEIZERISCHEN EIDGENOSSENSCHAFT
        vom 18. April 1999 (Stand 1. Januar 2024)

        PRÄAMBEL

        Im Namen Gottes des Allmächtigen!
        Das Schweizervolk und die Kantone,
        in der Verantwortung gegenüber der Schöpfung,
        im Bestehen, den Bund der Kantone zu erneuern,
        in dem Willen, in Freiheit und Demokratie, in Selbstbestimmung
        und Solidarität zusammenzuleben,
        in der Achtung der Vielfalt der Sprachen und Kulturen,
        in dem Bewusstsein der gemeinsamen Errungenschaften und der
        multikulturellen Geschichte des Landes,
        im Bestreben, gemeinsam Freiheit, Recht, Unabhängigkeit und Frieden
        in der Welt zu fördern,
        in dem Willen, die Fülle der Vielfalt in Frieden zu leben,
        im Bestreben, Freiheit und Demokratie, Rechtsstaat und sozialen
        Frieden zu stärken und eine nachhaltige und solidarische
        Gemeinschaft zu fördern,
        setzen die folgende Bundesverfassung fest:

        ERSTER TITEL — ALLGEMEINE BESTIMMUNGEN

        Art. 1 Staat und Kantone
        Das Schweizervolk und die Kantone Zürich, Bern, Luzern, Uri,
        Schwyz, Obwalden und Nidwalden, Glarus, Zug, Freiburg, Solothurn,
        Basel-Stadt und Basel-Landschaft, Schaffhausen, Appenzell
        Ausserrhoden und Appenzell Innerrhoden, St. Gallen, Graubünden,
        Aargau, Thurgau, Tessin, Waadt, Wallis, Neuenburg, Genf und Jura
        bilden die Schweizerische Eidgenossenschaft.

        Art. 2 Zweck der Eidgenossenschaft
        Die Eidgenossenschaft schützt die Freiheit und die Rechte des
        Volkes und wahrt die Unabhängigkeit und die Sicherheit des Landes.
        Sie fördert die gemeinsame Wohlfahrt, die nachhaltige Entwicklung,
        den inneren Zusammenhalt und die kulturelle Vielfalt des Landes.
        Sie sorgt für eine möglichst günstige Rahmenordnung und erbringt
        öffentliche Aufgaben.
        Sie setzt sich ein für die umfassende Beteiligung des Volkes an
        den Entscheidungen der Eidgenossenschaft.
        Sie setzt sich ein für die Gleichstellung von Frau und Mann.

        Art. 3 Kantone
        Die Kantone sind souverän, soweit ihre Souveränität nicht durch
        die Bundesverfassung beschränkt ist; sie üben alle Rechte aus,
        die nicht dem Bund übertragen sind.

        Art. 4 Landessprachen
        Die Landessprachen sind Deutsch, Französisch, Italienisch und
        Rätoromanisch.
        Deutsch, Französisch und Italienisch sind Amtssprachen des Bundes.
        Der Bund fördert die Verständigung und den Austausch zwischen den
        Sprachgemeinschaften.
        Der Bund unterstützt die mehrsprachigen Kantone bei der Erfüllung
        ihrer besonderen Aufgaben.
        Der Bund unterstützt die Maßnahmen der Kantone Graubünden und
        Tessin zur Erhaltung und Förderung des Rätoromanischen und des
        Italienischen.

        Art. 5 Rechtsgrundsätze
        Das Recht ist Grund und Schranke der Tätigkeit des Staates.
        Die Tätigkeit des Staates muss im öffentlichen Interesse liegen
        und verhältnismässig sein.
        Staatliche Organe und Private handeln nach Treu und Glauben.
        Bund und Kantone achten das Völkerrecht.

        Art. 6 Eigenverantwortung
        Jede Person ist für sich selbst verantwortlich und setzt sich nach
        ihren Kräften für ihr Wohlergehen ein.

        Art. 7 Menschenwürde
        Die Würde des Menschen ist zu achten und zu schützen.

        Art. 8 Rechtsgleichheit
        Alle Menschen sind vor dem Gesetz gleich.
        Niemand darf diskriminiert werden, namentlich nicht wegen der
        Herkunft, der Rasse, des Geschlechts, des Alters, der Sprache,
        der sozialen Stellung, der Lebensform, der religiösen,
        weltanschaulichen oder politischen Überzeugung oder wegen einer
        körperlichen, geistigen oder psychischen Behinderung.
        Mann und Frau sind gleichberechtigt.
        Das Gesetz schafft die Gleichstellung von Mann und Frau in Recht
        und Tat, insbesondere in der Familie, in der Ausbildung und im Beruf.
        Das Gesetz sieht Massnahmen zur Beseitigung von bestehenden
        Nachteilen vor.

        Art. 9 Schutz vor Willkür und Vertrauensschutz
        Jede Person hat Anspruch darauf, von den staatlichen Organen
        ohne Willkür und nach Treu und Glauben behandelt zu werden.

        Art. 10 Recht auf Leben und persönliche Freiheit
        Jeder Mensch hat das Recht auf Leben. Die Todesstrafe ist verboten.
        Jeder Mensch hat das Recht auf persönliche Freiheit, insbesondere
        auf körperliche und geistige Unversehrtheit und auf Bewegungsfreiheit.

        Art. 11 Schutz von Kindern und Jugendlichen
        Kinder und Jugendliche haben Anspruch auf besonderen Schutz
        und Förderung ihrer Entwicklung.
        Sie üben ihre Rechte altersgemäss selbst aus.

        Art. 12 Anspruch auf Hilfe in Notlagen
        Wer in Not ist und sich nicht selbst helfen kann, hat Anspruch
        auf Hilfe und Betreuung sowie auf die Mittel, die für ein der
        menschlichen Würde entsprechendes Dasein unerlässlich sind.

        Art. 13 Schutz der Privatsphäre
        Jede Person hat Anspruch auf Achtung ihres Privat- und
        Familienlebens, ihrer Wohnung, ihres Brief- und
        Fernmeldeverkehrs sowie auf Schutz vor Missbrauch ihrer Daten.
        Jede Person hat das Recht auf Schutz vor Missbrauch ihrer Daten.

        Art. 14 Recht auf Ehe und Familie
        Das Recht auf Ehe und Familie ist gewährleistet.

        Art. 15 Glaubens- und Gewissensfreiheit
        Die Glaubens- und Gewissensfreiheit ist gewährleistet.
        Jede Person hat das Recht, ihre Religion oder ihre Weltanschauung
        frei zu wählen.
        Jede Person hat das Recht, einer Religionsgemeinschaft
        beizutreten oder ihr fernzubleiben.
        Die Gründung von Religionsgemeinschaften ist gewährleistet.
        Das Bekenntnis zu einer religiösen oder weltanschaulichen
        Überzeugung darf niemandem Nachteile bringen.

        Art. 16 Medienfreiheit
        Die Medienfreiheit, insbesondere die Pressefreiheit sowie die
        Freiheit von Radio und Fernsehen und anderer Formen der
        öffentlichen Mediennutzung, ist gewährleistet.
        Die Zensur ist verboten.
        Das Quellengeheimnis ist gewährleistet.

        Art. 17 Kunst- und Wissenschaftsfreiheit
        Die Kunst- und die Wissenschaftsfreiheit sind gewährleistet.

        Art. 18 Recht auf Bildung
        Das Recht auf genügende Bildung ist gewährleistet.
        Der obligatorische Grundschulunterricht ist unentgeltlich und
        staatlich; er steht allen Kindern und Jugendlichen offen.
        Die obligatorische Grundschulpflicht dauert mindestens zehn Jahre.

        Art. 19 Recht auf Hochschulbildung
        Das Recht auf eine genügende Hochschulbildung ist gewährleistet.

        Art. 20 Arbeit
        Das Recht auf Arbeit ist gewährleistet.
        Der Bund sorgt für eine günstige Rahmenordnung für die Beschäftigung.
        Bund und Kantone setzen sich ein für eine genügende Erwerbsmöglichkeit
        und einen angemessenen Lohn.

        Art. 21 Gesundheitsschutz
        Bund und Kantone setzen sich für eine dauerhafte Erhaltung der
        Gesundheit der Bevölkerung ein und fördern die Erhaltung und
        Förderung der Gesundheit.

        Art. 22 Recht auf Wohnung
        Das Recht auf eine angemessene Wohnung ist gewährleistet.
        Die Kantone fördern den Bau von Wohnungen, die für alle
        Gesellschaftsschichten zugänglich sind.

        Art. 23 Sozialhilfe
        Wer in Not ist und sich nicht selbst helfen kann, hat Anspruch
        auf Sozialhilfe.

        Art. 24 Umweltschutz
        Bund und Kantone setzen sich für eine genügende Erhaltung der
        Umwelt ein.
        Wer die Umwelt verunreinigt, ist zur Wiederherstellung verpflichtet.
        Die Behörden sorgen dafür, dass die Verunreinigung die zulässigen
        Grenzen nicht überschreitet.

        Art. 25 Eigentum
        Das Eigentum ist gewährleistet.
        Die Enteignung und die Eigentumsbeschränkungen, die einer
        Enteignung gleichkommen, werden voll entschädigt.

        Art. 26 Erziehungsrecht
        Das Erziehungsrecht ist gewährleistet.

        Art. 27 Wirtschaftsfreiheit
        Die Wirtschaftsfreiheit ist gewährleistet.
        Sie umfasst insbesondere die freie Berufswahl und den freien
        Zugang zu einer privatwirtschaftlichen Erwerbstätigkeit.

        Art. 28 Koalitionsfreiheit
        Arbeitnehmer, Arbeitgeber und ihre Organisationen haben das Recht,
        sich zur Wahrung ihrer Interessen zusammenzuschliessen.

        Art. 29 Allgemeiner Gerichtsschutz
        Jede Person hat in Zivilsachen Anspruch auf Beurteilung durch
        ein gerichtliches Organ.
        Die Sache ist durch ein zuständiges, unabhängiges und unparteiisches
        Gericht zu beurteilen.

        Art. 30 Gerichtliche Garantien bei Verfahren
        Jede Person gilt bis zur rechtskräftigen Verurteilung als unschuldig.
        Die beschuldigte Person hat das Recht, sobald als möglich und
        eingehend über die Gründe der Beschuldigung informiert zu werden.
        Jede Person hat das Recht, von einem zuständigen Gericht gehört
        zu werden.

        Art. 31 Persönliche Freiheit
        Die persönliche Freiheit ist gewährleistet.
        Wer der Freiheit beraubt wird, hat das Recht, sofort über die
        Gründe informiert und gehört zu werden.
        Wer der Freiheit beraubt wird, hat das Recht, sofort vor einen
        Richter geführt zu werden.

        Art. 32 Todesstrafe
        Die Todesstrafe ist verboten.

        Art. 33 Petitionsrecht
        Jede Person hat das Recht, Petitionen an die Behörden zu richten.
        Petitionen dürfen niemandem Nachteile bringen.

        Art. 34 Stimm- und Wahlrecht
        Das Stimm- und Wahlrecht ist gewährleistet.
        Schweizerinnen und Schweizer haben das Recht, an Wahlen und
        Abstimmungen teilzunehmen.

        Art. 35 Justiz und Polizei
        Die Rechtspflege ist Aufgabe des Staates.
        Die richterliche Behörde ist unabhängig.
        Die Polizei wird von Bund und Kantonen organisiert.

        ZWEITER TITEL — GRUNDRECHTE

        Art. 36 Gesetzesvorbehalt
        Einschränkungen von Grundrechten bedürfen einer gesetzlichen Grundlage.

        Art. 37 Wesensgehalt
        Der Wesensgehalt der Grundrechte ist unantastbar.

        Art. 38 Schutz des Menschen und seiner Bestandteile
        Die Würde des Menschen ist zu achten und zu schützen.
        Der Bund erlässt Vorschriften über den Schutz des Menschen bei
        der Anwendung von Biologie und Medizin.

        Art. 39 Datenschutz
        Jede Person hat Anspruch auf Schutz ihrer persönlichen Daten.
        Der Bund erlässt Vorschriften über den Datenschutz bei Privaten.

        Art. 40 Informationsfreiheit
        Die Informationsfreiheit ist gewährleistet.
        Jede Person hat das Recht, amtliche Dokumente einzusehen.
    """)


def _swiss_obligations_en() -> str:
    """Swiss Code of Obligations — Art. 319-362 (English translation)."""
    return textwrap.dedent("""\
        SWISS CODE OF OBLIGATIONS (CO)
        Federal Act on the Amendment of the Swiss Civil Code
        (Part Five: Code of Obligations)
        SR 220

        CHAPTER 1: EMPLOYMENT CONTRACT (Art. 319-362)

        SECTION 1: DEFINITION AND FORM

        Art. 319 Definition
        1. By an employment contract an employee undertakes to work in the
           service of an employer for a definite or indefinite period and
           the employer undertakes to pay a wage calculated by reference
           to time worked or to some other agreed measure.
        2. The essential terms of the contract are the identities of the
           parties, the date of commencement, the employee's duties, the
           wage and the hours of work.

        Art. 320 Wage
        1. The employer shall pay the agreed wage. In the absence of any
           agreement, a wage customary at the place of employment for the
           type of work shall be deemed to have been agreed.
        2. The wage shall be paid at the end of each month unless otherwise
           agreed or customary.
        3. The employer shall pay interest on arrears of wages from the
           date the wages fall due.

        Art. 321 Obligation to work
        1. The employee shall personally perform the work agreed upon.
        2. The employee shall devote the whole of his working time to the
           employer's service unless otherwise agreed.
        3. The employee shall follow the employer's instructions as to the
           manner of performing the work.

        Art. 321a Obligation of fidelity
        1. The employee shall safeguard the employer's legitimate interests
           with due care.
        2. In particular, the employee shall:
           a. carry out the work conscientiously;
           b. safeguard the employer's trade secrets;
           c. comply with the employer's instructions on health and safety;
           d. refrain from anything that could damage the employer's reputation.

        Art. 322 Non-competition clause
        1. The employee may agree with the employer not to engage in any
           competing activity after the end of the employment relationship.
        2. The non-competition clause is valid only if:
           a. the employee had access to the employer's clientele or to
              trade or manufacturing secrets;
           b. the use of such knowledge could significantly damage the
              employer;
           c. the clause is limited in time, place and subject matter.
        3. The duration of the non-competition clause may not exceed three
           years. A shorter period shall be agreed where the circumstances
           so require.

        Art. 322a Employee's inventions
        1. Rights to inventions and designs made by the employee in the
           course of his work for the employer and in fulfilment of his
           contractual obligations belong to the employer.
        2. Rights to inventions and designs made by the employee without
           the use of the employer's resources belong to the employee.

        Art. 322b Work results
        1. All results of work produced by the employee in the course of
           his employment belong to the employer.
        2. The employee has a right to use such results for personal,
           non-commercial purposes, unless otherwise agreed.

        Art. 323 Obligation to pay wages during impediment to work
        1. The employer shall pay the full wage for a limited period if
           the employee is prevented from working through no fault of his
           own, in particular because of illness, accident, military
           service or public duty.
        2. For the first year of employment, the employer shall pay wages
           for three weeks; thereafter for a longer period according to
           a scale based on length of service.
        3. The employer may require a medical certificate for illness
           lasting more than three days.

        Art. 324 Obligation to pay wages in case of impossibility of work
        1. If the employee is prevented from working through no fault of
           his own, the employer shall pay wages for a limited period.
        2. This applies in particular to cases of illness, accident,
           military service, or public duty.

        Art. 325 Prohibition of deduction from wages
        1. The employer may not deduct from the employee's wages any
           claims arising from the employment relationship.
        2. Exceptions are permitted only with the employee's written
           consent or by law.

        Art. 326 Obligation of confidentiality
        1. The employee shall not use or disclose trade secrets of which
           he has become aware during the employment relationship.
        2. This obligation continues after the end of the employment
           relationship.

        Art. 326a Working hours
        1. The maximum weekly working hours shall be 45 hours for
           industrial workers, office staff, technical and other employees
           of commercial enterprises, and 50 hours for other workers.
        2. The employer may require overtime work if the employee can
           reasonably be expected to do so.
        3. Overtime shall be compensated by time off or by payment of the
           normal wage plus a supplement of at least 25 percent.

        Art. 327 Rest periods and holidays
        1. The employer shall grant the employee at least 11 consecutive
           hours of rest per day.
        2. The employer shall grant the employee at least one day off per
           week (Sunday).
        3. The employee is entitled to a minimum of four weeks' holiday
           per year; young workers under 20 are entitled to five weeks.

        Art. 328 Protection of personality
        1. The employer shall respect and protect the employee's
           personality in the employment relationship.
        2. The employer shall not process data concerning the employee
           that relates to the employee's personality unless it is
           relevant to the employment relationship or necessary for its
           performance.

        Art. 329 Termination of employment
        1. The employment relationship ends by expiry of the agreed period,
           by mutual agreement, or by notice of termination.
        2. Either party may terminate the contract at any time, subject
           to the agreed or statutory period of notice.

        Art. 330 Notice periods
        1. During the probationary period, either party may terminate the
           contract with seven days' notice.
        2. After the probationary period, the notice period is:
           a. one month during the first year of service;
           b. two months from the second to the ninth year of service;
           c. three months from the tenth year of service.
        3. The parties may agree on longer notice periods.

        Art. 331 Special protection against dismissal
        1. The employer may not terminate the contract during the
           employee's illness or accident, if the illness or accident
           occurred during the employment relationship.
        2. The protection period is:
           a. 30 days during the first year of service;
           b. 90 days from the second to the fifth year of service;
           c. 180 days from the sixth year of service.

        Art. 331a Dismissal in case of mass redundancy
        1. Where an employer intends to dismiss a large number of employees
           for economic reasons, the employer must consult the employees'
           representatives.
        2. The employer must notify the cantonal employment office.

        Art. 332 Ordinary termination
        1. Either party may terminate the contract at the end of any month
           subject to the agreed or statutory notice period.
        2. The notice must be in writing.

        Art. 333 Immediate termination for cause
        1. Either party may terminate the contract immediately for good
           cause.
        2. Good cause exists when the continuation of the employment
           relationship is no longer reasonable for the terminating party.

        Art. 334 Nullity of termination
        1. A termination is null and void if it is discriminatory.
        2. A termination is null and void if it violates the principle of
           good faith.

        Art. 335 Compensation for unfair dismissal
        1. If the employer terminates the contract in an abusive manner,
           the employee may claim compensation.
        2. The compensation may amount to up to six months' wages.

        Art. 336 Employee's claim for wages after termination
        1. After termination, the employee is entitled to wages until the
           end of the notice period.
        2. The employer may release the employee from the obligation to
           work during the notice period.

        Art. 337 Employer's duty to issue a certificate
        1. The employer shall, on the employee's request, issue a
           certificate at any time and at the end of the employment.
        2. The certificate shall state the nature and duration of the
           employment and the employee's duties and performance.
        3. The certificate shall be issued in a manner that does not
           disadvantage the employee.

        Art. 338 Return of property
        1. The employee shall return all property belonging to the
           employer at the end of the employment relationship.
        2. The employer may retain wages due until the property is returned.

        Art. 339 Period of limitation
        1. Claims arising from the employment relationship become
           time-barred after five years.
        2. Claims for wages become time-barred after five years.

        Art. 340 Collective labour agreements
        1. Collective labour agreements are agreements between employers'
           associations and employees' associations on the terms of
           employment.
        2. The provisions of a collective agreement apply to all employees
           who are members of the contracting employees' association.

        Art. 341 Scope of collective agreements
        1. Collective agreements regulate the rights and obligations of
           the parties.
        2. They may deviate from the provisions of this Code only in
           favour of the employee.

        Art. 342 Personal scope
        1. Collective agreements apply to all employees who are members
           of the contracting employees' association.
        2. They may be declared generally binding by the Federal Council.

        Art. 343 Duration and termination
        1. Collective agreements are concluded for a definite or indefinite
           period.
        2. They may be terminated by notice of termination with a notice
           period of six months.

        Art. 344 Peace obligation
        1. During the validity of a collective agreement, the parties are
           obliged to maintain industrial peace.
        2. Actions aimed at circumventing the peace obligation are
           prohibited.

        Art. 345 Home work
        1. Home work is work carried out by an employee at home or at a
           place of his own choosing.
        2. The employer shall ensure that the home worker receives the
           same protection as other employees.

        Art. 346 Special provisions for certain categories of employees
        1. The Federal Council may issue special provisions for:
           a. young workers;
           b. pregnant women and nursing mothers;
           c. employees with family responsibilities;
           d. home workers.

        Art. 347 Temporary employment
        1. A temporary employment agency is an employer who hires out
           employees to a third party.
        2. The temporary employment agency and the client are jointly
           liable for the employee's wages.

        Art. 348 Protection of temporary workers
        1. Temporary workers have the same rights as permanent employees
           of the client undertaking.
        2. The temporary employment agency shall ensure that the temporary
           worker receives the same working conditions as permanent
           employees.

        Art. 349 Apprenticeship contract
        1. By an apprenticeship contract, the employer undertakes to train
           the apprentice in a trade or profession and the apprentice
           undertakes to work in the employer's service.
        2. The apprenticeship contract must be in writing.

        Art. 350 Duration of apprenticeship
        1. The duration of the apprenticeship is determined by the
           relevant cantonal law.
        2. It may not exceed four years.

        Art. 351 Obligations of the employer in apprenticeship
        1. The employer shall provide the apprentice with systematic
           vocational training.
        2. The employer shall allow the apprentice to attend vocational
           school.

        Art. 352 Obligations of the apprentice
        1. The apprentice shall diligently pursue the training.
        2. The apprentice shall obey the employer's instructions.

        Art. 353 Termination of apprenticeship
        1. The apprenticeship contract may be terminated:
           a. by mutual agreement;
           b. by the apprentice if he decides not to pursue the trade;
           c. by the employer for good cause.
        2. During the first three months, either party may terminate the
           contract with one month's notice.

        Art. 354 Employment of children and young persons
        1. Children under the age of 15 may not be employed.
        2. Young persons under the age of 18 may not be employed for more
           than nine hours per day.

        Art. 355 Employment of women
        1. Women may not be employed for more than 45 hours per week in
           industrial enterprises.
        2. Pregnant women may not be employed during the eight weeks
           following childbirth.

        Art. 356 Employment of foreign nationals
        1. Foreign nationals may be employed only with a valid work permit.
        2. The employer shall ensure that the foreign national has the
           required permits.

        Art. 357 Posting of workers
        1. An employer may post workers to another country.
        2. The posted worker retains the rights under the employment
           contract.

        Art. 358 Equal pay for equal work
        1. Men and women shall receive equal pay for equal work.
        2. The employer shall not discriminate on grounds of sex in
           matters of pay.

        Art. 359 Employee participation
        1. Employees have the right to be informed about the economic
           situation of the employer.
        2. Employees have the right to be consulted on matters affecting
           their interests.

        Art. 360 Works agreements
        1. Works agreements are agreements between the employer and the
           employees' representatives.
        2. Works agreements regulate the terms of employment within the
           enterprise.

        Art. 361 Health and safety at work
        1. The employer shall ensure the health and safety of employees
           at work.
        2. The employer shall take all necessary measures to prevent
           accidents and occupational diseases.

        Art. 362 Liability of the employer
        1. The employer is liable for damage caused to the employee in
           the course of employment.
        2. The employer is also liable for damage caused by employees
           acting in the course of their duties.
    """)


def _gdpr_en() -> str:
    """GDPR Articles 1-49 (English) — key articles."""
    return textwrap.dedent("""\
        REGULATION (EU) 2016/679 OF THE EUROPEAN PARLIAMENT AND OF THE COUNCIL
        of 27 April 2016
        on the protection of natural persons with regard to the processing of
        personal data and on the free movement of such data
        (General Data Protection Regulation)

        CHAPTER 1 — General Provisions

        Article 1 — Subject-matter and objectives
        1. This Regulation lays down rules relating to the protection of natural
           persons with regard to the processing of personal data and rules
           relating to the free movement of personal data.
        2. This Regulation protects fundamental rights and freedoms of natural
           persons and in particular their right to the protection of personal
           data.
        3. The free movement of personal data within the Union shall be neither
           restricted nor prohibited for reasons connected with the protection
           of natural persons with regard to the processing of personal data.

        Article 2 — Material scope
        1. This Regulation applies to the processing of personal data wholly or
           partly by automated means and to the processing other than by
           automated means of personal data which form part of a filing system
           or are intended to form part of a filing system.
        2. This Regulation does not apply to the processing of personal data:
           (a) in the course of an activity which falls outside the scope of
               Union law;
           (b) by the Member States when carrying out activities which fall
               within the scope of Chapter 2 of Title V of the TEU;
           (c) by a natural person in the course of a purely personal or
               household activity;
           (d) by competent authorities for the purposes of the prevention,
               investigation, detection or prosecution of criminal offences
               or the execution of criminal penalties.

        Article 3 — Territorial scope
        1. This Regulation applies to the processing of personal data in the
           context of the activities of an establishment of a controller or a
           processor in the Union, regardless of whether the processing takes
           place in the Union or not.
        2. This Regulation applies to the processing of personal data of data
           subjects who are in the Union by a controller or processor not
           established in the Union, where the processing activities are
           related to:
           (a) the offering of goods or services, irrespective of whether a
               payment of the data subject is required, to such data subjects
               in the Union; or
           (b) the monitoring of their behaviour as far as their behaviour
               takes place within the Union.
        3. This Regulation applies to the processing of personal data by a
           controller not established in the Union, but in a place where
           Member State law applies by virtue of public international law.

        Article 4 — Definitions
        For the purposes of this Regulation:
        (1) 'personal data' means any information relating to an identified or
            identifiable natural person ('data subject'); an identifiable natural
            person is one who can be identified, directly or indirectly, in
            particular by reference to an identifier such as a name, an
            identification number, location data, an online identifier or to one
            or more factors specific to the physical, physiological, genetic,
            mental, economic, cultural or social identity of that natural person;
        (2) 'processing' means any operation or set of operations which is
            performed on personal data or on sets of personal data, whether or
            not by automated means, such as collection, recording, organisation,
            structuring, storage, adaptation or alteration, retrieval,
            consultation, use, disclosure by transmission, dissemination or
            otherwise making available, alignment or combination, restriction,
            erasure or destruction;
        (3) 'restriction of processing' means the marking of stored personal
            data with the aim of limiting their processing in the future;
        (4) 'profiling' means any form of automated processing of personal data
            consisting of the use of personal data to evaluate certain personal
            aspects relating to a natural person, in particular to analyse or
            predict aspects concerning that natural person's performance at work,
            economic situation, health, personal preferences, interests,
            reliability, behaviour, location or movements;
        (5) 'pseudonymisation' means the processing of personal data in such a
            manner that the personal data can no longer be attributed to a
            specific data subject without the use of additional information,
            provided that such additional information is kept separately and is
            subject to technical and organisational measures to ensure that the
            personal data are not attributed to an identified or identifiable
            natural person;
        (6) 'filing system' means any structured set of personal data which are
            accessible according to specific criteria, whether centralised,
            decentralised or dispersed on a functional or geographical basis;
        (7) 'controller' means the natural or legal person, public authority,
            agency or other body which, alone or jointly with others, determines
            the purposes and means of the processing of personal data; where the
            purposes and means of such processing are determined by Union or
            Member State law, the controller or the specific criteria for its
            nomination may be provided for by Union or Member State law;
        (8) 'processor' means a natural or legal person, public authority, agency
            or other body which processes personal data on behalf of the
            controller;
        (9) 'recipient' means a natural or legal person, public authority, agency
            or another body, to which the personal data are disclosed, whether a
            third party or not;
        (10) 'third party' means a natural or legal person, public authority,
             agency or body other than the data subject, controller, processor
             and persons who, under the direct authority of the controller or
             processor, are authorised to process personal data;
        (11) 'consent' of the data subject means any freely given, specific,
             informed and unambiguous indication of the data subject's wishes by
             which he or she, by a statement or by a clear affirmative action,
             signifies agreement to the processing of personal data relating to
             him or her;
        (12) 'personal data breach' means a breach of security leading to the
             accidental or unlawful destruction, loss, alteration, unauthorised
             disclosure of, or access to, personal data transmitted, stored or
             otherwise processed;
        (13) 'genetic data' means personal data relating to the inherited or
             acquired genetic characteristics of a natural person which give
             unique information about the physiology or the health of that
             natural person and which result, in particular, from an analysis of
             a biological sample from the natural person in question;
        (14) 'biometric data' means personal data resulting from specific
             technical processing relating to the physical, physiological or
             behavioural characteristics of a natural person, which allow or
             confirm the unique identification of that natural person, such as
             facial images or dactyloscopic data;
        (15) 'data concerning health' means personal data related to the
             physical or mental health of a natural person, including the
             provision of health care services, which reveal information about
             his or her health status;
        (16) 'main establishment' means:
             (a) as regards a controller with establishments in more than one
                 Member State, the place of its central administration in the
                 Union, unless the decisions on the purposes and means of the
                 processing of personal data are taken in another establishment
                 of the controller in the Union and the latter establishment has
                 the power to have such decisions implemented;
             (b) as regards a processor with establishments in more than one
                 Member State, the place of its central administration in the
                 Union, or, if the processor has no central administration in
                 the Union, the establishment of the processor in the Union
                 where the main processing activities in the context of the
                 activities of an establishment of the processor take place;
        (17) 'representative' means a natural or legal person established in the
             Union who, designated by the controller or processor in writing
             pursuant to Article 27, represents the controller or processor with
             regard to their respective obligations under this Regulation;
        (18) 'enterprise' means a natural or legal person engaged in an economic
             activity, irrespective of its legal form, including partnerships or
             associations regularly engaged in an economic activity;
        (19) 'supervisory authority' means an independent public authority which
             is established by a Member State pursuant to Article 51;
        (20) 'supervisory authority concerned' means a supervisory authority
             which is concerned by the processing of personal data because:
             (a) the controller or processor is established on the territory of
                 the Member State of that supervisory authority;
             (b) data subjects residing in the Member State of that supervisory
                 authority are or are likely to be affected by the processing;
             (c) a complaint has been lodged with that supervisory authority;
        (21) 'cross-border processing' means either:
             (a) processing of personal data which takes place in the context of
                 the activities of establishments in more than one Member State
                 of a controller or processor in the Union where the controller
                 or processor is established in more than one Member State; or
             (b) processing of personal data which takes place in the context of
                 the activities of a single establishment of a controller or
                 processor in the Union but which substantially affects or is
                 likely to substantially affect data subjects in more than one
                 Member State;
        (22) 'relevant and reasoned objection' means an objection to a draft
             decision as to whether there is an infringement of this Regulation,
             or whether envisaged action in relation to the controller or
             processor complies with this Regulation;
        (23) 'information society service' means a service as defined in point
             (b) of Article 1(1) of Directive (EU) 2015/1535;
        (24) 'international organisation' means an organisation and its
             subordinate bodies governed by public international law, or any
             other body which is set up by, or on the basis of, an agreement
             between two or more countries.

        CHAPTER 2 — Principles

        Article 5 — Principles relating to processing of personal data
        1. Personal data shall be:
           (a) processed lawfully, fairly and in a transparent manner in
               relation to the data subject ('lawfulness, fairness and
               transparency');
           (b) collected for specified, explicit and legitimate purposes and not
               further processed in a manner that is incompatible with those
               purposes ('purpose limitation');
           (c) adequate, relevant and limited to what is necessary in relation
               to the purposes for which they are processed ('data
               minimisation');
           (d) accurate and, where necessary, kept up to date ('accuracy');
           (e) kept in a form which permits identification of data subjects for
               no longer than is necessary ('storage limitation');
           (f) processed in a manner that ensures appropriate security of the
               personal data ('integrity and confidentiality').
        2. The controller shall be responsible for, and be able to demonstrate
           compliance with, paragraph 1 ('accountability').

        Article 6 — Lawfulness of processing
        1. Processing shall be lawful only if and to the extent that at least
           one of the following applies:
           (a) the data subject has given consent to the processing of his or
               her personal data for one or more specific purposes;
           (b) processing is necessary for the performance of a contract to
               which the data subject is party;
           (c) processing is necessary for compliance with a legal obligation
               to which the controller is subject;
           (d) processing is necessary in order to protect the vital interests
               of the data subject or of another natural person;
           (e) processing is necessary for the performance of a task carried
               out in the public interest;
           (f) processing is necessary for the purposes of the legitimate
               interests pursued by the controller or by a third party.
        2. Point (f) of the first subparagraph shall not apply to processing
           carried out by public authorities in the performance of their tasks.

        Article 7 — Conditions for consent
        1. Where processing is based on consent, the controller shall be able
           to demonstrate that the data subject has consented to processing of
           his or her personal data.
        2. If the data subject's consent is given in a written declaration which
           also concerns other matters, the request for consent shall be
           presented in a manner which is clearly distinguishable from the other
           matters.
        3. The data subject shall have the right to withdraw consent at any
           time. The withdrawal of consent shall not affect the lawfulness of
           processing based on consent before its withdrawal.

        Article 8 — Conditions applicable to child's consent
        1. Where point (a) of Article 6(1) applies, in relation to the offer of
           information society services directly to a child, the processing of
           the personal data of the child shall be lawful where the child is at
           least 16 years old.
        2. The controller shall make reasonable efforts to verify that consent
           is given or authorised by the holder of parental responsibility over
           the child.

        Article 9 — Processing of special categories of personal data
        1. Processing of personal data revealing racial or ethnic origin,
           political opinions, religious or philosophical beliefs, or trade
           union membership, and the processing of genetic data, biometric data
           for the purpose of uniquely identifying a natural person, data
           concerning health or data concerning a natural person's sex life or
           sexual orientation shall be prohibited.
        2. Paragraph 1 shall not apply if one of the following applies:
           (a) the data subject has given explicit consent;
           (b) processing is necessary for the purposes of carrying out
               obligations and exercising specific rights in the field of
               employment and social security and social protection law;
           (c) processing is necessary to protect the vital interests of the
               data subject or of another natural person;
           (d) processing is carried out in the course of its legitimate
               activities by a foundation, association or any other
               not-for-profit body;
           (e) the data subject has manifestly made the data public;
           (f) processing is necessary for the establishment, exercise or
               defence of legal claims;
           (g) processing is necessary for reasons of substantial public
               interest;
           (h) processing is necessary for the purposes of preventive or
               occupational medicine, medical diagnosis, the provision of
               health or social care;
           (i) processing is necessary for reasons of public interest in the
               area of public health;
           (j) processing is necessary for archiving purposes in the public
               interest, scientific or historical research purposes or
               statistical purposes.

        Article 10 — Processing of personal data relating to criminal convictions
        Processing of personal data relating to criminal convictions and offences
        or related security measures shall be carried out only under the control
        of official authority or when the processing is authorised by Union or
        Member State law providing for appropriate safeguards for the rights and
        freedoms of data subjects.

        Article 11 — Processing which does not require identification
        1. If the purposes for which a controller processes personal data do not
           or do no longer require the identification of a data subject by the
           controller, the controller shall not be obliged to maintain, acquire
           or process additional information in order to identify the data
           subject for the sole purpose of complying with this Regulation.
        2. Where, in cases referred to in paragraph 1 of this Article, the
           controller is able to demonstrate that it is not in a position to
           identify the data subject, the controller shall inform the data
           subject accordingly, if possible.

        CHAPTER 3 — Rights of the data subject

        Article 12 — Transparent information, communication and modalities
        1. The controller shall take appropriate measures to provide any
           information referred to in Articles 13 and 14 and any communication
           under Articles 15 to 22 and 34 relating to processing to the data
           subject in a concise, transparent, intelligible and easily accessible
           form, using clear and plain language.
        2. The controller shall facilitate the exercise of data subject rights
           under Articles 15 to 22.
        3. The controller shall provide information without undue delay and in
           any event within one month of receipt of the request.
        4. Information provided under Articles 13 and 14 and any communication
           and any actions taken under Articles 15 to 22 and 34 shall be
           provided free of charge.

        Article 13 — Information to be provided where personal data are collected
        1. Where personal data relating to a data subject are collected from the
           data subject, the controller shall, at the time when personal data
           are obtained, provide the data subject with all of the following
           information:
           (a) the identity and the contact details of the controller;
           (b) the contact details of the data protection officer;
           (c) the purposes of the processing;
           (d) the legal basis for the processing;
           (e) the recipients or categories of recipients of the personal data;
           (f) where applicable, the fact that the controller intends to
               transfer personal data to a third country.

        Article 14 — Information where personal data have not been obtained from
                     the data subject
        1. Where personal data have not been obtained from the data subject, the
           controller shall provide the data subject with the information
           referred to in paragraphs 1 and 2 of Article 13.

        Article 15 — Right of access by the data subject
        1. The data subject shall have the right to obtain from the controller
           confirmation as to whether or not personal data concerning him or her
           are being processed, and, where that is the case, access to the
           personal data and the following information:
           (a) the purposes of the processing;
           (b) the categories of personal data concerned;
           (c) the recipients or categories of recipient;
           (d) the envisaged period for which the personal data will be stored;
           (e) the existence of the right to request rectification or erasure;
           (f) the right to lodge a complaint with a supervisory authority.

        Article 16 — Right to rectification
        The data subject shall have the right to obtain from the controller
        without undue delay the rectification of inaccurate personal data
        concerning him or her.

        Article 17 — Right to erasure ('right to be forgotten')
        1. The data subject shall have the right to obtain from the controller
           the erasure of personal data concerning him or her without undue
           delay and the controller shall have the obligation to erase personal
           data without undue delay where one of the following grounds applies:
           (a) the personal data are no longer necessary in relation to the
               purposes for which they were collected;
           (b) the data subject withdraws consent;
           (c) the data subject objects to the processing;
           (d) the personal data have been unlawfully processed;
           (e) the personal data have to be erased for compliance with a legal
               obligation.

        Article 18 — Right to restriction of processing
        1. The data subject shall have the right to obtain from the controller
           restriction of processing where one of the following applies:
           (a) the accuracy of the personal data is contested by the data
               subject;
           (b) the processing is unlawful and the data subject opposes the
               erasure of the personal data;
           (c) the controller no longer needs the personal data;
           (d) the data subject has objected to processing pending the
               verification whether the legitimate grounds of the controller
               override those of the data subject.

        Article 19 — Notification obligation
        The controller shall communicate any rectification or erasure of personal
        data or restriction of processing carried out in accordance with Article
        16, Article 17(1) and Article 18 to each recipient to whom the personal
        data have been disclosed.

        Article 20 — Right to data portability
        1. The data subject shall have the right to receive the personal data
           concerning him or her, which he or she has provided to a controller,
           in a structured, commonly used and machine-readable format.
        2. The data subject shall have the right to transmit those data to
           another controller without hindrance.

        Article 21 — Right to object
        1. The data subject shall have the right to object, on grounds relating
           to his or her particular situation, at any time to processing of
           personal data concerning him or her.
        2. Where personal data are processed for direct marketing purposes, the
           data subject shall have the right to object at any time to processing
           of personal data concerning him or her for such marketing.

        Article 22 — Automated individual decision-making, including profiling
        1. The data subject shall have the right not to be subject to a decision
           based solely on automated processing, including profiling, which
           produces legal effects concerning him or her or similarly
           significantly affects him or her.

        Article 23 — Restrictions
        Union or Member State law may restrict the scope of the obligations and
        rights provided for in Articles 12 to 22 and Article 34, as well as
        Article 5, in so far as its provisions correspond to the rights and
        obligations provided for in Articles 12 to 22.

        CHAPTER 4 — Controller and processor

        Article 24 — Responsibility of the controller
        1. Taking into account the nature, scope, context and purposes of
           processing as well as the risks of varying likelihood and severity
           for the rights and freedoms of natural persons, the controller shall
           implement appropriate technical and organisational measures to ensure
           and to be able to demonstrate that processing is performed in
           accordance with this Regulation.

        Article 25 — Data protection by design and by default
        1. Taking into account the state of the art, the cost of implementation
           and the nature, scope, context and purposes of processing, the
           controller shall implement appropriate technical and organisational
           measures designed to implement data-protection principles.
        2. The controller shall implement appropriate technical and
           organisational measures for ensuring that, by default, only personal
           data which are necessary for each specific purpose of the processing
           are processed.

        Article 26 — Joint controllers
        1. Where two or more controllers jointly determine the purposes and
           means of processing, they shall be joint controllers.

        Article 27 — Representatives of controllers or processors not established
                     in the Union
        1. Where Article 3(2) applies, the controller or the processor shall
           designate in writing a representative in the Union.

        Article 28 — Processor
        1. Where processing is to be carried out on behalf of a controller, the
           controller shall use only processors providing sufficient guarantees
           to implement appropriate technical and organisational measures.
        2. The processor shall not engage another processor without prior
           specific or general written authorisation of the controller.

        Article 29 — Processing under the authority of the controller or processor
        The processor and any person acting under the authority of the controller
        or of the processor, who has access to personal data, shall not process
        those data except on instructions from the controller.

        Article 30 — Records of processing activities
        1. Each controller and, where applicable, the controller's
           representative, shall maintain a record of processing activities
           under its responsibility.
        2. Each processor and, where applicable, the processor's representative
           shall maintain a record of all categories of processing activities
           carried out on behalf of a controller.

        Article 31 — Cooperation with the supervisory authority
        The controller and the processor and, where applicable, their
        representatives, shall cooperate, on request, with the supervisory
        authority in the performance of its tasks.

        Article 32 — Security of processing
        1. Taking into account the state of the art, the cost of implementation
           and the nature, scope, context and purposes of processing as well as
           the risk of varying likelihood and severity for the rights and
           freedoms of natural persons, the controller and the processor shall
           implement appropriate technical and organisational measures to ensure
           a level of security appropriate to the risk.

        Article 33 — Notification of a personal data breach to the supervisory
                     authority
        1. In the case of a personal data breach, the controller shall without
           undue delay and, where feasible, not later than 72 hours after
           having become aware of it, notify the personal data breach to the
           supervisory authority.

        Article 34 — Communication of a personal data breach to the data subject
        1. When the personal data breach is likely to result in a high risk to
           the rights and freedoms of natural persons, the controller shall
           communicate the personal data breach to the data subject without
           undue delay.

        Article 35 — Data protection impact assessment
        1. Where a type of processing in particular using new technologies, and
           taking into account the nature, scope, context and purposes of the
           processing, is likely to result in a high risk to the rights and
           freedoms of natural persons, the controller shall carry out an
           assessment of the impact of the envisaged processing operations on
           the protection of personal data.

        Article 36 — Prior consultation
        1. The controller shall consult the supervisory authority prior to
           processing where a data protection impact assessment under Article 35
           indicates that the processing would result in a high risk in the
           absence of measures taken by the controller to mitigate the risk.

        Article 37 — Designation of the data protection officer
        1. The controller and the processor shall designate a data protection
           officer in any case where:
           (a) the processing is carried out by a public authority;
           (b) the core activities of the controller or the processor consist
               of processing operations which require regular and systematic
               monitoring of data subjects on a large scale;
           (c) the core activities of the controller or the processor consist
               of processing on a large scale of special categories of data.

        Article 38 — Position of the data protection officer
        1. The controller and the processor shall ensure that the data
           protection officer is involved, properly and in a timely manner, in
           all issues which relate to the protection of personal data.
        2. The controller and processor shall support the data protection
           officer by providing resources necessary to carry out their tasks.

        Article 39 — Tasks of the data protection officer
        1. The data protection officer shall have at least the following tasks:
           (a) to inform and advise the controller or the processor;
           (b) to monitor compliance with this Regulation;
           (c) to provide advice on the data protection impact assessment;
           (d) to cooperate with the supervisory authority.

        Article 40 — Codes of conduct
        1. The Member States, the supervisory authorities, the Board and the
           Commission shall encourage the drawing up of codes of conduct.

        Article 41 — Monitoring of approved codes of conduct
        1. Without prejudice to the tasks and powers of the competent
           supervisory authority, the monitoring of compliance with a code of
           conduct may be carried out by a body which has an appropriate level
           of expertise.

        Article 42 — Certification
        1. The Member States, the supervisory authorities, the Board and the
           Commission shall encourage the establishment of data protection
           certification mechanisms.

        Article 43 — Certification bodies
        1. Certification bodies accredited by the supervisory authority shall
           issue certification after having informed the controller or the
           processor.

        CHAPTER 5 — Transfers of personal data to third countries or
                     international organisations

        Article 44 — General principle for transfers
        Any transfer of personal data which are undergoing processing or are
        intended for processing after transfer to a third country or to an
        international organisation shall take place only if, subject to the
        other provisions of this Regulation, the conditions laid down in this
        Chapter are complied with.

        Article 45 — Transfers on the basis of an adequacy decision
        1. A transfer of personal data to a third country or an international
           organisation may take place where the Commission has decided that
           the third country, a territory or one or more specified sectors
           within that third country, or the international organisation in
           question ensures an adequate level of protection.

        Article 46 — Transfers subject to appropriate safeguards
        1. In the absence of a decision pursuant to Article 45(3), a controller
           or processor may transfer personal data to a third country or an
           international organisation only if the controller or processor has
           provided appropriate safeguards, and on condition that enforceable
           data subject rights and effective legal remedies for data subjects
           are available.

        Article 47 — Binding corporate rules
        1. The competent supervisory authority shall approve binding corporate
           rules in accordance with the consistency mechanism set out in
           Article 63, provided that they:
           (a) are legally binding;
           (b) expressly confer enforceable rights on data subjects.

        Article 48 — Transfers or disclosures not authorised by Union law
        Any judgment of a court or tribunal and any decision of an
        administrative authority of a third country requiring a controller or
        processor to transfer or disclose personal data may only be recognised
        or enforceable in any manner if based on an international agreement.

        Article 49 — Derogations for specific situations
        1. In the absence of an adequacy decision pursuant to Article 45(3), or
           of appropriate safeguards pursuant to Article 46, a transfer or a
           set of transfers of personal data to a third country shall take place
           only on one of the following conditions:
           (a) the data subject has explicitly consented;
           (b) the transfer is necessary for the performance of a contract;
           (c) the transfer is necessary for important reasons of public
               interest;
           (d) the transfer is necessary for the establishment, exercise or
               defence of legal claims;
           (e) the transfer is necessary in order to protect the vital
               interests of the data subject.
    """)


def _gdpr_it() -> str:
    """GDPR — Articles 1-20 key provisions (Italian translation)."""
    return textwrap.dedent("""\
        REGOLAMENTO (UE) 2016/679 DEL PARLAMENTO EUROPEO E DEL CONSIGLIO
        del 27 aprile 2016
        relativo alla protezione delle persone fisiche con riguardo al
        trattamento dei dati personali, nonché alla libera circolazione di
        tali dati (Regolamento generale sulla protezione dei dati)

        CAPITOLO 1 — Disposizioni generali

        Articolo 1 — Oggetto e obiettivi
        1. Il presente regolamento stabilisce le norme relative alla protezione
           delle persone fisiche con riguardo al trattamento dei dati personali,
           nonché le norme relative alla libera circolazione di tali dati.
        2. Il presente regolamento protegge i diritti e le libertà fondamentali
           delle persone fisiche, in particolare il diritto alla protezione dei
           dati personali.
        3. La libera circolazione dei dati personali nell'Unione non può essere
           limitata né vietata per motivi attinenti alla protezione delle persone
           fisiche con riguardo al trattamento dei dati personali.

        Articolo 2 — Ambito di applicazione materiale
        1. Il presente regolamento si applica al trattamento dei dati personali
           interamente o parzialmente con mezzi automatizzati e al trattamento
           con mezzi non automatizzati dei dati personali contenuti in un
           archivio o destinati a figurarvi.
        2. Il presente regolamento non si applica al trattamento dei dati
           personali:
           a) effettuato per attività che esulano dall'ambito di applicazione
              del diritto dell'Unione;
           b) effettuato dagli Stati membri nell'esercizio di attività che
              rientrano nell'ambito di applicazione del titolo V, capo 2, TUE;
           c) effettuato da una persona fisica per attività puramente personali
              o domestiche;
           d) effettuato dalle autorità competenti a fini di prevenzione,
              indagine, accertamento o perseguimento di reati.

        Articolo 3 — Ambito di applicazione territoriale
        1. Il presente regolamento si applica al trattamento dei dati personali
           effettuato nell'ambito delle attività di uno stabilimento del
           titolare del trattamento o del responsabile del trattamento
           nell'Unione, indipendentemente dal fatto che il trattamento sia
           effettuato o meno nell'Unione.
        2. Il presente regolamento si applica al trattamento dei dati personali
           di interessati che si trovano nell'Unione, effettuato da un titolare
           del trattamento o responsabile del trattamento che non è stabilito
           nell'Unione, quando le attività di trattamento riguardano:
           a) l'offerta di beni o la prestazione di servizi ai suddetti
              interessati nell'Unione;
           b) il monitoraggio del loro comportamento nella misura in cui tale
              comportamento ha luogo all'interno dell'Unione.

        Articolo 4 — Definizioni
        Ai fini del presente regolamento si intende per:
        1) «dato personale»: qualsiasi informazione riguardante una persona
           fisica identificata o identificabile («interessato»); si considera
           identificabile la persona fisica che può essere identificata,
           direttamente o indirettamente, con particolare riferimento a un
           identificativo come il nome, un numero di identificazione, dati
           relativi all'ubicazione, un identificativo online o a uno o più
           elementi caratteristici della sua identità fisica, fisiologica,
           genetica, psichica, economica, culturale o sociale;
        2) «trattamento»: qualsiasi operazione o insieme di operazioni,
           compiute con o senza l'ausilio di processi automatizzati e applicate
           a dati personali o insiemi di dati personali, come la raccolta, la
           registrazione, l'organizzazione, la strutturazione, la conservazione,
           l'adeguamento o la modifica, l'estrazione, la consultazione,
           l'uso, la comunicazione mediante trasmissione, diffusione o
           qualsiasi altra forma di messa a disposizione, il raffronto o
           l'interconnessione, la limitazione, la cancellazione o la
           distruzione;
        3) «limitazione del trattamento»: il contrassegno dei dati personali
           conservati con la finalità di limitarne il trattamento in futuro;
        4) «profilazione»: qualsiasi forma di trattamento automatizzato di
           dati personali consistente nell'utilizzo di tali dati personali
           per valutare determinati aspetti personali relativi a una persona
           fisica, in particolare per analizzare o prevedere aspetti
           riguardanti il rendimento professionale, la situazione economica,
           la salute, le preferenze personali, gli interessi,
           l'affidabilità, il comportamento, l'ubicazione o gli spostamenti
           di detta persona fisica;
        5) «pseudonimizzazione»: il trattamento dei dati personali in modo
           che i dati personali non possano più essere attribuiti a un
           interessato specifico senza l'utilizzo di informazioni aggiuntive,
           a condizione che tali informazioni aggiuntive siano conservate
           separatamente e soggette a misure tecniche e organizzative atte
           a garantire che tali dati personali non siano attribuiti a una
           persona fisica identificata o identificabile;
        6) «archivio»: qualsiasi insieme strutturato di dati personali
           accessibili secondo criteri determinati, indipendentemente dal
           fatto che tale insieme sia centralizzato, decentralizzato o
           ripartito in modo funzionale o geografico;
        7) «titolare del trattamento»: la persona fisica o giuridica,
           l'autorità pubblica, il servizio o altro organismo che, singolarmente
           o insieme ad altri, determina le finalità e i mezzi del trattamento
           di dati personali;
        8) «responsabile del trattamento»: la persona fisica o giuridica,
           l'autorità pubblica, il servizio o altro organismo che tratta dati
           personali per conto del titolare del trattamento;
        9) «destinatario»: la persona fisica o giuridica, l'autorità pubblica,
           il servizio o altro organismo che riceve comunicazione di dati
           personali;
        10) «terzo»: la persona fisica o giuridica, l'autorità pubblica,
            il servizio o altro organismo che non sia l'interessato, il
            titolare del trattamento, il responsabile del trattamento e le
            persone autorizzate al trattamento dei dati personali sotto
            l'autorità diretta del titolare o del responsabile;
        11) «consenso dell'interessato»: qualsiasi manifestazione di volontà
            libera, specifica, informata e inequivocabile dell'interessato,
            con la quale lo stesso accetta, mediante dichiarazione o azione
            positiva inequivocabile, che i dati personali che lo riguardano
            siano oggetto di trattamento.

        CAPITOLO 2 — Principi

        Articolo 5 — Principi applicabili al trattamento di dati personali
        1. I dati personali sono:
           a) trattati in modo lecito, corretto e trasparente nei confronti
              dell'interessato («liceità, correttezza e trasparenza»);
           b) raccolti per finalità determinate, esplicite e legittime, e
              ulteriormente trattati in modo che non sia incompatibile con
              tali finalità («limitazione delle finalità»);
           c) adeguati, pertinenti e limitati a quanto necessario rispetto
              alle finalità per cui sono trattati («minimizzazione dei dati»);
           d) esatti e, se necessario, aggiornati («esattezza»);
           e) conservati in una forma che consenta l'identificazione degli
              interessati per un arco di tempo non superiore al conseguimento
              delle finalità («limitazione della conservazione»);
           f) trattati in modo da garantire un'adeguata sicurezza dei dati
              personali («integrità e riservatezza»).

        Articolo 6 — Liceità del trattamento
        1. Il trattamento è lecito solo se e nella misura in cui si applica
           almeno una delle seguenti condizioni:
           a) l'interessato ha prestato il consenso al trattamento dei propri
              dati personali per una o più finalità specifiche;
           b) il trattamento è necessario all'esecuzione di un contratto di
              cui l'interessato è parte;
           c) il trattamento è necessario per adempiere un obbligo legale al
              quale è soggetto il titolare del trattamento;
           d) il trattamento è necessario per la salvaguardia degli interessi
              vitali dell'interessato o di un'altra persona fisica;
           e) il trattamento è necessario per l'esecuzione di un compito di
              interesse pubblico;
           f) il trattamento è necessario per il perseguimento del legittimo
              interesse del titolare del trattamento o di terzi.

        Articolo 7 — Condizioni per il consenso
        1. Qualora il trattamento sia basato sul consenso, il titolare del
           trattamento deve essere in grado di dimostrare che l'interessato
           ha prestato il consenso al trattamento dei propri dati personali.
        2. Se il consenso dell'interessato è prestato nel contesto di una
           dichiarazione scritta che riguarda anche altre questioni, la richiesta
           di consenso deve essere presentata in modo chiaramente distinguibile
           dalle altre questioni.
        3. L'interessato ha il diritto di revocare il consenso in qualsiasi
           momento.

        Articolo 8 — Condizioni applicabili al consenso dei minori
        1. Qualora si applichi l'articolo 6, paragrafo 1, lettera a), in
           relazione all'offerta diretta di servizi della società
           dell'informazione ai minori, il trattamento è lecito solo se il
           minore ha almeno 16 anni.
        2. Il titolare del trattamento si adopera ragionevolmente per
           verificare che il consenso sia prestato dal titolare della
           responsabilità genitoriale.

        Articolo 9 — Trattamento di categorie particolari di dati personali
        1. È vietato trattare dati personali che rivelino l'origine razziale
           o etnica, le opinioni politiche, le convinzioni religiose o
           filosofiche, o l'appartenenza sindacale, nonché trattare dati
           genetici, dati biometrici intesi a identificare in modo univoco
           una persona fisica, dati relativi alla salute o alla vita sessuale
           o all'orientamento sessuale della persona.
        2. Il paragrafo 1 non si applica se si verifica uno dei seguenti casi:
           a) l'interessato ha prestato il consenso esplicito;
           b) il trattamento è necessario per assolvere obblighi ed esercitare
              specifici diritti in materia di diritto del lavoro;
           c) il trattamento è necessario per tutelare un interesse vitale
              dell'interessato o di un'altra persona fisica;
           d) il trattamento è effettuato, nell'ambito delle sue legittime
              attività e con adeguate garanzie, da una fondazione, associazione
              o altro organismo senza scopo di lucro;
           e) i dati sono stati manifestamente resi pubblici dall'interessato;
           f) il trattamento è necessario per accertare, esercitare o difendere
              un diritto in sede giudiziaria;
           g) il trattamento è necessario per motivi di interesse pubblico
              rilevante;
           h) il trattamento è necessario per finalità di medicina preventiva,
              diagnosi medica, assistenza o terapia sanitaria;
           i) il trattamento è necessario per motivi di interesse pubblico nel
              settore della sanità pubblica;
           j) il trattamento è necessario a fini di archiviazione nel pubblico
              interesse, di ricerca scientifica o storica o a fini statistici.

        Articolo 10 — Trattamento dei dati personali relativi a condanne penali
        Il trattamento dei dati personali relativi a condanne penali e a reati
        o a connesse misure di sicurezza può avvenire soltanto sotto il controllo
        dell'autorità pubblica.

        Articolo 11 — Trattamento che non richiede l'identificazione
        1. Se le finalità per cui un titolare del trattamento tratta dati
           personali non richiedono o non richiedono più l'identificazione
           dell'interessato, il titolare non è obbligato a conservare o
           acquisire ulteriori informazioni al fine di identificare
           l'interessato.

        CAPITOLO 3 — Diritti dell'interessato

        Articolo 12 — Informazione trasparente, comunicazione e modalità
        1. Il titolare del trattamento adotta misure appropriate per fornire
           all'interessato tutte le informazioni di cui agli articoli 13 e 14
           e le comunicazioni di cui agli articoli 15 a 22 e 34 in forma
           concisa, trasparente, intelligibile e facilmente accessibile, con
           un linguaggio semplice e chiaro.

        Articolo 13 — Informazioni da fornire nel caso di raccolta dei dati
                      presso l'interessato
        1. In caso di raccolta presso l'interessato di dati che lo riguardano,
           il titolare del trattamento fornisce all'interessato, nel momento in
           cui i dati personali sono ottenuti, le seguenti informazioni:
           a) l'identità e i dati di contatto del titolare del trattamento;
           b) i dati di contatto del responsabile della protezione dei dati;
           c) le finalità del trattamento;
           d) la base giuridica del trattamento;
           e) gli eventuali destinatari dei dati personali.

        Articolo 14 — Informazioni da fornire qualora i dati non siano stati
                      ottenuti presso l'interessato
        1. Qualora i dati personali non siano stati ottenuti presso
           l'interessato, il titolare del trattamento fornisce all'interessato
           le informazioni di cui all'articolo 13.

        Articolo 15 — Diritto di accesso dell'interessato
        1. L'interessato ha il diritto di ottenere dal titolare del trattamento
           la conferma che sia o meno in corso un trattamento di dati personali
           che lo riguardano e in tal caso, di ottenere l'accesso ai dati
           personali e alle seguenti informazioni:
           a) le finalità del trattamento;
           b) le categorie di dati personali in questione;
           c) i destinatari o le categorie di destinatari;
           d) il periodo di conservazione previsto;
           e) il diritto di chiedere la rettifica o la cancellazione;
           f) il diritto di proporre reclamo a un'autorità di controllo.

        Articolo 16 — Diritto di rettifica
        L'interessato ha il diritto di ottenere dal titolare del trattamento la
        rettifica dei dati personali inesatti che lo riguardano senza ingiustificato
        ritardo.

        Articolo 17 — Diritto alla cancellazione («diritto all'oblio»)
        1. L'interessato ha il diritto di ottenere dal titolare del trattamento
           la cancellazione dei dati personali che lo riguardano senza
           ingiustificato ritardo e il titolare del trattamento ha l'obbligo di
           cancellare i dati personali senza ingiustificato ritardo se si
           verifica uno dei motivi seguenti:
           a) i dati personali non sono più necessari rispetto alle finalità;
           b) l'interessato revoca il consenso;
           c) l'interessato si oppone al trattamento;
           d) i dati personali sono stati trattati illecitamente;
           e) i dati personali devono essere cancellati per adempiere un
              obbligo legale.

        Articolo 18 — Diritto di limitazione di trattamento
        1. L'interessato ha il diritto di ottenere dal titolare del trattamento
           la limitazione del trattamento quando ricorre una delle seguenti
           ipotesi:
           a) l'interessato contesta l'esattezza dei dati personali;
           b) il trattamento è illecito e l'interessato si oppone alla
              cancellazione dei dati personali;
           c) il titolare del trattamento non ha più bisogno dei dati personali;
           d) l'interessato si è opposto al trattamento.

        Articolo 19 — Obbligo di notifica
        Il titolare del trattamento comunica a ciascuno dei destinatari la
        rettifica o la cancellazione dei dati personali o la limitazione del
        trattamento.

        Articolo 20 — Diritto alla portabilità dei dati
        1. L'interessato ha il diritto di ricevere in un formato strutturato,
           di uso comune e leggibile da dispositivo automatico i dati personali
           che lo riguardano forniti a un titolare del trattamento.
        2. L'interessato ha il diritto di trasmettere tali dati a un altro
           titolare del trattamento senza impedimenti.
    """)


def _eu_ai_act_en() -> str:
    """EU AI Act — Titles I-IV (key articles, English)."""
    return textwrap.dedent("""\
        REGULATION (EU) 2024/1689 OF THE EUROPEAN PARLIAMENT AND OF THE COUNCIL
        of 13 June 2024
        laying down harmonised rules on artificial intelligence
        (Artificial Intelligence Act)

        TITLE I — GENERAL PROVISIONS

        Article 1 — Subject matter
        1. This Regulation lays down:
           (a) harmonised rules for the placing on the market, the putting into
               service, and the use of artificial intelligence systems in the
               Union;
           (b) prohibitions of certain artificial intelligence practices;
           (c) specific requirements for high-risk artificial intelligence
               systems and obligations for operators of such systems;
           (d) harmonised transparency rules for certain artificial
               intelligence systems;
           (e) harmonised rules for the placing on the market of
               general-purpose artificial intelligence models;
           (f) rules on market monitoring, market surveillance, governance and
               enforcement;
           (g) measures to support innovation, with a particular focus on SMEs.

        Article 2 — Scope
        1. This Regulation applies to:
           (a) providers placing on the market or putting into service AI systems
               in the Union, irrespective of whether those providers are
               established or located within the Union or in a third country;
           (b) deployers of AI systems that have their place of establishment or
               are located within the Union;
           (c) providers and deployers of AI systems that are established or
               located in a third country, where the output produced by the AI
               system is used in the Union;
           (d) importers and distributors of AI systems;
           (e) product manufacturers placing on the market or putting into
               service an AI system together with their product;
           (f) authorised representatives of providers;
           (g) affected persons located in the Union.

        Article 3 — Definitions
        For the purposes of this Regulation, the following definitions apply:
        (1) 'artificial intelligence system' (AI system) means a machine-based
            system that is designed to operate with varying levels of autonomy
            and that may exhibit adaptiveness after deployment and that, for
            explicit or implicit objectives, infers, from the input it receives,
            how to generate outputs such as predictions, content, recommendations,
            or decisions that can influence physical or virtual environments;
        (2) 'risk' means the combination of the probability of an occurrence of
            a hazard and the severity of that hazard;
        (3) 'provider' means a natural or legal person, public authority, agency
            or other body that develops an AI system or a general-purpose AI
            model, or that has an AI system or a general-purpose AI model
            developed, and places it on the market or puts the AI system into
            service under its own name or trademark;
        (4) 'deployer' means a natural or legal person, public authority, agency
            or other body using an AI system under its authority;
        (5) 'authorised representative' means a natural or legal person located
            or established in the Union who has received and accepted a written
            mandate from a provider to act on its behalf;
        (6) 'importer' means a natural or legal person located in the Union that
            places on the market an AI system that bears the name or trademark
            of a natural or legal person established in a third country;
        (7) 'distributor' means a natural or legal person in the supply chain,
            other than the provider or the importer, that makes an AI system
            available on the Union market;
        (8) 'operator' means a provider, a deployer, an authorised
            representative, an importer or a distributor;
        (9) 'putting into service' means the supply of an AI system for first
            use directly to the deployer;
        (10) 'placing on the market' means the first making available of an AI
             system on the Union market;
        (11) 'intended purpose' means the use for which an AI system is intended
             by the provider;
        (12) 'reasonably foreseeable misuse' means the use of an AI system in a
             way that is not in accordance with its intended purpose;
        (13) 'safety component' means a component of a product or of an AI
             system which fulfils a safety function;
        (14) 'high-risk AI system' means an AI system that is classified as
             high-risk pursuant to Article 6;
        (15) 'training data' means data used for training an AI system;
        (16) 'validation data' means data used for providing an evaluation of
             the trained AI system;
        (17) 'test data' means data used for the final evaluation of the AI
             system;
        (18) 'input data' means data provided to or directly acquired by an AI
             system on the basis of which the system produces an output;
        (19) 'biometric data' means personal data resulting from specific
             technical processing relating to the physical, physiological or
             behavioural characteristics of a natural person;
        (20) 'emotion recognition system' means an AI system for the purpose of
             identifying or inferring emotions or intentions of natural persons
             on the basis of their biometric data;
        (21) 'biometric categorisation system' means an AI system for the
             purpose of assigning natural persons to specific categories;
        (22) 'remote biometric identification system' means an AI system for the
             purpose of identifying natural persons at a distance;
        (23) 'general-purpose AI model' means an AI model, including where such
             an AI model is trained with a large amount of data using
             self-supervision at scale, that displays significant generality and
             is capable of competently performing a wide range of distinct tasks;
        (24) 'general-purpose AI system' means an AI system which is based on a
             general-purpose AI model and which has the capability to serve a
             variety of purposes;
        (25) 'substantial modification' means a change to an AI system following
             its placing on the market or putting into service;
        (26) 'recall of an AI system' means any measure aimed at achieving the
             return of an AI system that has been made available to the deployer;
        (27) 'withdrawal of an AI system' means any measure aimed at preventing
             an AI system in the supply chain from being made available;
        (28) 'performance' means the ability of an AI system to achieve its
             intended purpose;
        (29) 'accuracy' means the ability of an AI system to correctly identify
             relevant elements in a given context;
        (30) 'robustness' means the ability of an AI system to function reliably
             and accurately under different conditions;
        (31) 'cybersecurity' means the protection of AI systems against
             unauthorised access, modification or disclosure of data.

        TITLE II — PROHIBITED ARTIFICIAL INTELLIGENCE PRACTICES

        Article 5 — Prohibited AI practices
        1. The following AI practices shall be prohibited:
           (a) the placing on the market, the putting into service or the use
               of an AI system that deploys subliminal techniques beyond a
               person's consciousness;
           (b) the placing on the market, the putting into service or the use
               of an AI system that exploits any of the vulnerabilities of a
               natural person;
           (c) the placing on the market, the putting into service or the use
               of an AI system for the evaluation or classification of natural
               persons based on their social behaviour;
           (d) the use of an AI system for making risk assessments of natural
               persons in order to assess or predict the risk of a natural
               person committing a criminal offence;
           (e) the placing on the market, the putting into service or the use
               of AI systems that create or expand facial recognition databases
               through the untargeted scraping of facial images from the
               internet or CCTV footage;
           (f) the use of an AI system to infer emotions of a natural person in
               the areas of workplace and education institutions;
           (g) the use of an AI system for the biometric categorisation of
               natural persons to deduce or infer their race, political
               opinions, trade union membership, religious or philosophical
               beliefs, sex life or sexual orientation;
           (h) the use of an AI system for real-time remote biometric
               identification in publicly accessible spaces for the purposes
               of law enforcement.

        TITLE III — HIGH-RISK AI SYSTEMS

        Chapter 1: Classification of AI systems as high-risk

        Article 6 — Classification rules for high-risk AI systems
        1. An AI system referred to in paragraph 2 shall be considered high-risk
           if it is intended to be used as a safety component of a product.
        2. An AI system shall be considered high-risk if it is intended to be
           used as a safety component of a product covered by the Union
           harmonisation legislation listed in Section A of Annex I.

        Article 7 — Amendments to the list of high-risk AI systems
        1. The Commission is empowered to adopt delegated acts to amend the list
           of high-risk AI systems in Annex III.

        Chapter 2: Requirements for high-risk AI systems

        Article 8 — Compliance with the requirements
        1. High-risk AI systems shall comply with the requirements established
           in this Section.

        Article 9 — Risk management system
        1. A risk management system shall be established, implemented,
           documented and maintained in relation to high-risk AI systems.
        2. The risk management system shall be iterative and run throughout the
           entire lifecycle of a high-risk AI system.

        Article 10 — Data and data governance
        1. High-risk AI systems which make use of techniques involving the
           training of AI models with data shall be developed on the basis of
           training, validation and testing data sets that meet the quality
           criteria referred to in paragraphs 2 to 5.
        2. Training, validation and testing data sets shall be subject to
           appropriate data governance and management practices.

        Article 11 — Technical documentation
        1. The technical documentation of a high-risk AI system shall be drawn
           up before that system is placed on the market or put into service
           and shall be kept up-to date.

        Article 12 — Record-keeping
        1. High-risk AI systems shall be designed and developed with
           capabilities enabling the automatic recording of events (logs).

        Article 13 — Transparency and provision of information to deployers
        1. High-risk AI systems shall be designed and developed in such a way
           that they are sufficiently transparent to enable deployers to
           interpret the system's output and use it appropriately.

        Article 14 — Human oversight
        1. High-risk AI systems shall be designed and developed in such a way
           that they can be effectively overseen by natural persons.

        Article 15 — Accuracy, robustness and cybersecurity
        1. High-risk AI systems shall be designed and developed in such a way
           that they achieve an appropriate level of accuracy, robustness and
           cybersecurity.

        Chapter 3: Obligations of providers and deployers

        Article 16 — Obligations of providers of high-risk AI systems
        1. Providers of high-risk AI systems shall:
           (a) ensure that their high-risk AI systems comply with the
               requirements established in Chapter 2;
           (b) establish a quality management system;
           (c) keep the documentation;
           (d) ensure that the AI system undergoes the relevant conformity
               assessment;
           (e) comply with registration obligations.

        Article 17 — Quality management system
        1. Providers of high-risk AI systems shall put a quality management
           system in place.

        Article 18 — Documentation keeping
        1. Providers of high-risk AI systems shall keep the documentation
           referred to in Article 11 for a period ending 10 years after the AI
           system has been placed on the market or put into service.

        Article 19 — Automatically generated logs
        1. Providers of high-risk AI systems shall keep the logs automatically
           generated under their control for a period of at least six months.

        Article 20 — Corrective actions
        1. Providers of high-risk AI systems which consider or have reason to
           consider that an AI system which they have placed on the market is
           not in conformity with this Regulation shall immediately take the
           corrective actions necessary.

        Article 21 — Duty of information
        1. Where a high-risk AI system presents a risk, providers shall
           immediately inform the market surveillance authorities.

        Article 22 — Obligations of deployers of high-risk AI systems
        1. Deployers of high-risk AI systems shall take appropriate technical
           and organisational measures to ensure they use such systems in
           accordance with the instructions of use.
        2. Deployers shall assign human oversight to natural persons who have
           the necessary competence, training and authority.

        TITLE IV — TRANSPARENCY OBLIGATIONS FOR PROVIDERS AND DEPLOYERS OF
                   CERTAIN AI SYSTEMS

        Article 50 — Transparency obligations for providers and deployers of
                     certain AI systems
        1. Providers shall ensure that AI systems intended to interact directly
           with natural persons are designed and developed in such a way that
           the natural persons concerned are informed that they are interacting
           with an AI system.
        2. Providers of AI systems, including general-purpose AI systems,
           generating synthetic audio, image, video or text content, shall
           ensure the outputs of the AI system are marked in a machine-readable
           format and detectable as artificially generated or manipulated.
        3. Deployers of an AI system that generates or manipulates image, audio
           or video content constituting a deep fake, shall disclose that the
           content has been artificially generated or manipulated.
        4. Deployers of an AI system that generates or manipulates text which is
           published with the purpose of informing the public on matters of
           public interest shall disclose that the text has been artificially
           generated or manipulated.

        TITLE V — GENERAL-PURPOSE AI MODELS

        Article 51 — Obligations for providers of general-purpose AI models
        1. Providers of general-purpose AI models shall:
           (a) draw up and maintain the technical documentation of the model;
           (b) provide information and documentation to providers of AI systems;
           (c) establish a policy to comply with Union copyright law;
           (d) publish a sufficiently detailed summary of the training content.
    """)


def _sentenza_tf() -> str:
    """Fictional Swiss Federal Tribunal judgment (Italian)."""
    return textwrap.dedent("""\
        TRIBUNALE FEDERALE
        Sentenza 4A_123/2024 del 15 marzo 2024

        I. Composizione

        Giudice federale: dott. Hans Müller, Presidente
        Giudici federali: dott. Maria Rossi, dott. Jean-Pierre Dupont,
                          dott. Anna Schmidt, dott. Luigi Bianchi
        Cancelliere: dott. Peter Keller

        II. Parti

        Ricorrente: Tizio SA, con sede in Lugano, rappresentato dall'avv.
                     Dr. Carlo Mancini, Studio Legale Mancini, Lugano
        Controparte: Caia SAGL, con sede in Zurigo, rappresentata dall'avv.
                     Dr. Friedrich Weber, Kanzlei Weber & Partner, Zurigo

        III. Oggetto

        Il Tribunale federale è adito in materia di diritto delle obbligazioni
        (art. 319 ss. CO) in relazione a un contratto di lavoro e alla clausola
        di non concorrenza (art. 322 CO).

        IV. Fatti di causa

        A. Con contratto di lavoro del 1° gennaio 2020, Tizio SA (di seguito:
        "il datore di lavoro") ha assunto la signora Sempronia Tizia come
        responsabile del reparto vendite con un salario annuo di CHF 120'000.--.

        B. L'art. 8 del contratto di lavoro contiene la seguente clausola di
        non concorrenza:

        "La lavoratrice si impegna a non esercitare alcuna attività concorrenziale
        nei confronti della datrice di lavoro per un periodo di 24 mesi dalla
        cessazione del rapporto di lavoro, su tutto il territorio svizzero.
        In caso di violazione, la lavoratrice è tenuta a pagare una penale
        di CHF 50'000.--."

        C. Il 30 giugno 2023, la signora Sempronia Tizia ha rassegnato le
        dimissioni con effetto immediato e ha iniziato a lavorare per Caia
        SAGL, società concorrente, dal 1° luglio 2023.

        D. Tizio SA ha agito giudiziariamente dinanzi al Tribunale cantonale
        di Zurigo, chiedendo il pagamento della penale contrattuale di
        CHF 50'000.-- e l'ingiunzione di non concorrenza.

        E. Il Tribunale cantonale di Zurigo, con sentenza del 15 novembre 2023,
        ha accolto parzialmente la domanda, riducendo la penale a CHF 25'000.--
        e limitando il divieto di concorrenza a 12 mesi.

        F. Tizio SA ha impugnato la sentenza dinanzi al Tribunale federale,
        chiedendo la riforma della sentenza nel senso di accogliere integralmente
        le domande.

        V. Diritto

        A. Sulla competenza del Tribunale federale

        1. La competenza del Tribunale federale è fondata sull'art. 74 cpv. 1
           lett. a LTF in materia di cause civili di diritto delle obbligazioni.

        2. Il valore litigioso supera CHF 30'000.--; pertanto, il ricorso è
           ammissibile.

        B. Sulla clausola di non concorrenza (art. 322 CO)

        3. Secondo l'art. 322 cpv. 1 CO, il lavoratore può obbligarsi per
           iscritto a non esercitare, dopo la cessazione del rapporto di
           lavoro, alcuna attività concorrenziale.

        4. L'art. 322 cpv. 2 CO richiede che la clausola sia limitata
           per iscritto, per luogo, tempo e oggetto, nella misura in cui
           l'uso delle cognizioni acquisite presso il datore di lavoro possa
           pregiudicare sensibilmente quest'ultimo.

        5. L'art. 322 cpv. 3 CO prevede che la durata del divieto non può
           superare tre anni. Una durata più breve è da stabilire se le
           circostanze lo richiedono.

        6. Nel caso concreto, la clausola prevede un divieto di 24 mesi su
           tutto il territorio svizzero. Il Tribunale federale ritiene che:

           a) La durata di 24 mesi è eccessiva rispetto alla posizione della
              lavoratrice (responsabile reparto vendite) e alla sua anzianità
              di servizio (3 anni e mezzo). Una durata di 12 mesi appare
              proporzionata.

           b) L'estensione territoriale a tutta la Svizzera è sproporzionata
              rispetto all'area di attività effettiva della lavoratrice, che
              operava principalmente nel Canton Ticino e in parte nel Canton
              Grigioni. Il divieto va limitato ai cantoni Ticino e Grigioni.

           c) La penale di CHF 50'000.-- è eccessiva rispetto al salario annuo
              di CHF 120'000.--. Secondo la giurisprudenza (DTF 132 III 115),
              la penale non deve superare il salario di un anno. La penale va
              ridotta a CHF 25'000.--.

        7. Tizio SA sostiene che la clausola sia necessaria per proteggere la
           propria clientela. Tuttavia, come ritenuto dal Tribunale cantonale,
           il rapporto di fiducia con la clientela non è di tale intensità da
           giustificare un divieto così ampio.

        8. Caia SAGL sostiene che la clausola sia nulla per intero in quanto
           sproporzionata. Il Tribunale federale rigetta tale argomento: la
           clausola non è nulla, ma va ridotta in conformità con l'art. 322
           cpv. 2 CO.

        C. Sulla penale contrattuale

        9. L'art. 160 cpv. 1 CO prevede che la penale pattuita possa essere
           ridotta dal giudice se è manifestamente eccessiva.

        10. Nel caso concreto, la penale di CHF 50'000.-- equivale a circa
            5 mesi di salario. Il Tribunale federale conferma la riduzione a
            CHF 25'000.--, tenendo conto:
            - della posizione della lavoratrice;
            - dell'anzianità di servizio;
            - del salario percepito;
            - della gravità della violazione.

        VI. Dispositivo

        1. Il ricorso è respinto nella misura della sua ammissibilità.

        2. La sentenza del Tribunale cantonale di Zurigo del 15 novembre 2023
           è confermata.

        3. Le spese giudiziarie, fissate in CHF 3'000.--, sono poste a carico
           di Tizio SA.

        4. Tizio SA verserà a Caia SAGL un'indennità per ripetibili di
           CHF 4'000.--.

        5. Comunicazione alle parti e al Tribunale cantonale di Zurigo.

        Losanna, 15 marzo 2024

        In nome del Tribunale federale svizzero
        Il Presidente: dott. Hans Müller
        Il Cancelliere: dott. Peter Keller

        ----
        Nota: questa è una sentenza fittizia creata a scopo di test.
        Non corrisponde a nessuna sentenza reale del Tribunale federale.
    """)


def _contratto_lavoro() -> str:
    """Fictional employment contract (Italian)."""
    return textwrap.dedent("""\
        CONTRATTO DI LAVORO

        Tra

        Datore di lavoro:
        TechVision SA
        Via Lugano 15, 6900 Lugano
        Partita IVA: CHE-123.456.789
        Rappresentata dal Dr. Marco Bianchi, Amministratore Delegato

        e

        Lavoratore:
        Dr. Alessandro Rossi
        Nato il 15 marzo 1990
        Residente in Via Lugano 22, 6900 Lugano
        Carta d'identità: TI-1234567

        Articolo 1 — Oggetto del contratto
        1.1 Il presente contratto disciplina il rapporto di lavoro subordinato
            tra TechVision SA (di seguito "il Datore") e il Dr. Alessandro
            Rossi (di seguito "il Lavoratore").
        1.2 Il Lavoratore è assunto come Ingegnere del Software Senior nel
            reparto Sviluppo Prodotti.

        Articolo 2 — Durata del contratto
        2.1 Il contratto è stipulato a tempo indeterminato.
        2.2 Il rapporto di lavoro ha inizio il 1° aprile 2024.
        2.3 Il periodo di prova è di tre mesi, durante il quale ciascuna delle
            parti può recedere dal contratto con preavviso di sette giorni
            (art. 335b cpv. 1 CO).

        Articolo 3 — Mansioni del lavoratore
        3.1 Il Lavoratore svolge le seguenti mansioni:
            a) Progettazione e sviluppo di software;
            b) Supervisione del team di sviluppo;
            c) Partecipazione a riunioni tecniche;
            d) Redazione di documentazione tecnica;
            e) Altre mansioni compatibili con la qualifica.
        3.2 Il Lavoratore si impegna a svolgere le mansioni con diligenza e
            nel rispetto delle istruzioni del Datore (art. 321 CO).

        Articolo 4 — Orario di lavoro
        4.1 L'orario di lavoro settimanale è di 42 ore, distribuite dal lunedì
            al venerdì, con le seguenti fasce orarie:
            - Mattina: 08:30 - 12:00
            - Pomeriggio: 13:30 - 17:30
        4.2 Il Lavoratore ha diritto a una pausa pranzo di 60 minuti.
        4.3 Il lavoro straordinario è compensato con tempo libero o, su
            richiesta del Lavoratore, con il salario maggiorato del 25%
            (art. 321c cpv. 3 CO).

        Articolo 5 — Retribuzione
        5.1 Il salario annuo lordo è di CHF 110'000.-- (centodiecimila franchi),
            corrisposto in 13 mensilità.
        5.2 La tredicesima è corrisposta nel mese di novembre.
        5.3 Il salario è versato entro l'ultimo giorno lavorativo di ogni mese
            sul conto bancario indicato dal Lavoratore.
        5.4 Il Datore versa i contributi AVS/AI/IPG/APG e le altre
            prestazioni sociali obbligatorie secondo la legislazione vigente.

        Articolo 6 — Ferie
        6.1 Il Lavoratore ha diritto a 25 giorni lavorativi di ferie all'anno.
        6.2 Le ferie devono essere concordate con il Datore e godute durante
            l'anno di riferimento.
        6.3 Il Lavoratore con più di 50 anni ha diritto a 30 giorni di ferie.

        Articolo 7 — Assenza per malattia o infortunio
        7.1 In caso di malattia o infortunio, il Lavoratore conserva il diritto
            al salario per la durata del rapporto di lavoro, ma non oltre un
            anno (art. 324a CO).
        7.2 Il Datore ha stipulato un'assicurazione indennità giornaliera di
            malattia che interviene dopo 30 giorni di assenza.
        7.3 Il Lavoratore deve informare immediatamente il Datore in caso di
            assenza e presentare un certificato medico dopo tre giorni di
            assenza consecutivi.

        Articolo 8 — Divieto di concorrenza
        8.1 Al termine del rapporto di lavoro, il Lavoratore si impegna a non
            esercitare attività concorrenziale nei confronti del Datore per un
            periodo di 12 mesi (art. 322 CO).
        8.2 Il divieto è limitato al Canton Ticino e al Canton Grigioni.
        8.3 Il divieto è valido solo se il Lavoratore ha avuto accesso alla
            clientela o a segreti commerciali del Datore.
        8.4 In caso di violazione, il Lavoratore è tenuto a pagare una penale
            di CHF 25'000.--.

        Articolo 9 — Segreto professionale
        9.1 Il Lavoratore si impegna a mantenere il segreto su tutte le
            informazioni confidenziali del Datore (art. 321a CO).
        9.2 L'obbligo di segretezza permane anche dopo la cessazione del
            rapporto di lavoro.
        9.3 Sono considerate informazioni confidenziali: dati commerciali,
            strategie aziendali, codice sorgente, brevetti, know-how e
            qualsiasi altra informazione non pubblica.

        Articolo 10 — Proprietà intellettuale
        10.1 Tutte le opere create dal Lavoratore nell'ambito delle sue
             mansioni appartengono al Datore (art. 332 CO).
        10.2 Il Lavoratore non ha diritto a ulteriore compenso per le opere
             create nell'ambito del rapporto di lavoro.
        10.3 Le invenzioni fatte dal Lavoratore con mezzi propri e al di fuori
             delle mansioni restano di proprietà del Lavoratore (art. 332 cpv. 2
             CO).

        Articolo 11 — Preavviso e cessazione del rapporto
        11.1 Dopo il periodo di prova, il rapporto può essere disdetto da
             ciascuna delle parti con il seguente preavviso:
             - 1° anno di servizio: 1 mese (art. 335c cpv. 1 CO)
             - 2° - 9° anno: 2 mesi
             - 10° anno in poi: 3 mesi
        11.2 Il preavviso decorre dal primo giorno del mese successivo alla
             disdetta.
        11.3 In caso di giusta causa, ciascuna delle parti può recedere
             immediatamente (art. 337 CO).

        Articolo 12 — Attestato di lavoro
        12.1 Al termine del rapporto di lavoro, il Datore rilascia al
             Lavoratore un attestato di lavoro completo e benevolo
             (art. 330a CO).
        12.2 L'attestato deve contenere informazioni sul tipo e la durata del
             rapporto di lavoro, sulle mansioni svolte e sulla valutazione
             della prestazione.

        Articolo 13 — Clausola di modifica
        13.1 Eventuali modifiche al presente contratto devono essere concordate
             per iscritto.
        13.2 La modifica unilaterale delle condizioni essenziali del contratto
             non è ammessa.

        Articolo 14 — Clausola di salvaguardia
        14.1 Se una clausola del presente contratto è o diventa invalida, le
             restanti clausole conservano la loro validità.
        14.2 La clausola invalida è sostituita da una disposizione che si
             avvicina il più possibile allo scopo della clausola invalida.

        Articolo 15 — Diritto applicabile e foro
        15.1 Il presente contratto è regolato dal diritto svizzero.
        15.2 Per ogni controversia derivante dal presente contratto è competente
             il giudice del luogo di lavoro (art. 34 cpv. 1 LPGA).

        Articolo 16 — Entrata in vigore
        16.1 Il presente contratto è redatto in due originali, uno per ciascuna
             delle parti.
        16.2 Il contratto entra in vigore con la firma di entrambe le parti.

        Firma del Datore di lavoro          Firma del Lavoratore

        ________________________            ________________________
        Dr. Marco Bianchi                   Dr. Alessandro Rossi
        Amministratore Delegato             Ingegnere del Software Senior
        TechVision SA

        Data: 15 marzo 2024                 Data: 15 marzo 2024

        Luogo: Lugano                       Luogo: Lugano

        ----
        Nota: questo è un contratto fittizio creato a scopo di test.
        Non corrisponde a nessun contratto reale.
    """)


# ===========================================================================
# PDF generation
# ===========================================================================


def _create_pdf(output_path: Path, title: str, content: str) -> None:
    """Create a simple PDF from text content using fpdf2."""
    if not HAS_FPDF:
        print(f"  [SKIP] fpdf2 not available — cannot create PDF: {output_path.name}")
        return

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    # Add a Unicode font (DejaVu is commonly available on Linux)
    font_paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/dejavu-sans-fonts/DejaVuSans.ttf",
        "/usr/share/fonts/TTF/DejaVuSans.ttf",
    ]
    font_added = False
    for fp in font_paths:
        if Path(fp).exists():
            pdf.add_font("DejaVu", "", fp)
            pdf.set_font("DejaVu", size=10)
            font_added = True
            break

    if not font_added:
        pdf.set_font("Helvetica", size=10)

    # Title
    pdf.set_font_size(14)
    pdf.multi_cell(0, 8, title)
    pdf.ln(5)
    pdf.set_font_size(10)

    # Content — write line by line with error handling
    for line in content.split("\n"):
        stripped = line.strip()
        if not stripped:
            pdf.ln(3)
        else:
            try:
                pdf.multi_cell(0, 5, stripped)
            except Exception:
                # Try with sanitized text
                try:
                    safe = stripped.encode("ascii", errors="replace").decode("ascii")
                    pdf.multi_cell(0, 5, safe)
                except Exception:
                    # Skip problematic lines
                    pass

    pdf.output(str(output_path))


# ===========================================================================
# DOCX generation
# ===========================================================================


def _create_docx(output_path: Path, title: str, content: str) -> None:
    """Create a DOCX file from text content."""
    if not HAS_DOCX:
        print(f"  [SKIP] python-docx not available — cannot create DOCX: {output_path.name}")
        return

    doc = Document()
    doc.add_heading(title, level=0)

    for paragraph in content.split("\n\n"):
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        # Detect headings (lines starting with specific patterns)
        if paragraph.startswith("CAPITOLO") or paragraph.startswith("TITOLO") or \
           paragraph.startswith("Articolo") or paragraph.startswith("Art."):
            # Check if it's a section header
            lines = paragraph.split("\n")
            if len(lines) <= 3:
                doc.add_heading(paragraph, level=2)
            else:
                p = doc.add_paragraph(paragraph)
                p.style.font.size = Pt(10)
        else:
            p = doc.add_paragraph(paragraph)
            p.style.font.size = Pt(10)

    doc.save(str(output_path))


# ===========================================================================
# Main fetch/generate logic
# ===========================================================================


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate synthetic legal dataset")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("tests/data/synthetic/legal/documents"),
        help="Output directory for generated documents",
    )
    args = parser.parse_args()

    docs_dir = args.output_dir
    docs_dir.mkdir(parents=True, exist_ok=True)

    print(f"Output directory: {docs_dir}")

    # -----------------------------------------------------------------------
    # 1. Swiss Constitution IT — TXT
    # -----------------------------------------------------------------------
    txt_path = docs_dir / "ch_constitution_it.txt"
    if not txt_path.exists():
        print("Generating: ch_constitution_it.txt")
        txt_path.write_text(_swiss_constitution_it(), encoding="utf-8")
    else:
        print(f"  [SKIP] {txt_path.name} already exists")

    # -----------------------------------------------------------------------
    # 2. Swiss Constitution IT — PDF
    # -----------------------------------------------------------------------
    pdf_path = docs_dir / "ch_constitution_it.pdf"
    if not pdf_path.exists():
        print("Generating: ch_constitution_it.pdf")
        _create_pdf(pdf_path, "Costituzione Federale della Confederazione Svizzera (estratti)",
                    _swiss_constitution_it())
    else:
        print(f"  [SKIP] {pdf_path.name} already exists")

    # -----------------------------------------------------------------------
    # 3. Bundesverfassung DE — PDF
    # -----------------------------------------------------------------------
    pdf_de_path = docs_dir / "ch_constitution_de.pdf"
    if not pdf_de_path.exists():
        print("Generating: ch_constitution_de.pdf")
        _create_pdf(pdf_de_path,
                    "Bundesverfassung der Schweizerischen Eidgenossenschaft (Auszüge)",
                    _swiss_constitution_de())
    else:
        print(f"  [SKIP] {pdf_de_path.name} already exists")

    # -----------------------------------------------------------------------
    # 4. Swiss CO EN — TXT
    # -----------------------------------------------------------------------
    co_txt = docs_dir / "swiss_obligations_en.txt"
    if not co_txt.exists():
        print("Generating: swiss_obligations_en.txt")
        co_txt.write_text(_swiss_obligations_en(), encoding="utf-8")
    else:
        print(f"  [SKIP] {co_txt.name} already exists")

    # -----------------------------------------------------------------------
    # 5. Swiss CO EN — PDF
    # -----------------------------------------------------------------------
    co_pdf = docs_dir / "swiss_obligations_en.pdf"
    if not co_pdf.exists():
        print("Generating: swiss_obligations_en.pdf")
        _create_pdf(co_pdf, "Swiss Code of Obligations — Art. 319-362", _swiss_obligations_en())
    else:
        print(f"  [SKIP] {co_pdf.name} already exists")

    # -----------------------------------------------------------------------
    # 6. GDPR EN — TXT
    # -----------------------------------------------------------------------
    gdpr_en_txt = docs_dir / "gdpr_en.txt"
    if not gdpr_en_txt.exists():
        print("Generating: gdpr_en.txt")
        gdpr_en_txt.write_text(_gdpr_en(), encoding="utf-8")
    else:
        print(f"  [SKIP] {gdpr_en_txt.name} already exists")

    # -----------------------------------------------------------------------
    # 7. GDPR EN — PDF
    # -----------------------------------------------------------------------
    gdpr_en_pdf = docs_dir / "gdpr_en.pdf"
    if not gdpr_en_pdf.exists():
        print("Generating: gdpr_en.pdf")
        _create_pdf(gdpr_en_pdf, "GDPR — Articles 1-49", _gdpr_en())
    else:
        print(f"  [SKIP] {gdpr_en_pdf.name} already exists")

    # -----------------------------------------------------------------------
    # 8. GDPR IT — TXT
    # -----------------------------------------------------------------------
    gdpr_it_txt = docs_dir / "gdpr_it.txt"
    if not gdpr_it_txt.exists():
        print("Generating: gdpr_it.txt")
        gdpr_it_txt.write_text(_gdpr_it(), encoding="utf-8")
    else:
        print(f"  [SKIP] {gdpr_it_txt.name} already exists")

    # -----------------------------------------------------------------------
    # 9. GDPR DOCX (IT + EN combined)
    # -----------------------------------------------------------------------
    gdpr_docx = docs_dir / "gdpr.docx"
    if not gdpr_docx.exists():
        print("Generating: gdpr.docx")
        combined = _gdpr_en() + "\n\n---\n\nVERSIONE ITALIANA\n\n" + _gdpr_it()
        _create_docx(gdpr_docx, "GDPR — Regolamento (UE) 2016/679", combined)
    else:
        print(f"  [SKIP] {gdpr_docx.name} already exists")

    # -----------------------------------------------------------------------
    # 10. Sentenza TF — MD
    # -----------------------------------------------------------------------
    sentenza_path = docs_dir / "sentenza_tf.md"
    if not sentenza_path.exists():
        print("Generating: sentenza_tf.md")
        sentenza_path.write_text(_sentenza_tf(), encoding="utf-8")
    else:
        print(f"  [SKIP] {sentenza_path.name} already exists")

    # -----------------------------------------------------------------------
    # 11. Contratto lavoro — DOCX
    # -----------------------------------------------------------------------
    contratto_path = docs_dir / "contratto_lavoro.docx"
    if not contratto_path.exists():
        print("Generating: contratto_lavoro.docx")
        _create_docx(contratto_path, "Contratto di Lavoro — TechVision SA",
                     _contratto_lavoro())
    else:
        print(f"  [SKIP] {contratto_path.name} already exists")

    # -----------------------------------------------------------------------
    # 12. EU AI Act EN — TXT
    # -----------------------------------------------------------------------
    ai_act_txt = docs_dir / "eu_ai_act_en.txt"
    if not ai_act_txt.exists():
        print("Generating: eu_ai_act_en.txt")
        ai_act_txt.write_text(_eu_ai_act_en(), encoding="utf-8")
    else:
        print(f"  [SKIP] {ai_act_txt.name} already exists")

    # -----------------------------------------------------------------------
    # 13. EU AI Act EN — PDF
    # -----------------------------------------------------------------------
    ai_act_pdf = docs_dir / "eu_ai_act_en.pdf"
    if not ai_act_pdf.exists():
        print("Generating: eu_ai_act_en.pdf")
        _create_pdf(ai_act_pdf, "EU AI Act — Titles I-IV", _eu_ai_act_en())
    else:
        print(f"  [SKIP] {ai_act_pdf.name} already exists")

    print("\nDone! All documents generated.")


if __name__ == "__main__":
    main()
