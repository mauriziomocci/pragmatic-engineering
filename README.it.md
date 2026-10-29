# pragmatic-engineering

[English](README.md)

pragmatic-engineering è un metodo di ingegneria per Claude Code, messo in ordine. Porta regole di lavoro a ogni agente di una sessione con una sola riga di import nel tuo `CLAUDE.md`, e aggiunge dodici skill che coprono le fasi e le tre corsie del lavoro, più un agente, `blunt-reviewer`, che rivede un intervallo git in modo indipendente e schietto. La versione 0.1.0 è il nucleo del metodo: le regole, le skill, il revisore e un hook `SessionStart` che tiene le regole al loro posto. Questa versione non ha nessun controllo meccanico sulle merge request: la revisione prima di una merge request è una regola per il modello, non un cancello.

Questa pagina segue i quattro tipi di documentazione di Diataxis (<https://diataxis.fr>), una sezione per ciascuno: un tutorial, le guide pratiche, una spiegazione e un riferimento, con i limiti noti fra gli ultimi due. Per ogni parte del metodo la spiegazione dice che cosa la garantisce: un meccanismo, cioè codice che gira qualunque cosa faccia il modello, oppure solo una regola per il modello, cioè un testo che il modello deve seguire e che nessuno controlla.

<!-- section: tutorial -->
## Tutorial: una prima sessione guidata

Ti servono Claude Code e un progetto git su cui lavorare. Ogni passo dice che cosa dovresti vedere; se vedi altro, fermati lì e leggi la guida all'installazione più sotto.

1. Installa il plugin come dice la guida all'installazione. Prima controlla che `claude plugin marketplace list` mostri `claude-plugins-official`, e se manca aggiungilo come dice la guida; poi esegui i due comandi:

   ```
   claude plugin marketplace add mauriziomocci/pragmatic-engineering
   claude plugin install pragmatic-engineering@pragmatic-engineering
   ```

   Dovresti vedere i due comandi finire senza errori. Se il plugin resta disabilitato e il messaggio dice che una dipendenza non è installata, la guida all'installazione spiega perché e che cosa fare.

2. Avvia Claude Code nel tuo progetto. In cima alla sessione l'hook `SessionStart` stampa due avvisi. Il primo dice, in inglese, "pragmatic-engineering: the rules file was updated; the updated rules apply from the next session."; compare perché l'hook ha appena copiato il file delle regole nella cartella dei dati del plugin. Il secondo dice che `~/.claude/CLAUDE.md` non porta ancora due righe e le stampa: una riga di import che comincia con `@`, e una riga lunga che comincia con "If the pragmatic-engineering rules".

3. Aggiungi le due righe a `~/.claude/CLAUDE.md`, dopo una copia datata del file, come mostra la guida all'installazione, poi esci e riavvia Claude Code. Questa volta non dovresti vedere nessun avviso. Se l'avviso torna, le righe non sono scritte come stampate: l'hook cerca il percorso dell'import e la riga di rete di sicurezza per intero.

4. Chiedi: "Quote your rule `PE:backup-diff-go`." (puoi anche chiederlo in italiano). Dovresti vedere una risposta che dice che i file di istruzioni, impostazioni e memoria cambiano solo dopo una copia datata, un diff e il tuo via. Quella regola sta in `rules.md` e in nient'altro che una sessione carichi, non nella riga di rete di sicurezza e non in una skill, quindi una risposta giusta mostra che l'import ha raggiunto la sessione. Se il modello dice di non avere una regola con quel nome, l'import non è arrivato: ricontrolla le due righe del passo 3 e riprova in una sessione nuova.

5. Chiedi una piccola modifica con un test, per esempio una funzione con un solo comportamento. Dovresti vedere, in quest'ordine: il modello nomina la corsia (una funzionalità) e dice in poche frasi che cosa sta per fare, chiudendo con «is it clear?» nella tua lingua; si ferma per la tua approvazione scritta di una spec breve prima del codice, perché i due cancelli pesanti restano anche per un lavoro piccolo; scrive il test che fallisce per primo e lo esegue; scrive il codice; rivede il proprio diff seguendo `blunt-review` e chiude con una dichiarazione che i test passano o con l'elenco di ciò che non passa; si ferma di nuovo per la tua approvazione del risultato; non fa mai un push senza il tuo via.

6. Fai il commit del lavoro su un ramo e di': "Review this branch before I open the merge request." (anche in italiano). Dovresti vedere il modello lanciare `blunt-reviewer` con una sola riga, `<merge-base>..HEAD`, dove `<merge-base>` è il commit che stampa `git merge-base`. Il revisore scrive il rapporto in `.pe/reviews/`, in un file chiamato `<base7>..<tip7>-round1.md` la cui prima riga è una riga di stato, e il suo messaggio finale chiude con cinque righe: `VERDICT:`, `FINDINGS:`, `COVERAGE:`, `REPORT:` e `THE THING:`. Con `VERDICT: changes` si correggono i rilievi bloccanti, si fa il commit e parte una seconda revisione sulle correzioni; la spiegazione del ciclo di revisione, più sotto, dice come procede.

<!-- section: how-to -->
## Guide pratiche

<!-- section: install -->
### Installare

Requisiti: Claude Code, `python3` 3.9 o successivo nel percorso di ricerca (l'hook è uno script Python) e git (il revisore legge intervalli git).

Il plugin dipende da superpowers (`superpowers@claude-plugins-official`). Claude Code installa superpowers da sé insieme a questo plugin solo se il marketplace ufficiale è già registrato nel tuo Claude Code. Di norma si registra da solo la prima volta che avvii una sessione interattiva da terminale, ma non per chi ha usato Claude Code soltanto dall'estensione di VS Code, né quando una policy lo blocca o quando è impostata `CLAUDE_CODE_DISABLE_OFFICIAL_MARKETPLACE_AUTOINSTALL`. Senza di esso il plugin si installa ma resta disabilitato, e Claude Code dice che la dipendenza non è installata. Quindi controlla prima, dal terminale:

```
claude plugin marketplace list
```

Se `claude-plugins-official` non è nell'elenco, aggiungilo:

```
claude plugin marketplace add anthropics/claude-plugins-official
```

Poi installa questo plugin:

```
claude plugin marketplace add mauriziomocci/pragmatic-engineering
claude plugin install pragmatic-engineering@pragmatic-engineering
```

Se hai installato il plugin prima di aggiungere il marketplace ufficiale e resta disabilitato, aggiungi il marketplace con il comando qui sopra ed esegui `/reload-plugins` dentro Claude Code.

Che cosa è stato provato: i manifesti passano `claude plugin validate` di Claude Code 2.1.303, e le skill che citano superpowers sono state controllate contro superpowers 7.0.0. Una prova da capo a fondo, che si lancia su richiesta, verifica che un import `@rules.md` nel `CLAUDE.md` di un progetto raggiunga la sessione principale e un sotto-agente, con il plugin caricato da `--plugin-dir`; è stata eseguita dal vivo una volta, il 29 ottobre 2026, e 4 prove sono passate. L'import da `~/.claude/CLAUDE.md` della copia nella cartella dei dati, che è quello usato da questa guida, non è esercitato da quella prova. L'installazione dal marketplace e quella automatica di superpowers seguono la documentazione delle dipendenze di Claude Code e si verificano alla prima installazione reale, non prima.

Avvia una sessione. `SessionStart` copia `rules.md` nella cartella dei dati del plugin e stampa le due righe che il tuo `CLAUDE.md` richiede. Il plugin non scrive mai il tuo `CLAUDE.md`: lo scrivi tu, dopo una copia datata del file e guardando la differenza. Fai prima la copia (saltala se non hai ancora un `CLAUDE.md`, e crea il file), aggiungi le due righe, controlla la differenza, poi apri una sessione nuova:

```
cp ~/.claude/CLAUDE.md ~/.claude/CLAUDE.md.$(date +%F).bak
diff ~/.claude/CLAUDE.md.$(date +%F).bak ~/.claude/CLAUDE.md
```

Le due righe sono queste. La prima è l'import che l'avviso stampa, per esempio `@~/.claude/plugins/data/<cartella del plugin>/rules.md`: copiala dall'avviso, perché porta il percorso esatto sulla tua macchina e protegge gli spazi che contiene. La seconda è la riga di rete di sicurezza, che resta in inglese, parola per parola, perché è il testo che il modello legge quando il plugin non c'è più:

```
If the pragmatic-engineering rules (marker PE-RULES v1) or its skills are missing from this session, tell the user before doing any work: the plugin is uninstalled or disabled.
```

L'import è ciò che porta le regole alla sessione. La riga di rete di sicurezza è ciò che ti avvisa quando smettono di arrivare, perché `SessionStart` non può girare quando il plugin è disinstallato o disabilitato.

Aggiornare: il manifesto fissa la versione, quindi Claude Code ti porta a una nuova versione solo quando cambia la sua stringa di versione, e l'aggiornamento automatico è spento di norma per i marketplace diversi da quelli di Anthropic. Per aggiornare a mano, aggiorna il marketplace con `claude plugin marketplace update pragmatic-engineering`, esegui `claude plugin update pragmatic-engineering@pragmatic-engineering` e riavvia. Il `SessionStart` successivo copia il nuovo `rules.md`, e le nuove regole valgono dalla sessione dopo.

<!-- section: uninstall -->
### Disinstallare e tornare indietro

Vai in quest'ordine. Prima togli le due righe da `~/.claude/CLAUDE.md`, oppure ripristina la copia datata che hai fatto all'installazione se da allora non hai cambiato altro nel file. Poi esegui:

```
claude plugin uninstall pragmatic-engineering@pragmatic-engineering
```

L'ordine conta per due ragioni. La riga di rete di sicurezza senza il plugin fa avvisare il modello a ogni avvio di sessione. E la disinstallazione cancella la cartella dei dati del plugin, che contiene la copia di `rules.md` a cui punta il tuo import, a meno che tu passi `--keep-data`; che cosa faccia Claude Code con un import che punta a un file mancante non è stato provato qui.

Tre cose restano, di proposito. Superpowers resta installato; `--prune` sul comando di disinstallazione toglie anche le dipendenze installate in automatico che non servono più. Il marketplace resta registrato finché non esegui `claude plugin marketplace remove pragmatic-engineering`. E restano le cartelle `.pe/` che il revisore e la nota di avanzamento hanno creato nei tuoi progetti: contengono rapporti di revisione e note, non entrano mai in git perché ciascuna porta un `.gitignore` con `*`, e le cancelli a mano se vuoi eliminarle.

<!-- section: maintainers -->
### Lavorare su questo repository

Gli strumenti qui sotto appartengono a questo repository e non fanno parte del plugin. Proteggono la privacy di un repository costruito in pubblico, e si usano nel clone del manutentore:

- `tools/privacy_check.py` controlla tutto ciò che un push manda al remoto (per ogni commit spinto le righe aggiunte, il messaggio, i nomi e le email di autore e committer e il percorso di ogni file aggiunto o modificato; i nomi dei riferimenti; i tag annotati) cercando i termini privati del manutentore, elencati in un file fuori dal repository che `git config pe.privateTermsFile` indica, e gli schemi generici come i percorsi di home e i token riconoscibili. Salta i file binari e lo dice, e fallisce chiuso.
- `tools/install_dev_hooks.py` copia quel controllo, l'hook di progetto qui sotto e i loro filtri nella cartella git del clone, fuori dall'albero di lavoro, e installa l'hook `pre-push` che esegue la copia; una modifica all'albero di lavoro ha effetto solo quando l'installatore gira di nuovo. Se la copia manca o si rompe, un controllo che non può girare rifiuta il push o lo strumento; rieseguire `python3 tools/install_dev_hooks.py` dal tuo terminale ripristina la copia. Rifiuta di sovrascrivere un hook `pre-push` che non ha scritto lui, e di installare mentre `core.hooksPath` è impostato.
- `tools/dev_guard.py` è un hook `PreToolUse` di Claude Code, registrato nel `.claude/settings.local.json` del manutentore (un file che git ignora) con il comando `python3 "<copia>/tools/dev_guard.py" || exit 2` e con `"onFailure": "block"`. Il `|| exit 2` fa bloccare qualunque uscita diversa da 0 con ogni versione di Claude Code, compresi un `python3` mancante o una copia dello script mancante. `"onFailure": "block"` blocca lo strumento anche quando l'hook va in timeout, non riesce ad avviarsi o stampa un'uscita che non passa la validazione; Claude Code lo legge dalla versione 2.1.295, e con una versione precedente un hook in timeout non blocca e la chiamata prosegue con il normale flusso dei permessi. Impedisce a un agente di saltare il controllo o di spegnere gli hook, blocca gli strumenti MCP che scrivono direttamente su un remoto e le chiamate API dirette che scrivono sulle pull request, e controlla il testo dei comandi sulle pull e merge request (`gh`, `glab` e strumenti MCP). Legge quel testo solo dove è scritto, e blocca ciò che la shell riempie al momento dell'esecuzione, con il suggerimento di scriverlo prima in un file. Le regole esatte sono nei docstring dei moduli `tools/dev_guard.py` e `lib/pe_guard/filters.py`.

Non coperto. I filtri leggono testo e difendono dalla fretta di un agente, non da chi vuole aggirarli di proposito. Aperto, in parte per scelta e in parte non ancora chiuso:

- gli altri comandi `gh` e `glab` che scrivono testo: release, issue, gist, etichette, impostazioni del repository;
- gli strumenti MCP che creano rami o altri oggetti, scrivono issue, o commentano e rivedono pull request;
- le scritture API dirette fuori dalle pull request (contenuti del repository, riferimenti, file e commit di GitLab, una mutation GraphQL che crea un commit), e qualunque chiamata con `curl` o un altro client;
- `core.hooksPath` modificato con gli strumenti di file (`git config` e `git -c` sono bloccati);
- `--no-verify` dal terminale del manutentore;
- il controllo modificato nell'albero di lavoro e poi installato: per ora nulla protegge l'installatore;
- i file che una regola `-diff` di `.gitattributes` fa dichiarare binari a git: saltati, e il salto è elencato;
- un termine attaccato ad altre lettere, prima o dopo (`myterm`, `MYTERM`, `terms`): i termini corrispondono come parole intere in qualunque maiuscolo o minuscolo, e solo un carattere che non è una lettera o una maiuscola che apre una parola nuova (`myTerm`) segna il confine, quindi anche queste forme vanno elencate;
- le forme che l'hook non vede nel comando: una chiamata nascosta in uno script, un alias, una funzione o una variabile, o costruita dentro `sh -c`; un programma diverso da `xargs` che esegue `gh` e ne fornisce il testo (`find -exec`, `parallel`); il nome di un'opzione o di un comando scritto fra virgolette o con escape; un cambio di cartella fatto da un programma diverso da `cd`, `pushd` o `chdir`; l'espansione con le graffe e i glob; un file del corpo scritto con un'altra grafia del suo nome, o da uno script che non lo nomina;
- i flag di `gh` che riempiono una pull request da altrove: modelli, allegati, un'esecuzione precedente fallita, un editor, il browser, e i messaggi dei commit, che il pre-push controlla;
- le sessioni in cui l'hook di progetto non è caricato: gira nel clone principale e nelle sessioni di worktree avviate dall'app desktop di Claude (leggono le impostazioni del checkout principale), non in una sessione da terminale dentro un worktree collegato, dove il pre-push gira comunque.

Gli elenchi esatti delle forme nascoste e dei flag di `gh` sono nei docstring dei moduli `tools/dev_guard.py` e `lib/pe_guard/filters.py`.

Prove: `python3 -m pytest -q` dalla radice del repository. Requisiti: Python 3.9 o successivo, pytest 7 o successivo, git 2.32 o successivo. La prova da capo a fondo dell'import avvia Claude Code, quindi l'esecuzione predefinita la lascia fuori (prove marcate `e2e`); si lancia su richiesta con `python3 -m pytest -m e2e tests/e2e -v`.

Il flusso `.github/workflows/ci.yml` esegue la stessa suite a ogni push e a ogni pull request, su Python 3.9 e sull'ultimo Python, e fallisce con un rosso. Un secondo job esegue ruff 0.12.8 con le regole C901, PLR0912, PLR0915 e PLR1702, in modalità preview e con l'annidamento limitato a 3, sui file Python che la modifica tocca rispetto al ramo predefinito, e fallisce con qualunque rilievo. Due tipi di prova lì non girano: le prove da capo a fondo, che chiedono le credenziali di Claude Code, e il controllo dei nomi fissati di superpowers, che si salta da sé dove superpowers non è installato. Ruff non ha una regola per le funzioni oltre le 40 righe: si misurano prima del commit e in revisione.

<!-- section: explanation -->
## Come funziona

Le sette parti qui sotto chiudono ciascuna con una riga che dice che cosa garantisce la parte. In questa versione quattro cose sono meccaniche: l'hook `SessionStart`, che copia le regole e controlla il tuo `CLAUDE.md`; l'import `@` di Claude Code, che consegna il file delle regole come tue istruzioni; il campo `skills` dell'agente, che fa caricare `blunt-review` e `quality-scoring` a Claude Code dentro l'agente; e il campo `disable-model-invocation` della skill `autonomous-execution`, che impedisce al modello di avviarla. Tutto il resto è una regola per il modello.

<!-- section: explain-lanes -->
### Tre corsie

La corsia viene dalla natura del lavoro, e la dichiara `development-workflow`. Una funzionalità (un comportamento nuovo o un cambio di struttura) passa per fasi e cancelli. Supporto e incidenti, dal ticket alla correzione, mettono le prove primarie prima delle ipotesi e le tue modifiche recenti prima delle cause esterne, con una diagnosi e una proposta più brevi al posto delle fasi complete, e con un via sulla proposta e un via prima della produzione. Le operazioni su sistemi vivi caricano `safe-operations` prima di qualunque comando o strumento che cambia un sistema esterno: si verifica e si dichiara il bersaglio attivo, si dicono prima il raggio d'azione e la via del ritorno, e ogni esecuzione in produzione chiede il suo via. Quando la corsia non è chiara, il modello chiede.

**Garantito da:** solo una regola per il modello (le regole `lanes` e `production-go` in `rules.md`, e le skill `development-workflow` e `safe-operations`). Nulla controlla quale corsia sceglie il modello né che il via sia stato chiesto.

<!-- section: explain-gates -->
### Fasi e cancelli

Una funzionalità passa per sette fasi: idea e requisiti, spec, piano, compiti, implementazione, validazione e chiusura. Una fase comincia solo quando il cancello prima di essa è chiuso. I cancelli sono quattro: due pesanti, la spec e la validazione finale, e due leggeri, il piano e l'elenco dei compiti. Un cancello pesante è una sintesi breve, la domanda «is it clear?» e la tua approvazione scritta; un semplice "ok" a una spec che nessuno ha letto non è un'approvazione. Un cancello leggero è un rapido controllo di coerenza. L'implementazione non ha un cancello ma un'escalation: un caso imprevisto, un'ipotesi sbagliata o un'incoerenza con il codice esistente fermano il compito e lo riportano a chi decide.

Il lavoro piccolo (meno di tre file, una correzione ovvia, un valore di configurazione) condensa le prime quattro fasi in una breve analisi, e tiene entrambi i cancelli pesanti. L'unica eccezione è `autonomous-execution`, che puoi avviare solo tu, nominandola: la sua validazione interna (la suite completa e la revisione di `blunt-reviewer`) sostituisce il cancello finale, e la tua invocazione è il via a spingere il ramo del lavoro e ad aprirne la merge request, mai a unirla. Il cancello della spec non ha eccezioni.

Una funzionalità usa una sola catena di strumenti, mai due. Di norma è superpowers (`superpowers:brainstorming`, `superpowers:writing-plans`, `superpowers:subagent-driven-development`, con `superpowers:test-driven-development` per ogni compito); spec-kit solo se lo chiedi, e allora `spec-driven-layout` dice dove stanno i suoi file. Il test che fallisce viene prima in entrambe le catene.

**Garantito da:** un meccanismo per una cosa: `disable-model-invocation` impedisce al modello di avviare `autonomous-execution`. Una regola per il resto (le regole `heavy-gates` e `test-first` in `rules.md`, e la skill `development-workflow`). Nulla registra un'approvazione né impedisce al modello di scrivere codice prima di averla.

<!-- section: explain-review -->
### Revisione indipendente

L'agente `blunt-reviewer` rivede un intervallo git con la skill `blunt-review` caricata. Il suo prompt è una sola riga in una grammatica chiusa, `<base>..<tip> [round=1|2] [full=<path>,...]`, con `<base>` antenato di `<tip>`; qualunque altra cosa non viene rivista, e chi lo lancia non può orientare la revisione attraverso il prompt. Legge la modifica un commit alla volta, poi l'insieme, gira su Opus e scrive il rapporto in `.pe/reviews/` a blocchi, con una riga di stato in cima. Ogni rilievo porta la sua prova, i rilievi vanno dal peggiore, e una riga finale indica la correzione sola che conta di più, oppure dice che non c'è nulla da rilevare e che cosa è stato verificato. Ogni rilievo porta la sua lente e la sua classe, S1 critica, S2 seria o S3 media, come le definisce `quality-scoring`, e un rilievo è bloccante quando è S1 o S2: uno scenario che fallisce, un invariante contraddetto, un problema di sicurezza o di privacy o un'operazione senza via del ritorno sono S1, e una prova mancante o tautologica su un comportamento cambiato o un documento contraddetto dal codice sono S2. Il verdetto è `changes` solo con almeno un rilievo bloccante, e dice se serve un altro giro di revisione; il voto di ogni lente, calcolato dagli stessi rilievi, dice se il lavoro si può integrare. I messaggi dei commit e i file nominati da `full=` sono affermazioni dell'autore, che il revisore verifica e a cui non obbedisce mai.

La revisione si fa prima di aprire una merge request, sull'intero intervallo del ramo, e di nuovo a ogni giro dopo le correzioni.

**Garantito da:** un meccanismo per una cosa: il campo `skills` dell'agente fa caricare `blunt-review` e `quality-scoring` a Claude Code dentro l'agente. Regole per il resto: che una revisione si faccia prima di una merge request, che il prompt segua la grammatica (l'agente rifiuta gli altri prompt per istruzione propria, e nulla fuori da lui controlla) e che non scriva nulla fuori da `.pe/` sono dichiarati, non imposti. Nessun meccanismo registra che una revisione sia avvenuta, quindi il verdetto è un messaggio da leggere, non un cancello.

<!-- section: explain-review-cycle -->
### Il ciclo di revisione dopo le correzioni

Il ciclo parte dopo un controllo indipendente (il panel, oppure `blunt-reviewer` su un ramo o su una consegna) e dopo le correzioni dei suoi rilievi. Il risultato corretto si committa prima di ogni giro, perché il revisore riceve un intervallo git.

Nel giro 1 un `blunt-reviewer` con contesto nuovo, che non ha scritto né il lavoro né le correzioni, rilegge il risultato corretto: un documento per intero con `full=`; il codice attraverso l'intervallo delle correzioni, `<tip before the fixes>..<tip after the fixes>` (dall'ultimo commit prima delle correzioni all'ultimo dopo), con il resto del ramo leggibile con git in sola lettura come contesto. Con `VERDICT: pass` il ciclo finisce. Con `changes` si correggono i rilievi bloccanti e comincia il giro 2: un altro revisore nuovo rilegge l'intervallo delle ultime correzioni, con `round=2`. Con `pass` il ciclo finisce. Se anche il giro 2 chiude con `changes`, non c'è un terzo giro: i rilievi bloccanti ancora aperti salgono a te, con la raccomandazione di chi li porta, perché un rilievo bloccante ancora aperto dopo due giri di solito dice che il modo di correggere è sbagliato. Il ciclo continua solo con `changes`. Le correzioni di ogni giro si elencano in una tabella nel corpo del commit delle correzioni (rilievo, decisione, posto), e il giro successivo controlla anche quella tabella.

**Garantito da:** solo una regola per il modello (la skill `blunt-review`). Nessun meccanismo conta i giri né impedisce un terzo.

<!-- section: explain-rules-import -->
### Le regole attraverso un import

`rules.md` è il file delle regole di lavoro. La sua prima riga è il marcatore `PE-RULES v1`, e ha tre blocchi: le regole per ogni agente, quelle per la sessione principale, quelle per i sotto-agenti. Dichiara che le tue istruzioni prevalgono in caso di conflitto, e che un conflitto con le sue cinque regole di precedenza (prove, nessun difetto lasciato indietro, prima il test, revisione schietta, onere della prova su ciò che si aggiunge) va a te e non si risolve mai in silenzio.

La radice del plugin non sopravvive a un aggiornamento del plugin e la sua cartella dei dati sì, quindi a ogni avvio di sessione `SessionStart` copia `rules.md` dalla radice alla cartella dei dati quando la copia manca o è diversa. Il tuo `CLAUDE.md` importa la copia con una riga `@`; è così che le regole raggiungono la sessione come tue istruzioni, che superpowers mette sopra le sue skill. La seconda riga che aggiungi è la riga di rete di sicurezza, per il giorno in cui il plugin non c'è più.

Nel tuo `CLAUDE.md` cambiano esattamente due righe, e le aggiungi tu: l'hook legge soltanto il file e stampa ciò che manca. Le regole raggiungono la sessione principale e i sotto-agenti che caricano il tuo `CLAUDE.md`; non raggiungono `Explore`, `Plan` e gli agenti definiti con `omitClaudeMd: true`. Un aggiornamento delle regole vale dalla sessione successiva. Una prova da capo a fondo, lanciata su richiesta, dà un riscontro sull'import di Claude Code; non è un meccanismo del plugin e non gira nella tua sessione (la guida all'installazione dice che cosa copre).

**Garantito da:** un meccanismo per la consegna: l'hook copia e controlla, e l'import `@` di Claude Code porta il file. Una regola per l'osservanza: al modello è chiesto di seguire le regole, e nulla controlla che lo faccia.

<!-- section: explain-continuity -->
### Continuità

Il lavoro si salva in anticipo, in tre forme, tutte descritte da `continuity-note`. La nota di avanzamento è lo stato in poche righe (fatto, in corso, prossimo, decisioni aperte), aggiornata a ogni traguardo e riletta dopo una compattazione; sta in `.pe/progress.md` alla radice del repository, con un `.pe/.gitignore` che contiene `*`, a meno che il progetto dichiari una nota propria. Il file di consegna di un compito dato a un sotto-agente si scrive a blocchi e porta in cima una riga di stato, `STATUS: IN PROGRESS - done: ...; next: ...`, che l'ultimo blocco sostituisce con `STATUS: COMPLETE`. La nota di continuità completa si scrive quando una sessione finisce con del lavoro in corso o quando il lavoro passa a un altro agente, così che un contesto nuovo riparta senza rileggere la conversazione.

**Garantito da:** solo una regola per il modello (le regole `save-ahead` e `status-line` in `rules.md`). Nulla conta i salvataggi, quindi una compattazione perde al massimo il lavoro fatto dall'ultimo salvataggio, e quanto sia poco dipende dalla disciplina del modello.

<!-- section: explain-communication -->
### Come ti parla il plugin

Il modello spiega in breve e ad alto livello in quattro momenti: all'inizio e alla fine di un blocco di lavoro, a ogni scelta di architettura (la scelta, l'alternativa principale scartata e perché) e prima di un cancello pesante. Ogni spiegazione chiude con «is it clear?» nella tua lingua, e ciò che dici non essere chiaro si spiega di nuovo con parole diverse e un esempio. La risposta si aspetta solo ai due cancelli pesanti e alle scelte di architettura; non c'è nessun quiz e nessuna domanda di verifica, mai. Il tono è franco: niente consenso per compiacere, niente adulazione, ragionamenti deboli contestati con le prove, rischi e costi opportunità nominati, e un'ipotesi sulle tue intenzioni dichiarata come ipotesi. La skill `teach` porta le spiegazioni e il metodo per insegnare il codice; il file delle regole porta il tono.

**Garantito da:** solo una regola per il modello (le regole `explain`, `no-quiz` e `candour` in `rules.md`, e la skill `teach`). «Is it clear?» non prova che tu abbia capito, e le regole sul tono riducono la tendenza del modello a darti ragione, non la eliminano.

<!-- section: limits -->
## Limiti noti

I limiti che descrivono il comportamento di Claude Code (quali agenti caricano `CLAUDE.md`, Cowork, la compattazione) vengono dalla sua documentazione letta durante la progettazione del plugin. Le prove del plugin non li esercitano, a parte l'import stesso.

- Non c'è nessun controllo meccanico sulle merge request: la revisione prima di una è una regola per il modello, e il verdetto di `blunt-reviewer` è un messaggio da leggere, non un cancello.
- Le regole non raggiungono `Explore`, `Plan` e gli agenti con `omitClaudeMd: true`, perché viaggiano nel tuo `CLAUDE.md`.
- Cowork salta gli import che puntano fuori dalla sua cartella di lavoro, quindi le regole lì non arrivano.
- Un aggiornamento del file delle regole vale dalla sessione successiva a quella che lo ha copiato.
- Che un sotto-agente compattato da Claude Code conservi le regole importate non è verificato.
- Con il plugin disinstallato o disabilitato `SessionStart` non gira, e ti avvisa soltanto la riga di rete di sicurezza nel tuo `CLAUDE.md`.
- «Is it clear?» non prova la comprensione, e le regole sul tono riducono la tendenza del modello a darti ragione senza eliminarla.
- La continuità perde al massimo il lavoro fatto dopo l'ultimo salvataggio, e dipende dalla disciplina del modello perché nulla conta i salvataggi.
- La grammatica del prompt di `blunt-reviewer` e il fatto che non scriva file fuori da `.pe/` sono dichiarati nell'agente, non imposti.
- Superpowers si installa da sé solo se il marketplace ufficiale è già registrato nel tuo Claude Code; altrimenti questo plugin resta disabilitato finché non lo aggiungi (vedi la guida all'installazione).
- La versione è fissata nel manifesto, quindi un aggiornamento ti raggiunge solo quando cambia la stringa di versione e tu lo chiedi, a meno che tu attivi l'aggiornamento automatico.
- Se hai già un plugin chiamato superpowers da un altro marketplace, la documentazione di Claude Code dice che entrambi risultano abilitati e che gli hook di uno dei due vengono lasciati fuori; qui non è stato provato.
- Il plugin è stato provato solo su macOS; la CI esegue le prove del repository su Linux.

<!-- section: reference -->
## Riferimento

In questa versione non ci sono comandi.

### Skill

Claude Code carica una skill quando il compito corrisponde alla sua descrizione, salvo diversa indicazione della tabella.

| Skill | Che cosa fa | Quando si carica |
|---|---|---|
| `engineering-principles` | Capire prima di implementare, riusare prima di costruire, principi di progetto e di collocazione, disciplina dei test, nessun difetto lasciato indietro, codice sicuro, igiene dei segreti, regole di scrittura. | Prima di capire un requisito, proporre un approccio, o scrivere o cambiare codice, test o documentazione; non per il lavoro palesemente banale. |
| `evidence-based-investigation` | Verificare prima di affermare, dichiarare il livello di confidenza, escludere le ipotesi una a una, delimitare un difetto in quattro passi, separare il verificato dall'inferito. | Indagini, diagnosi e risposte tecniche in cui una conclusione sbagliata ha un costo; non per progetto o revisione. |
| `blunt-review` | Come si scrive una revisione e quando un rilievo blocca; lenti per progetto, test, documentazione, infrastruttura e diagnosi; la revisione indipendente e il ciclo di revisione dopo le correzioni. | Ogni revisione, autorevisione compresa. Precaricata in `blunt-reviewer`. |
| `quality-scoring` | Un voto da 1 a 10 per ogni lente che il lavoro tocca, calcolato dai rilievi classificati S1, S2 o S3; chi vota quale lente; la scheda del voto; il registro di taratura nella cartella dei dati del plugin. | Ogni revisione che alimenta il cancello 8/10 della fase 6, prima di integrare o rilasciare il lavoro. Precaricata in `blunt-reviewer`. |
| `adversarial-review-panel` | Quattro lenti che si contraddicono, un controinterrogatorio e una sola decisione. | Decisioni in cui sbagliare costa caro: architettura, spec, refactoring rischiosi, sicurezza, scelte di tecnologia, modelli di dati; non per le revisioni ordinarie. |
| `development-workflow` | Le tre corsie, sette fasi e quattro cancelli, una catena per funzionalità, il progetto in tre passi, i modelli per ruolo, i livelli di istruzioni, la chiusura. | Qualunque lavoro sul codice, un rilascio, un merge o una chiusura. |
| `spec-driven-layout` | Dove spec-kit tiene i suoi file e quanto scrivere per il peso del lavoro. | Solo quando chiedi spec-kit. |
| `autonomous-execution` | Esegue una spec approvata senza supervisione fino all'apertura della sua merge request, registrando le decisioni che prende da sola. | Solo quando la invochi per nome; il modello non la carica mai di sua iniziativa. |
| `teach` | Spiegazioni brevi seguite da «is it clear?», il metodo a sei strati per insegnare il codice, lo stato su una schermata alla ripresa. | Quando chiedi come funziona il codice o di essere istruito, quando una sessione riprende, prima di un cancello pesante. |
| `continuity-note` | La nota di continuità, la nota di avanzamento e la riga di stato dei file di consegna. | Quando il lavoro passa a un altro agente o a un'altra sessione, e a ogni traguardo nella sua forma breve. |
| `safe-operations` | Verificare il bersaglio, prova a secco, dire il raggio d'azione e la via del ritorno, un via a parte per la produzione, mai interrogare in ciclo, verificare a ogni livello. | Prima di un comando o di uno strumento che cambia un sistema esterno. |
| `interface-quality` | I dieci principi di un'interfaccia semplice, le misure prima di un cambio (ogni stato, due temi, 375, 768 e 1280 px, WCAG AA misurato), lo studio UX prima del codice, la lente UX e la lente utente. | Ogni cambio di un'interfaccia, e delle risposte, dei messaggi e della documentazione di un'API. |

### Agente

`blunt-reviewer`: modello Opus; strumenti Read, Grep, Glob, Bash e Write; precarica `pragmatic-engineering:blunt-review` e `pragmatic-engineering:quality-scoring`. Accetta una riga, `<base>..<tip> [round=1|2] [full=<path>,...]`, scrive `.pe/reviews/<base7>..<tip7>-round<k>.md` e chiude con `VERDICT: pass | changes`, `FINDINGS: <n> (<b> blocking; <lens> S1=<a> S2=<c> S3=<d>; ...)`, `COVERAGE: full | partial`, `REPORT: <path>` e `THE THING: <...>`. La sessione principale lo lancia prima di una merge request, per un intervallo consegnato e per ogni giro del ciclo di revisione.

### Hook

`SessionStart`, registrato in `hooks/hooks.json` come `python3 "${CLAUDE_PLUGIN_ROOT}/hooks/session_start.py"`, con un timeout di 10 secondi. A ogni avvio di sessione copia `rules.md` nella cartella dei dati del plugin quando la copia manca o è diversa, controlla che `~/.claude/CLAUDE.md` porti l'import della copia e la riga di rete di sicurezza, e stampa le righe che mancano, a te e al modello con lo stesso testo. Non blocca mai e non fa mai fallire un avvio di sessione: un problema diventa un avviso. Tace quando le regole sono a posto e nulla è cambiato.

### File

`rules.md` è il file delle regole di lavoro, che comincia con il marcatore `PE-RULES v1`. La cartella `.pe/`, alla radice di un progetto, contiene `reviews/` (i rapporti di `blunt-reviewer`) e `progress.md` (la nota di avanzamento), e non entra mai in git grazie al proprio `.gitignore` con `*`.

<!-- section: license -->
## Licenza

MIT, vedi [LICENSE](LICENSE). Le opere su cui si basa il plugin sono accreditate in [NOTICE](NOTICE).
