/**
 * firebase.js — autenticazione Google e salvataggio sessioni su Firestore.
 *
 * La configurazione Firebase viene letta dal server (GET /firebase-config),
 * che la legge dal file .env — niente config hardcoded nel frontend.
 *
 * SETUP:
 *  1. console.firebase.google.com → Impostazioni progetto → App web
 *  2. Copia i valori nel .env (FIREBASE_API_KEY, FIREBASE_PROJECT_ID, ecc.)
 *  3. Abilita: Authentication > Sign-in method > Google
 *              Firestore Database > Crea database
 */
import { initializeApp }                              from 'firebase/app';
import { getAuth, signInWithPopup, GoogleAuthProvider,
         signOut, onAuthStateChanged,
         signInWithEmailAndPassword,
         createUserWithEmailAndPassword,
         sendPasswordResetEmail }                     from 'firebase/auth';
import { getFirestore, collection, addDoc, doc, getDoc, setDoc,
         getDocs, query, orderBy,
         serverTimestamp }                            from 'firebase/firestore';

let _auth, _db, _provider;

/**
 * Inizializza Firebase recuperando la config dal backend.
 * Va chiamata con await prima di usare qualsiasi altra funzione.
 * Restituisce true se configurato, false se le variabili .env mancano.
 */
export async function inizializza() {
    const resp = await fetch('/firebase-config');
    const config = await resp.json();

    if (!config.apiKey || config.apiKey === 'INSERISCI-QUI') {
        console.warn('Firebase non configurato: compila le variabili FIREBASE_* nel .env');
        return false;
    }

    const app = initializeApp(config);
    _auth     = getAuth(app);
    _db       = getFirestore(app);
    _provider = new GoogleAuthProvider();
    return true;
}

/** Apre il popup Google per il login. */
export function loginGoogle() {
    return signInWithPopup(_auth, _provider);
}

/** Login con email e password. */
export function loginEmail(email, password) {
    return signInWithEmailAndPassword(_auth, email, password);
}

/** Registrazione con email e password. */
export function registraEmail(email, password) {
    return createUserWithEmailAndPassword(_auth, email, password);
}

/** Invia email di reset password. */
export function resetPassword(email) {
    return sendPasswordResetEmail(_auth, email);
}

/** Disconnette l'utente corrente. */
export function logout() {
    return signOut(_auth);
}

/**
 * Registra un callback chiamato ogni volta che lo stato auth cambia.
 * Se Firebase non è configurato chiama subito callback(null).
 */
export function onAuth(callback) {
    if (!_auth) { callback(null); return () => {}; }
    return onAuthStateChanged(_auth, callback);
}

/**
 * Salva una sessione su Firestore: users/{uid}/sessions/{auto-id}
 */
export async function salvaSessione(uid, dati) {
    if (!_db) return;
    try {
        await addDoc(collection(_db, 'users', uid, 'sessions'), {
            ...dati,
            data: serverTimestamp(),
        });
        console.log('sessione salvata su Firestore');
    } catch (e) {
        console.warn('Firestore: errore salvataggio sessione', e);
    }
}

/**
 * Legge il profilo utente da Firestore: users/{uid}  (campo "profilo")
 * Restituisce l'oggetto profilo o null se non esiste ancora.
 */
export async function caricaProfilo(uid) {
    if (!_db) return null;
    try {
        const snap = await getDoc(doc(_db, 'users', uid));
        if (!snap.exists()) return null;
        const d = snap.data();
        // Il profilo è valido solo se ha almeno il campo "nome"
        return d.nome ? d : null;
    } catch (e) {
        console.warn('Firestore: errore caricamento profilo', e);
        return null;
    }
}

/**
 * Salva (o aggiorna) il profilo utente su Firestore: users/{uid}
 */
export async function salvaProfilo(uid, dati) {
    if (!_db) return;
    try {
        await setDoc(doc(_db, 'users', uid), {
            ...dati,
            aggiornato: serverTimestamp(),
        }, { merge: true });
        console.log('profilo salvato su Firestore');
    } catch (e) {
        console.warn('Firestore: errore salvataggio profilo', e);
    }
}

/**
 * Salva una meditazione giornaliera: users/{uid}/meditazioni/{auto-id}
 * Include racconto, riflessione post, serie temporali, spiegazioni in italiano,
 * dati facciali prima/dopo, analisi Claude.
 */
export async function salvaSessioneGiornaliera(uid, dati) {
    if (!_db) return null;
    try {
        const oggi = new Date().toISOString().split('T')[0]; // YYYY-MM-DD
        const ref = await addDoc(collection(_db, 'users', uid, 'meditazioni'), {
            ...dati,
            data_giorno: oggi,
            data: serverTimestamp(),
        });
        console.log('meditazione salvata su Firestore:', ref.id);
        return ref.id;
    } catch (e) {
        console.warn('Firestore: errore salvataggio meditazione', e);
        return null;
    }
}

/**
 * Carica tutte le meditazioni di un utente.
 * Restituisce un oggetto { 'YYYY-MM-DD': [{dati}, ...], ... }
 */
export async function caricaSessioniCalendario(uid) {
    if (!_db) return {};
    try {
        const snap = await getDocs(
            query(collection(_db, 'users', uid, 'meditazioni'), orderBy('data', 'desc'))
        );
        const mappa = {};
        snap.forEach(d => {
            const dati = d.data();
            const giorno = dati.data_giorno || '';
            if (giorno) {
                if (!mappa[giorno]) mappa[giorno] = [];
                mappa[giorno].push({ id: d.id, ...dati });
            }
        });
        return mappa;
    } catch (e) {
        // Se l'indice non è ancora pronto, carica senza ordine
        try {
            const snap2 = await getDocs(collection(_db, 'users', uid, 'meditazioni'));
            const mappa = {};
            snap2.forEach(d => {
                const dati = d.data();
                const giorno = dati.data_giorno || '';
                if (giorno) {
                    if (!mappa[giorno]) mappa[giorno] = [];
                    mappa[giorno].push({ id: d.id, ...dati });
                }
            });
            return mappa;
        } catch (_) { return {}; }
    }
}
