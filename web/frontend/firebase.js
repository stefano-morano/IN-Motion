/**
 * firebase.js — Google authentication and Firestore session storage.
 *
 * Firebase config is read from the server (GET /firebase-config),
 * which reads it from the .env file — no hardcoded config in the frontend.
 *
 * SETUP:
 *  1. console.firebase.google.com → Project settings → Web app
 *  2. Copy the values into .env (FIREBASE_API_KEY, FIREBASE_PROJECT_ID, etc.)
 *  3. Enable: Authentication > Sign-in method > Google
 *             Firestore Database > Create database
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
 * Initialize Firebase by fetching config from the backend.
 * Must be awaited before using any other function.
 * Returns true if configured, false if .env variables are missing.
 */
export async function initialize() {
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

/** Open the Google login popup. */
export function loginGoogle() {
    return signInWithPopup(_auth, _provider);
}

/** Sign in with email and password. */
export function loginEmail(email, password) {
    return signInWithEmailAndPassword(_auth, email, password);
}

/** Register with email and password. */
export function registerEmail(email, password) {
    return createUserWithEmailAndPassword(_auth, email, password);
}

/** Send a password-reset email. */
export function resetPassword(email) {
    return sendPasswordResetEmail(_auth, email);
}

/** Sign out the current user. */
export function logout() {
    return signOut(_auth);
}

/**
 * Register a callback fired whenever auth state changes.
 * If Firebase is not configured, calls callback(null) immediately.
 */
export function onAuth(callback) {
    if (!_auth) { callback(null); return () => {}; }
    return onAuthStateChanged(_auth, callback);
}

/**
 * Save a session to Firestore: users/{uid}/sessions/{auto-id}
 */
export async function saveSession(uid, dati) {
    if (!_db) return;
    try {
        await addDoc(collection(_db, 'users', uid, 'sessions'), {
            ...dati,
            data: serverTimestamp(),
        });
        console.log('session saved to Firestore');
    } catch (e) {
        console.warn('Firestore: session save error', e);
    }
}

/**
 * Read the user profile from Firestore: users/{uid}  (field "profilo")
 * Returns the profile object or null if it does not exist yet.
 */
export async function loadProfile(uid) {
    if (!_db) return null;
    try {
        const snap = await getDoc(doc(_db, 'users', uid));
        if (!snap.exists()) return null;
        const d = snap.data();
        // Profile is valid only if it has at least the "nome" field
        return d.nome ? d : null;
    } catch (e) {
        console.warn('Firestore: profile load error', e);
        return null;
    }
}

/**
 * Save (or update) the user profile on Firestore: users/{uid}
 */
export async function saveProfile(uid, dati) {
    if (!_db) return;
    try {
        await setDoc(doc(_db, 'users', uid), {
            ...dati,
            aggiornato: serverTimestamp(),
        }, { merge: true });
        console.log('profile saved to Firestore');
    } catch (e) {
        console.warn('Firestore: profile save error', e);
    }
}

/**
 * Save a daily meditation: users/{uid}/meditazioni/{auto-id}
 * Includes story, post reflection, time series, Italian explanations,
 * pre/post facial data, Claude analysis.
 */
export async function saveDailySession(uid, dati) {
    if (!_db) return null;
    try {
        const today = new Date().toISOString().split('T')[0]; // YYYY-MM-DD
        const ref = await addDoc(collection(_db, 'users', uid, 'meditazioni'), {
            ...dati,
            data_giorno: today,
            data: serverTimestamp(),
        });
        console.log('meditazione salvata su Firestore:', ref.id);
        return ref.id;
    } catch (e) {
        console.warn('Firestore: meditation save error', e);
        return null;
    }
}

/**
 * Load all meditations for a user.
 * Returns an object { 'YYYY-MM-DD': [{dati}, ...], ... }
 */
export async function loadCalendarSessions(uid) {
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
        // If the index is not ready yet, load without ordering
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
