/**
 * scena.js — coordinate mondo condivise tra logica, testo e renderer.
 *
 * Il rapporto d'aspetto segue la finestra (come in td_face_points.py con
 * render.par.resolutionw / resolutionh), così volto e scritte non si
 * deformano su schermi non 16:9.
 */

export const SCALA = 2.45;

export const TESTO_LARGHEZZA = 2.33;
export const TESTO_ALTEZZA   = 1.10;

export const CAM_TX = 0.0;
export const CAM_TY = 0.0;

export const MANDALA_RIEMPIMENTO = 0.88;

// Distanza della telecamera dal piano z=0. Con la prospettiva impostata in
// particelle.js, a z=0 l'inquadratura e' identica a quella ortografica di
// prima: cambia solo cio' che sta davanti o dietro quel piano, che e' appunto
// il senso di profondita' che si voleva.
export const CAM_TZ = 2.8;

// ---------------------------------------------------------------- webcam
// MediaPipe normalizza x sulla LARGHEZZA dell'immagine e y sull'ALTEZZA,
// separatamente: un passo in x e uno in y non sono la stessa distanza reale.
// Per rimettere il volto in proporzione serve il rapporto d'aspetto della
// TELECAMERA — non quello della finestra, che non c'entra nulla. Usando
// quello dello schermo, su una finestra piu' larga di 16:9 il volto veniva
// schiacciato e allargato.
let _aspettoWebcam = 16 / 9;   // ripiego, finche' il video non e' pronto

export function aspettoWebcam() {
    return _aspettoWebcam;
}

export function impostaAspettoWebcam(a) {
    if (Number.isFinite(a) && a > 0) _aspettoWebcam = a;
}

export function aspettoSchermo() {
    const w = window.innerWidth  || 1280;
    const h = window.innerHeight || 720;
    return w / h;
}

export function larghezzaMondo() {
    return aspettoSchermo() * SCALA;
}

export function altezzaMondo() {
    return SCALA;
}

export function raggioVisibile() {
    return (SCALA / 2.0) * MANDALA_RIEMPIMENTO;
}
